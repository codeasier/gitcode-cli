# Shared transport boundaries

The CLI and MCP reuse native services, but have different transport policies.
This document records the boundaries for [issue #155](https://github.com/codeasier/gitcode-cli/issues/155).
The behavior comparison below is anchored to [source baseline c0838056](https://github.com/codeasier/gitcode-cli/tree/c083805695b2fe746a51b9a0aa8c922e59c20cc9); it is not a live-provider acceptance claim.

## Producer-only response reader

`gitcode_cli.transport.read_response_bytes(response, *, max_response_bytes)`
is an unreleased, credential-agnostic primitive. Neither `GitCodeClient` nor
`GitCodeAPI` uses it yet. It does not change the public service/client request
signature, CLI behavior, MCP dependency pin, tool catalog, or deployment.

- Supply an exact positive built-in `int`, or explicitly `None` for unlimited
  buffering. Booleans, integer subclasses (including enums), floats, strings,
  zero and negative values raise a fixed `ValueError` before stream consumption.
  There is deliberately no default limit.
- The helper returns bytes from HTTPX `iter_bytes`, after HTTP content decoding.
  It counts those bytes rather than trusting `Content-Length`. Overflow raises
  `ResponseTooLargeError`; it never returns a truncated or partial result.
- The overflow exception has a fixed message and no response-specific fields.
  The helper does not log, interpret status or text, parse JSON, send requests,
  resolve credentials, follow redirects, retry, or paginate.
- HTTPX stream exceptions propagate unchanged. The entry point must retain its
  existing credential-safe mapping; raw exception text and tracebacks are not
  suitable for callers or logs.
- The caller owns the response context and must close it on success or failure.
  The finite limit is a decoded-payload limit, not a total process-memory bound:
  HTTPX decompression may allocate temporary memory before yielding a chunk.
  `None` is intentionally unlimited and is not an appropriate MCP policy.

A future consumer must check status and redirects at the appropriate point
**before** invoking this reader. In particular, MCP must not start reading
upstream error bodies just because the reader is shared. No shared decoder,
policy switch, HTTP client factory, or error hierarchy is introduced here.

## Entry policies that must remain separate

| Boundary | CLI baseline | MCP baseline |
| --- | --- | --- |
| Credential source and attachment | CLI token resolution remains flag, then `GC_TOKEN`, then CLI config. The client adds query `access_token` and adds `private-token` only for its repository method/path allowlist. | Bearer header only; credential query keys are rejected. OAuth obtains the current connection's upstream credential, without falling back to CLI configuration or server PAT. |
| Redaction | Request-scoped HTTPX/HTTPCore log filtering and error redaction cover literal and URL-encoded tokens plus `access_token` values. Successful payloads are returned unchanged. | Upstream error bodies, URLs and exception strings are not returned. Successful JSON keys/values and text have literal reflected tokens removed recursively. |
| Origin and paths | Configurable client `base_url`; `/user`, `/user/repos` and organization endpoints remain valid. Client URL joining and command-level target validation are distinct responsibilities. | Fixed `https://api.gitcode.com/api/v5/`; requires `/repos/` paths and retains decoded traversal/URL/separator guards. Tool-level repository allowlists remain separate. |
| Network and timeout | Constructs HTTPX with a 30-second timeout and otherwise leaves its constructor policies at library defaults. | Explicitly disables redirects and environment-derived network settings with `follow_redirects=False` and `trust_env=False`. Default timeout is 30 seconds; environment configuration bounds it to 1–120 seconds. |
| Retries and uncertain writes | No automatic request retry. Errors for non-GET methods carry remote-state verification guidance. | No automatic retries. POST/PUT/PATCH/DELETE timeout, network, redirect, oversized/invalid response and 5xx outcomes carry structured write-uncertainty metadata; definitive 4xx normally do not. |
| Response size | Eager response loading, without an application byte ceiling. | Streams decoded bytes with a default 2,000,000-byte ceiling, rejecting overflow rather than truncating; checks redirects and error status before body consumption. |
| Status and decoding | Rejects non-2xx and 202. Empty JSON bodies are accepted only for 204/205; JSON `null` is rejected. Repository deletion has additional confirmation rules. Text uses HTTPX decoding. | Transport accepts 202, empty bodies and JSON `null`; higher-level result validation remains independent. Text requires valid UTF-8. Redirects have their own error code. |
| Error presentation | Typed CLI errors preserve redacted upstream detail; 401 includes a CLI login hint. | Static error codes/messages, with bounded numeric `Retry-After` for 429. File-write commit/SHA verification remains a higher-level policy. |
| Pagination | Services/adapters own it. PR linked issues and comments eagerly aggregate, rejecting malformed/repeated pages and limiting page count. | One upstream page per call; overfull pages rejected. Unpaged collections are bounded and locally sliced, explicitly not a stable multi-page snapshot. |

Implementation references at the baseline:
[CLI client](https://github.com/codeasier/gitcode-cli/blob/c083805695b2fe746a51b9a0aa8c922e59c20cc9/src/gitcode_cli/client.py),
[CLI redaction](https://github.com/codeasier/gitcode-cli/blob/c083805695b2fe746a51b9a0aa8c922e59c20cc9/src/gitcode_cli/_redact.py),
[MCP transport and pagination](https://github.com/codeasier/gitcode-cli/blob/c083805695b2fe746a51b9a0aa8c922e59c20cc9/packages/gitcode-mcp/src/gitcode_mcp/api.py),
[OAuth request credentials](https://github.com/codeasier/gitcode-cli/blob/c083805695b2fe746a51b9a0aa8c922e59c20cc9/packages/gitcode-mcp/src/gitcode_mcp/server.py#L82-L113),
[CLI pagination](https://github.com/codeasier/gitcode-cli/blob/c083805695b2fe746a51b9a0aa8c922e59c20cc9/src/gitcode_cli/services/pulls.py#L27-L58).

These differences must not be silently normalized during extraction. In
particular, a common status/JSON decoder would change existing 202, empty/null,
text-decoding and repository-deletion behavior.

## Validation and later adoption

The producer's offline unit contracts cover exact/overflow/unlimited limits,
opaque bytes, multiple chunks, invalid limits before reads, misleading or absent
Content-Length, compressed bodies, unchanged stream errors, payload-free overflow
errors and caller-owned cleanup. They do not call GitCode.

The installed-checkout probe is in
`packages/gitcode-mcp/tests_checkout/test_transport.py`. The source-compatibility
workflow verifies the installed `transport.py` hash and explicitly selects this
suite. The normal MCP suite and published-`pygitcode==0.1.7` artifact suites do
not select checkout-only tests. Root CLI tests still use the existing 90%
coverage floor and Python 3.9–3.13 CI; MCP source compatibility uses Python
3.11–3.13. CI results must be tied to the actual candidate commit.

Before any runtime adopts the reader:

1. Preserve the existing request/helper signatures; services never acquire
   credential or entry-policy arguments.
2. Characterize CLI custom origins, `/user`, authentication allowlists, logging,
   and 202/empty/null/text/delete behavior, alongside MCP origin/query guards,
   no-proxy/no-redirect policy, body-read ordering, and uncertainty metadata.
3. Assert one request for uncertain writes, unchanged pagination call counts,
   response closure on every outcome, and no credential/body disclosure.
4. Keep CLI and MCP response/error decoding in their respective entry layers.
   A new CLI limit or change to an existing policy needs its own compatibility
   decision, not an incidental consequence of reuse.
5. Release and verify actual CLI artifacts under separate authorization before
   changing MCP's pinned dependency and adopting the producer in production.
   Checkout compatibility is not release, OAuth, or deployment acceptance.

This producer slice does not complete transport convergence or issue #155.
