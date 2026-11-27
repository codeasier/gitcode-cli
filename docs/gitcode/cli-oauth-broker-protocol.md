# Standalone CLI OAuth broker: client protocol

This is an unmounted component, not a published service or an available
`gc auth login` mode. It does not configure a public broker, start a listener,
persist CLI credentials, change PAT behavior or issue MCP grants. The existing
MCP OAuth application is not a CLI broker.

A future native client must pin an independently configured HTTPS broker origin,
verify TLS and avoid following redirects or logging bodies, proof material or
credentials. Never accept an issuer, callback or credential location from a
transaction response. The embedding service must supply a dedicated encrypted
store/key, fixed official OAuth app registration and a trusted Bearer-only
GitCode identity verifier. Access logs, proxies and traces must omit query
strings, headers, bodies and responses. A trusted ingress must enforce its own
header, elapsed-time, connection and deployment-wide admission limits; never
derive a trusted origin from arbitrary forwarded headers.

1. Generate 32 cryptographically random bytes, encode using unpadded base64url
   (43 characters) and keep this **verifier** private. SHA-256 its ASCII bytes;
   send the unpadded base64url **challenge** to `POST /cli/v1/start` as the only
   JSON field. HTTP 201 returns exactly `selector`, `pairing` and `browser_url`.
   Confirm that URL equals the pinned origin plus `/cli/v1/browser`, with no
   parameters. Open only that clean URL. Show the one-use pairing value only on
   the requesting terminal; the user enters it into their own browser. It is
   not a device code and must not be put in a URL or sent to another person.
2. The browser pairs, authorizes at GitCode and returns to the registered
   callback. Only the same paired browser may submit fresh same-origin consent
   to the independently verified GitCode identity. A successful callback or
   cookie alone is not approval.
3. Send `POST /cli/v1/redeem` with exactly `selector` and `verifier` in JSON.
   HTTP 202 `{"status":"pending","retry_after":5}` is returned only to the
   verifier holder. Wait at least five seconds before polling again, stopping
   no later than five minutes after the initial start or when the user cancels.
   HTTP 200 contains `status: authorized`, `subject`, `login`, `expires_at`
   (Unix seconds) and the **one-time** `access_token` receipt. The token is
   never returned by a browser route. Only the first committed redemption can
   succeed, including across broker restarts using the same store and binding.
   Never print the receipt; a future CLI must validate and persist credentials
   independently, and this component installs no token.
4. A denied, expired, misbound, consumed or missing flow returns the same HTTP
   400 unavailable response. Do not retry. HTTP 429 is admission rejection
   before state access. Store/budget errors return generic HTTP 503 where a
   response can still be sent. A timeout, broken connection or lost receipt
   can occur after commit: never replay an uncertain mutation or attempt to
   recover the released token. Initiate a new explicit login instead. A failed
   upstream exchange may remain unavailable for completion until its original
   deadline and must not be re-exchanged.

Both native routes require exact fixed paths/authority, HTTPS POST,
`application/json`, one explicit byte-accurate Content-Length of at most
256 bytes, no query string, no credential/cookie/origin/referrer headers and
no content/transfer encoding. Every reply is non-cacheable; neither endpoint
redirects. Each operation shares a five-second monotonic budget across input,
database admission/commit and response, with its final 0.1 s reserved for
the reply. A synchronous SQLite commit already in progress cannot be revoked,
and a transport exception does not roll it back. The single-process limits
are 20 starts/minute and 120 redemption attempts/minute; browser admissions
are independent. They are deliberately not per-client or cluster quotas.

Offline tests exercise genuine pairing and consent paths with a synthetic
upstream, local encrypted storage, replay/concurrency, rejection and bounded
failure. They do **not** establish live provider, browser, deployed broker,
CLI command, refresh/revocation or credential-store acceptance.
