"""Contract for a single direct CLI Tree request, using synthetic HTTP only."""

from __future__ import annotations

import gzip
import inspect
import json
from unittest.mock import Mock

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import repo_read
from gitcode_cli.cli import main
from gitcode_cli.errors import GCError
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command
from gitcode_cli.repo_read_dir import MAX_PAGE, fetch_page

COMMIT = "7fe24b3805ade9beb48e55f354315960567443d3"
DIR = "scripts/MemSnapDump"
ARGS = ["repo", "read-dir", "-R", "gitcode.com/Ascend/msinsight", "--ref", COMMIT]
MODES = {"tree": "040000", "blob": "100644", "commit": "160000"}


def item(name="base", directory=DIR, kind="tree", **extras):
    return {
        "name": name,
        "path": f"{directory}/{name}" if directory else name,
        "type": kind,
        "mode": MODES[kind],
        "sha": "23ef9378491c404901dcaa760b7f0757bc9faba3",
        **extras,
    }


def run(args, charset="utf-8"):
    if "mix_stderr" in inspect.signature(CliRunner.__init__).parameters:
        return CliRunner(mix_stderr=False, charset=charset).invoke(main, args)
    return CliRunner(charset=charset).invoke(main, args)


@pytest.fixture
def install(monkeypatch, tmp_config_dir):
    real = httpx.Client
    monkeypatch.delenv("GC_TOKEN", raising=False)

    def configure(handler):
        provider = Mock(side_effect=handler)

        def client(**kwargs):
            assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
            return real(transport=httpx.MockTransport(provider), **kwargs)

        monkeypatch.setattr(repo_read.httpx, "Client", client)
        return provider

    return configure


def test_pinned_tree_one_page_preserves_paths_and_continuation_uncertainty(install):
    entries = [item(name=f"child{i}") for i in range(5)]

    def handle(req):
        assert req.method == "GET" and req.url.scheme == "https" and req.url.host == "api.gitcode.com"
        assert req.url.path == f"/api/v5/repos/Ascend/msinsight/git/trees/{COMMIT}"
        params = dict(req.url.params)
        assert set(params) == {"page", "per_page", "file_path"} and params["file_path"] == DIR
        assert req.headers["Accept-Encoding"] == "identity" and "authorization" not in req.headers
        page, limit = int(params["page"]), int(params["per_page"])
        return httpx.Response(200, json={"sha": COMMIT, "tree": entries[(page - 1) * limit : page * limit]})

    provider = install(handle)
    for page, limit, count, full in [(1, 3, 3, True), (2, 3, 2, False), (1, 5, 5, True), (2, 5, 0, False)]:
        result = run([*ARGS, DIR, "--page", str(page), "--per-page", str(limit)])
        assert result.exit_code == 0, result.output
        lines = result.stdout.splitlines()
        assert len(lines) == count
        assert all(line.startswith("040000 tree ") and f"\t{DIR}/child" in line for line in lines)
        assert ("may be empty" in result.stderr) is full
        if not count:
            assert "does not confirm" in result.stderr
    assert provider.call_count == 4  # No lookahead, recursion or Contents fallback.


def test_literal_ref_and_query_encoding_and_header_auth(install):
    path = "dir space/中 %2F?#"

    def handle(req):
        assert req.url.raw_path.split(b"?")[0].endswith(b"/git/trees/topic%2Ftag%23%252F")
        assert dict(req.url.params) == {"file_path": path, "page": "1", "per_page": "20"}
        assert req.headers["Authorization"] == "Bearer dummy-secret"
        assert "private-token" not in req.headers and "dummy-secret" not in str(req.url)
        return httpx.Response(
            200, json={"tree": [item("链接", path, "blob", mode="120000"), item("sub", path, "commit")]}
        )

    provider = install(handle)
    result = run(["-R", "Acme/project", "--token", "dummy-secret", "repo", "read-dir", "--ref", "topic/tag#%2F", path])
    assert result.exit_code == 0 and "120000 blob " in result.stdout and "160000 commit " in result.stdout
    assert f"{path}/链接" in result.stdout
    provider.assert_called_once()


def test_exact_subtree_sha_root_yields_relative_names_without_file_path(install, monkeypatch):
    monkeypatch.setattr("gitcode_cli.commands.repo._origin_repository_arg", lambda: "git@ssh.gitcode.com:org/repo.git/")
    subtree = "e7ffdd5a9ae903675df4fd670bdf751cfe0b38e1"

    def handle(req):
        assert req.url.path.endswith(f"/repos/org/repo/git/trees/{subtree}")
        assert dict(req.url.params) == {"page": "1", "per_page": "20"}
        return httpx.Response(200, json={"tree": [item("a.py", "", "blob")]})

    provider = install(handle)
    result = run(["repo", "read-dir", "--ref", subtree])
    assert result.exit_code == 0 and result.stdout.endswith("\ta.py\n")
    provider.assert_called_once()


@pytest.mark.parametrize("path", ["missing", "README.md", "maybe-empty"])
def test_filtered_empty_first_page_cannot_prove_directory(install, path):
    provider = install(lambda _: httpx.Response(200, json={"tree": []}))
    result = run([*ARGS, path])
    assert result.exit_code == 1 and not result.stdout and "Inspect its parent" in result.stderr
    provider.assert_called_once()


@pytest.mark.parametrize(
    "args",
    [
        ["-R", "o/r"],
        ["--ref", "main", "-R", "github.com/o/r"],
        ["--ref", "invalid..ref", "-R", "o/r"],
        ["--ref", "main", "-R", "o/r", "../escape"],
        ["--ref", "main", "-R", "o/r", ""],
        ["--ref", "main", "-R", "o/r", "/root"],
        ["--ref", "main", "-R", "o/r", "--per-page", "101"],
        ["--ref", "main", "-R", "o/r", "--page", "0"],
        ["--ref", "main", "-R", "o/r", "--page", str(MAX_PAGE + 1)],
    ],
)
def test_reject_bad_inputs_before_request(install, args):
    provider = install(lambda _: pytest.fail("invalid CLI input must not contact provider"))
    assert run(["repo", "read-dir", *args]).exit_code != 0
    provider.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"tree": {}},
        {"tree": [item(), item()]},
        {"tree": [item(), {}]},
        {"tree": [item(), 3]},
        {"tree": [item(path="another/base")]},
        {"tree": [item("README.md", "", "blob")]},  # An ignored file_path must not become a root listing.
        {"tree": [item(name="../outside")]},
        {"tree": [item(name="nested/child")]},
        {"tree": [item(name="..")]},
        {"tree": [item(name="")]},
        {"tree": [item(name="bad\x1b[2J")]},
        {"tree": [item(name="bad\u202e")]},
        {"tree": [item(name="bad\\p")]},
        {"tree": [item(sha=None)]},
        {"tree": [item(mode="1")]},
        {"tree": [item(type="blob")]},
        {"tree": [], "truncated": True},
        {"tree": [], "truncated": "false"},
    ],
)
def test_malformed_or_unconfirmed_rows_never_print_partial_page(install, payload):
    provider = install(lambda _: httpx.Response(200, json=payload))
    result = run([*ARGS, DIR])
    assert result.exit_code == 1 and not result.stdout
    provider.assert_called_once()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(302, headers={"location": "https://another.invalid/secret"}),
        httpx.Response(401, text="sensitive"),
        httpx.Response(429, text="sensitive"),
        httpx.Response(200, json={"tree": [item(), item("two")]}),
        httpx.Response(200, content=b'{"tree": [], "tree": []}'),
        httpx.Response(200, content=b" " * (repo_read.MAX_RESPONSE + 1)),
        httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(b'{"tree":[]}')),
    ],
)
def test_fail_closed_no_retry_or_body_disclosure(install, response):
    requests = install(lambda _: response)
    result = run([*ARGS, DIR, "--per-page", "1"])
    assert result.exit_code == 1 and not result.stdout and "sensitive" not in result.stderr
    requests.assert_called_once()


def test_secret_in_target_or_result_is_not_printed(install):
    req = install(lambda _: httpx.Response(200, json={"tree": [item(name="dummy-secret", directory="")]}))
    for expected, extra in [(0, ["dummy-secret"]), (1, [])]:
        result = run(["--token", "dummy-secret", *ARGS, *extra])
        assert result.exit_code == 1 and not result.stdout and "dummy-secret" not in result.stderr
        assert req.call_count == expected


def test_direct_only_and_discoverable():
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(["repo", "read-dir", "--ref", "main", "-R", "gitcode.com/o/r"])
    assert "read-dir" in run(["repo", "--help"]).output


@pytest.mark.parametrize(("page", "size"), [(0, 1), (True, 1), (1, False), (1, 101), (MAX_PAGE + 1, 1)])
def test_programmatic_bounds_before_network(install, page, size):
    requests = install(lambda _: pytest.fail("invalid page must not contact provider"))
    with pytest.raises(GCError):
        fetch_page("team", "repo", None, COMMIT, page, size, "")
    requests.assert_not_called()


def test_last_allowed_full_page_has_no_unusable_next_hint(install):
    install(lambda _: httpx.Response(200, json={"tree": [item()]}))
    result = run([*ARGS, DIR, "--page", str(MAX_PAGE), "--per-page", "1"])
    assert result.exit_code == 0 and "remaining entries are unknown" in result.stderr


def test_redirected_output_uses_exact_utf8_even_with_gbk_stream(install):
    install(lambda _: httpx.Response(200, json={"tree": [item("目录🌍", "", "tree")]}))
    result = run(ARGS, charset="gbk")
    assert result.exit_code == 0 and result.stdout_bytes.endswith("\t目录🌍\n".encode())


def test_encoded_token_not_printed_or_reflected(install):
    req = install(lambda _: httpx.Response(200, json={"tree": [item("dummy%2Fsecret", "", "blob")]}))
    for expected, extra in [(0, ["dummy%2Fsecret"]), (1, [])]:
        result = run(["--token", "dummy/secret", *ARGS, *extra])
        assert result.exit_code == 1 and not result.stdout and "dummy" not in result.stderr
        assert req.call_count == expected


def test_json_page_projects_native_child_fields_preserving_order_and_kind(install):
    rows = [
        item('z"🌍', DIR, "blob", mode="120000", sha="a" * 40),
        item("a", DIR, "commit", sha="B" * 40),
        item("m", DIR, "tree", sha="1" * 40),
    ]

    def handle(req):
        assert req.method == "GET" and req.url.path == f"/api/v5/repos/Ascend/msinsight/git/trees/{COMMIT}"
        assert dict(req.url.params) == {"file_path": DIR, "page": "3", "per_page": "3"}
        assert "authorization" not in req.headers
        return httpx.Response(
            200,
            json={
                "sha": "e" * 40,
                "tree": [
                    {**row, "gitSHA": COMMIT, "gitType": "file", "url": "https://ignored.invalid", "size": 9}
                    for row in rows
                ],
            },
        )

    provider = install(handle)
    result = run([*ARGS, DIR, "--page", "3", "--per-page", "3", "--json"], charset="gbk")
    assert result.exit_code == 0, result.stderr
    output = json.loads(result.stdout_bytes.decode("utf-8"))
    assert output == [{"name": r["name"], "path": r["path"], "gitSHA": r["sha"], "gitType": r["type"]} for r in rows]
    assert list(output[0]) == ["name", "path", "gitSHA", "gitType"]
    assert "--page 4" in result.stderr and "may be empty" in result.stderr
    provider.assert_called_once()


def test_json_modes_use_validated_tree_values_without_extra_requests(install):
    # Independent decimal values; modeOctal must keep the leading zero for directories.
    cases = [
        ("dir", "tree", "040000", 16384),
        ("file", "blob", "100644", 33188),
        ("exec", "blob", "100755", 33261),
        ("link", "blob", "120000", 40960),
        ("sub", "commit", "160000", 57344),
    ]
    rows = [item(name, DIR, kind, mode=mode, modeOctal="untrusted") for name, kind, mode, _ in cases]

    def handle(req):
        assert req.method == "GET" and req.url.path == f"/api/v5/repos/Ascend/msinsight/git/trees/{COMMIT}"
        assert dict(req.url.params) == {"page": "1", "per_page": "20", "file_path": DIR}
        return httpx.Response(200, json={"tree": rows})

    provider = install(handle)
    result = run([*ARGS, DIR, "--json", "modeOctal,name,mode"])
    assert result.exit_code == 0 and not result.stderr, result.output
    assert [list(row.items()) for row in json.loads(result.stdout)] == [
        [("modeOctal", mode), ("name", name), ("mode", number)] for name, _, mode, number in cases
    ]
    provider.assert_called_once()


def test_json_selected_keys_and_max_page_hint(install):
    def handle(req):
        assert dict(req.url.params) == {"page": str(MAX_PAGE), "per_page": "1"}
        return httpx.Response(200, json={"tree": [item("a", "", "blob")]})

    provider = install(handle)
    result = run([*ARGS, "--json", "gitType, name", "--per-page", "1", "--page", str(MAX_PAGE)])
    assert result.exit_code == 0 and list(json.loads(result.stdout)[0].items()) == [("gitType", "blob"), ("name", "a")]
    assert "remaining entries are unknown" in result.stderr
    provider.assert_called_once()


@pytest.mark.parametrize(
    "options",
    [
        ["--json", "size"],
        ["--json", "modeoctal"],
        ["--json", "content"],
        ["--json", "path,gitSha"],
        ["--json="],
        ["--json", "path,"],
        ["--json", ",name"],
        ["--json", "path, path"],
        ["--json", "path", "--json", "name"],
        ["--json", "untrusted-not-for-echoing"],
        ["--json", "--per-page", "0"],
        ["--json", "--per-page", "101"],
        ["--json", "--page", str(MAX_PAGE + 1)],
        ["--json", "--jq", "."],
        ["--json", "--template", "{{.path}}"],
    ],
)
def test_invalid_json_selector_or_page_fails_before_lookup(install, monkeypatch, options):
    origin = Mock(side_effect=AssertionError("invalid selector should not resolve origin"))
    monkeypatch.setattr("gitcode_cli.commands.repo._origin_repository_arg", origin)
    provider = install(lambda _: pytest.fail("no API call expected"))
    result = run(["repo", "read-dir", "--ref", COMMIT, *options])
    assert result.exit_code == 2 and result.stdout_bytes == b"" and "untrusted-not-for-echoing" not in result.stderr
    provider.assert_not_called()
    origin.assert_not_called()


@pytest.mark.parametrize(
    "bad",
    [
        item("b", sha=None),
        item("b", type="blob"),
        item("b", mode="bad"),
        item("b", path="wrong/b"),
        item("a"),
        item("dummy-secret"),
        item("dummy%2Fsecret"),
    ],
)
def test_json_rejects_whole_page_even_when_bad_field_not_selected(install, bad):
    provider = install(lambda _: httpx.Response(200, json={"tree": [item("a"), bad]}))
    token = "dummy/secret" if bad["name"] == "dummy%2Fsecret" else "dummy-secret"
    result = run(["--token", token, *ARGS, DIR, "--json", "gitType"])
    assert result.exit_code == 1 and result.stdout_bytes == b"" and "dummy" not in result.stderr
    provider.assert_called_once()


@pytest.mark.parametrize("payload", [{"tree": [item("a"), item("b")]}, {"truncated": True, "tree": [item("a")]}])
def test_json_refuses_invalid_page_without_truncation(install, payload):
    provider = install(lambda _: httpx.Response(200, json=payload))
    result = run([*ARGS, DIR, "--per-page", "1", "--json", "path"])
    assert result.exit_code == 1 and result.stdout_bytes == b""
    provider.assert_called_once()


@pytest.mark.parametrize(("extra", "ok"), [([], True), ([DIR], False), ([DIR, "--page", "2"], True)])
def test_json_empty_pages_report_ambiguity_on_stderr(install, extra, ok):
    provider = install(lambda _: httpx.Response(200, json={"tree": []}))
    result = run([*ARGS, *extra, "--json"])
    assert result.exit_code == (0 if ok else 1)
    assert result.stdout_bytes == (b"[]\n" if ok else b"") and "does not confirm" in result.stderr
    provider.assert_called_once()


def test_encoded_json_cannot_reconstitute_a_token(install):
    # JSON inserts a backslash before a quote; that secret never appeared in the native line.
    provider = install(lambda _: httpx.Response(200, json={"tree": [item('z"x', "", "blob")]}))
    result = run(["--token", r"z\"x", *ARGS, "--json", "name"])
    assert result.exit_code == 1 and not result.stdout_bytes
    assert r"z\"x" not in result.stderr
    provider.assert_called_once()


def test_json_discoverable_and_still_direct_only():
    help_text = run(["repo", "read-dir", "--help"]).output
    assert "--json" in help_text and "JSON FIELDS" in help_text
    assert all(field in help_text for field in ("gitSHA", "modeOctal", "mode"))
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(["repo", "read-dir", "--ref", "main", "--json", "path", "-R", "gitcode.com/o/r"])


# Object IDs independently produced with 'git mktree -z --missing' (SHA-1).
# Including a.c, directory a and a0 distinguishes Git sorting from lexical name sorting.
ALL_ROWS = [
    item("a0", "", "blob", mode="100755", sha="A" * 40),
    item("sub", "", "commit", sha="c" * 40),
    item("a", "", "tree", sha="1" * 40),
    item('é"🌍', "", "blob", sha="4" * 40),
    item("a.c", "", "blob", sha="a" * 40),
    item("link", "", "blob", mode="120000", sha="5" * 40),
]
TREE = "a65c6637d20d88455075ed6ad357400da0ca697a"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def all_args(ref=TREE):
    return ["repo", "read-dir", "-R", "team/project", "--all", "--ref", ref]


@pytest.mark.parametrize(("size", "pages"), [(2, 4), (4, 2), (100, 1)])
def test_all_pins_tree_and_checks_git_oid_without_sorting_provider_output(install, size, pages):
    calls = []

    def handle(req):
        calls.append(len(calls) + 1)
        assert req.method == "GET" and req.url.path == f"/api/v5/repos/team/project/git/trees/{TREE}"
        assert dict(req.url.params) == {"page": str(calls[-1]), "per_page": str(size)}
        assert req.headers["Authorization"] == "Bearer dummy-secret"
        start = (calls[-1] - 1) * size
        return httpx.Response(200, json={"tree": ALL_ROWS[start : start + size]})

    provider = install(handle)
    result = run(["--token", "dummy-secret", *all_args(), "--per-page", str(size), "--json", "name,gitType,modeOctal"])
    assert result.exit_code == 0 and not result.stderr, result.output
    assert json.loads(result.stdout_bytes) == [
        {"name": r["name"], "gitType": r["type"], "modeOctal": r["mode"]} for r in ALL_ROWS
    ]
    assert provider.call_count == pages


@pytest.mark.parametrize(
    "last_page",
    [
        {"tree": []},  # A short or empty response by itself is not proof of completeness.
        {"tree": ALL_ROWS[2:3]},
        {"tree": [ALL_ROWS[1]]},  # Duplicate across pages, including exact replay.
        {"tree": [dict(ALL_ROWS[2], sha="6" * 40)]},
        {"tree": [dict(ALL_ROWS[2], path="elsewhere/a")]},
        {"tree": [ALL_ROWS[2]], "truncated": True},
        {"tree": [ALL_ROWS[2], {}, ALL_ROWS[4]]},
        None,
    ],
)
def test_all_never_prints_prefix_on_later_failure(install, last_page):
    def handle(req):
        if req.url.params["page"] == "1":
            return httpx.Response(200, json={"tree": ALL_ROWS[:2]})
        assert req.url.params["page"] == "2"
        return httpx.Response(200, json=last_page) if last_page is not None else httpx.Response(403, text="foo-secret")

    provider = install(handle)
    result = run([*all_args(), "--per-page", "2", "--json", "gitType"])
    assert result.exit_code != 0 and result.stdout_bytes == b"" and "foo-secret" not in result.stderr
    assert provider.call_count == 2


def test_all_empty_tree_and_empty_impostor(install):
    provider = install(lambda _: httpx.Response(200, json={"tree": []}))
    result = run([*all_args(EMPTY_TREE), "--json"])
    assert result.exit_code == 0 and result.stdout == "[]\n" and not result.stderr
    wrong = run([*all_args(COMMIT), "--json"])
    assert wrong.exit_code != 0 and not wrong.stdout
    assert provider.call_count == 2


@pytest.mark.parametrize("extra", [["--page", "1"], ["--page", "2"], ["dir"]])
def test_all_cannot_combine_path_or_page(install, extra):
    provider = install(lambda req: pytest.fail("invalid combination should not make requests"))
    result = run([*all_args(), *extra])
    assert result.exit_code == 2 and not result.stdout
    provider.assert_not_called()


@pytest.mark.parametrize("name", ["main", "topic/v1", TREE[:8], ""])
def test_all_refuses_moving_or_short_ref(install, name):
    provider = install(lambda req: pytest.fail("never page a mutable ref"))
    result = run(all_args(name))
    assert result.exit_code != 0 and not result.stdout
    provider.assert_not_called()


def test_all_hard_request_budget_includes_finding_completion(install, monkeypatch):
    from gitcode_cli import repo_read_dir

    monkeypatch.setattr(repo_read_dir, "MAX_TREE_PAGES", 2)
    provider = install(lambda req: httpx.Response(200, json={"tree": [ALL_ROWS[int(req.url.params["page"]) - 1]]}))
    exact = run([*all_args("4963befdc43c2403e45f19b40d3641deb6bc69fd"), "--per-page", "1"])
    assert exact.exit_code == 0 and len(exact.stdout.splitlines()) == 2
    assert provider.call_count == 2  # Exact fit proven by the tree object, no over-budget probe.
    over = run([*all_args(), "--per-page", "1"])
    assert over.exit_code != 0 and not over.stdout and "limit" in over.stderr
    assert provider.call_count == 4


def test_all_detects_wrong_tree_even_when_all_rows_are_well_formed(install):
    altered = [dict(row) for row in ALL_ROWS]
    altered[-1]["mode"] = "100644"  # Still a blob; a name-only comparison wouldn't notice.
    provider = install(lambda req: httpx.Response(200, json={"tree": altered}))
    result = run([*all_args(), "--json", "name"])
    assert result.exit_code != 0 and not result.stdout_bytes
    provider.assert_called_once()


def test_all_verifies_output_token_guard_even_after_hash_match(install):
    provider = install(lambda req: httpx.Response(200, json={"tree": ALL_ROWS}))
    # Backslash appears only after JSON escaping; the input row itself has no backslash.
    result = run(["--token", r"\"", *all_args(), "--json", "path"])
    assert result.exit_code != 0 and not result.stdout_bytes
    provider.assert_called_once()
