"""Strict offline HTTP contract for read-only PR commit comparison."""

import copy
import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, dispatch

HEAD = "a" * 40
BASE = "b" * 40
COMMON = "c" * 40
TOKEN = "update-plan-synthetic"
PREFIX = "/api/v5/repos/o/r"
DETAIL = f"{PREFIX}/pulls/7"
API_URL = f"https://api.gitcode.com{DETAIL}"
FORWARD = f"{PREFIX}/compare/{BASE}...{HEAD}"
REVERSE = f"{PREFIX}/compare/{HEAD}...{BASE}"
PR = {
    "number": 7,
    "id": 107,
    "state": "open",
    "html_url": "https://gitcode.com/o/r/pulls/7",
    "url": API_URL,
    "head": {"ref": "feature/build", "sha": HEAD, "repo": {"full_name": "o/r"}},
    "base": {
        "ref": "main",
        "sha": BASE,
        "repo": {"full_name": "o/r", "path": "r", "namespace": {"path": "o"}, "html_url": "https://gitcode.com/o/r"},
    },
}


def compare(start, merge_base, **overrides):
    return {
        "base_commit": {"sha": start},
        "merge_base_commit": {"sha": merge_base},
        "commits": [],
        "files": [],
        "truncated": 0,
        **overrides,
    }


@pytest.fixture
def invoke(monkeypatch):
    def run(*steps, args=None, token=TOKEN):
        expected = iter(steps)

        def respond(request):
            step = next(expected, None)
            assert step is not None, "Unexpected request"
            path, payload = step
            assert request.method == "GET" and request.url.host == "gitcode.com.invalid"
            assert request.url.scheme == "https" and request.url.raw_path == path.encode("ascii")
            assert not request.content and "private-token" not in request.headers
            assert request.headers.get("authorization") == (f"Bearer {token}" if token else None)
            assert request.headers["accept-encoding"] == "identity"
            if isinstance(payload, httpx.Response):
                return payload
            return httpx.Response(200, json=payload)

        client_class = httpx.Client

        def client(**kwargs):
            assert kwargs == {"timeout": 30, "follow_redirects": False, "trust_env": False}
            return client_class(transport=httpx.MockTransport(respond), **kwargs)

        def no_git(*_args, **_kwargs):
            pytest.fail("Explicit PR update plan must not run any Git commands")

        monkeypatch.setattr("gitcode_cli.repo_read.BASE_URL", "https://gitcode.com.invalid/api/v5/")
        monkeypatch.setattr("gitcode_cli.repo_read.httpx.Client", client)
        monkeypatch.setattr("gitcode_cli.repo.subprocess.run", no_git)
        monkeypatch.setattr("gitcode_cli.cli.get_token", lambda: token)
        argv = ["--token", token] if token else []
        result = CliRunner().invoke(
            main, argv + (args if args is not None else ["pr", "update-plan", "7", "-R", "o/r"])
        )
        assert next(expected, None) is None
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        assert TOKEN not in result.output
        return result

    return run


@pytest.mark.parametrize(
    ("merge_base", "relationship"),
    [(BASE, "head-includes-base"), (HEAD, "head-is-ancestor-of-base"), (COMMON, "diverged")],
)
def test_compare_exact_shas_in_both_orders_and_read_back_pr(invoke, merge_base, relationship):
    result = invoke(
        (DETAIL, PR), (FORWARD, compare(BASE, merge_base)), (REVERSE, compare(HEAD, merge_base)), (DETAIL, PR)
    )
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "Read-only GitCode PR snapshot: o/r#7",
        f"Head SHA: {HEAD}",
        f"Base SHA: {BASE}",
        f"Merge base SHA: {merge_base}",
        f"Relationship: {relationship}",
        "This compares recorded commits, not live branch tips or merge readiness. "
        "This command did not update any branch.",
    ]


def test_same_commit_uses_only_two_pr_identity_reads(invoke):
    snapshot = {**PR, "head": {**PR["head"], "sha": BASE.upper()}}
    result = invoke(
        (DETAIL, snapshot),
        (DETAIL, snapshot),
        args=["-R", "o/r", "pr", "update-plan", "7"],
        token="",
    )
    assert result.exit_code == 0 and "Relationship: same-commit" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["pr", "update-plan", "7"],
        ["pr", "update-plan", "7", "-R", ""],
        ["pr", "update-plan", "feature/build", "-R", "o/r"],
        ["pr", "update-plan", "https://gitcode.com/o/r/pulls/7", "-R", "o/r"],
        ["pr", "update-plan", "0", "-R", "o/r"],
        ["pr", "update-plan", str(2**31), "-R", "o/r"],
        ["pr", "update-plan", "7", "-R", "github.com/o/r"],
        ["pr", "update-plan", "7", "-R", "o/%72"],
        ["-R", "fork/r", "pr", "update-plan", "7", "-R", "o/r"],
        ["pr", "update-plan", "7", "-R", "o/r", "--rebase"],
    ],
)
def test_scope_is_explicit_and_never_guesses(invoke, args):
    result = invoke(args=args)
    assert result.exit_code != 0 and "Relationship:" not in result.output


@pytest.mark.parametrize(
    "path,value",
    [
        (("id",), True),
        (("number",), 8),
        (("state",), "merged"),
        (("html_url",), {"malformed": True}),
        (("html_url",), "https://gitcode.com/o/other/pulls/7"),
        (("url",), f"https://wrong.example{DETAIL}"),
        (("url",), API_URL[:-1] + "8"),
        (("url",), API_URL.replace("/o/r/", "/other/r/")),
        (("url",), API_URL + "?access_token=" + TOKEN),
        (("url",), {"url": API_URL}),
        (("url",), None),
        (("head", "repo"), {"path": "r", "name": "r"}),
        (("head", "repo"), {"full_name": "fork/r"}),
        (("base", "repo", "namespace", "path"), "fork"),
        (("base", "repo", "namespace", "full_path"), "fork"),
        (("base", "repo", "namespace", "html_url"), "https://gitcode.com/fork"),
        (("base", "repo", "namespace"), {"full_path": "fork"}),
        (("base", "repo", "namespace"), {"full_name": "o"}),
        (("base", "repo", "namespace"), None),
        (("base", "repo", "namespace", "id"), False),
        (("base", "repo", "full_path"), "wrong/r"),
        (("base", "repo", "path_with_namespace"), "wrong/r"),
        (("base", "repo", "url"), "https://api.gitcode.com/api/v5/repos/o/wrong"),
        (("base", "repo", "id"), 0),
        (("base", "repo", "id"), "91"),
        (("base", "repo", "id"), True),
        (("base", "repo", "id"), None),
        (("base", "repo", "html_url"), "https://gitcode.com/o/other"),
        (("head", "sha"), HEAD[:12]),
        (("head", "sha"), "0" * 40),
        (("head", "ref"), "-bad"),
        (("head", "ref"), "x" * 1025),
        (("head", "ref"), "main"),
    ],
)
def test_refuses_unverified_pr_before_comparing(invoke, path, value):
    snapshot = copy.deepcopy(PR)
    field = snapshot
    for component in path[:-1]:
        field = field[component]
    field[path[-1]] = value
    result = invoke((DETAIL, snapshot))
    assert result.exit_code != 0 and "Relationship:" not in result.output


def test_does_not_infer_same_repository_from_bare_paths_in_official_example(invoke):
    source = (
        Path(__file__).parents[1]
        / "fixtures/gitcode-api-contracts/raw/Pull Requests/get-api-v-5-repos-owner-repo-pulls-number.json"
    )
    sample = json.loads(source.read_text(encoding="utf-8"))["responseExample"]
    snapshot = {**sample, "state": "open", "number": 7, "html_url": PR["html_url"], "url": API_URL}
    result = invoke((DETAIL, snapshot))
    assert result.exit_code != 0 and "exact same selected repository" in result.output


def _snapshot_with_ids():
    snapshot = copy.deepcopy(PR)
    for side in ("head", "base"):
        snapshot[side]["repo"].update(
            {
                "id": 91,
                "path": "r",
                "full_path": "o/r",
                "path_with_namespace": "o/r",
                "url": "https://api.gitcode.com/api/v5/repos/o/r",
                "namespace": {"id": 81, "full_path": "o", "full_name": "Display Name"},
            }
        )
    return snapshot


@pytest.mark.parametrize("url", [None, API_URL, f"https://gitcode.com{DETAIL}"])
def test_accepts_consistent_ids_full_namespace_path_and_official_url_aliases(invoke, url):
    snapshot = _snapshot_with_ids()
    if url is None:
        snapshot.pop("url")
    else:
        snapshot["url"] = url
    result = invoke(
        (DETAIL, snapshot),
        (FORWARD, compare(BASE, HEAD)),
        (REVERSE, compare(HEAD, HEAD)),
        (DETAIL, snapshot),
    )
    assert result.exit_code == 0 and "Relationship: head-is-ancestor-of-base" in result.output


@pytest.mark.parametrize("project_field", ["repo", "namespace"])
def test_refuses_head_and_base_with_conflicting_immutable_ids(invoke, project_field):
    snapshot = _snapshot_with_ids()
    changed = snapshot["head"]["repo"]
    if project_field == "namespace":
        changed = changed["namespace"]
    changed["id"] = 100
    result = invoke((DETAIL, snapshot))
    assert result.exit_code != 0 and "contradictory repository or namespace IDs" in result.output


@pytest.mark.parametrize("event", ["repository-replaced", "namespace-replaced", "id-disappeared", "id-appeared"])
def test_revalidates_immutable_repository_and_namespace_ids_on_final_read(invoke, event):
    snapshot = _snapshot_with_ids()
    changed = copy.deepcopy(snapshot)
    for side in ("head", "base"):
        if event == "repository-replaced":
            changed[side]["repo"]["id"] = 200
        elif event == "namespace-replaced":
            changed[side]["repo"]["namespace"]["id"] = 200
        elif event == "id-disappeared":
            changed[side]["repo"].pop("id")
        else:
            snapshot[side]["repo"].pop("id")
    result = invoke(
        (DETAIL, snapshot),
        (FORWARD, compare(BASE, COMMON)),
        (REVERSE, compare(HEAD, COMMON)),
        (DETAIL, changed),
    )
    assert result.exit_code != 0 and "identity, refs or SHAs changed" in result.output
    assert "Relationship:" not in result.output


@pytest.mark.parametrize(
    "bad",
    [
        {"truncated": 1},
        {"truncated": False},
        {"truncated": None},
        {"commits": None},
        {"files": None},
        {"base_commit": {"sha": HEAD}},
        {"merge_base_commit": {"sha": "unknown"}},
        {"merge_base_commit": None},
    ],
)
def test_refuses_truncated_or_unverified_first_comparison(invoke, bad):
    result = invoke((DETAIL, PR), (FORWARD, compare(BASE, COMMON, **bad)))
    assert result.exit_code != 0 and "Relationship:" not in result.output


def test_refuses_inconsistent_reverse_merge_base(invoke):
    result = invoke((DETAIL, PR), (FORWARD, compare(BASE, COMMON)), (REVERSE, compare(HEAD, HEAD)))
    assert result.exit_code != 0 and "disagree" in result.output and "Relationship:" not in result.output


def test_refuses_wrong_echo_in_reverse_comparison(invoke):
    result = invoke((DETAIL, PR), (FORWARD, compare(BASE, COMMON)), (REVERSE, compare(BASE, COMMON)))
    assert result.exit_code != 0 and "did not confirm" in result.output and "Relationship:" not in result.output


@pytest.mark.parametrize(
    "changed",
    [
        {**PR, "head": {**PR["head"], "sha": COMMON}},
        {**PR, "base": {**PR["base"], "ref": "other-branch"}},
        {**PR, "id": 108},
        {**PR, "state": "closed"},
    ],
)
def test_refuses_changed_pr_on_final_read(invoke, changed):
    result = invoke((DETAIL, PR), (FORWARD, compare(BASE, COMMON)), (REVERSE, compare(HEAD, COMMON)), (DETAIL, changed))
    assert result.exit_code != 0 and "Relationship:" not in result.output


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(302, headers={"Location": "https://unexpected.invalid/path"}), "HTTP 302"),
        (httpx.Response(403, json={"message": TOKEN}), "HTTP 403"),
        (httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1)), "2 MiB limit"),
        (httpx.Response(200, content=b'{"truncated": 1, "truncated": 0}'), "Invalid"),
        (
            httpx.Response(200, content=json.dumps(compare(BASE, COMMON)), headers={"Content-Encoding": "identity, x"}),
            "compressed",
        ),
    ],
)
def test_compare_uses_same_bounded_transport(invoke, response, error):
    result = invoke((DETAIL, PR), (FORWARD, response))
    assert result.exit_code != 0 and error in result.output and "Relationship:" not in result.output


@pytest.mark.parametrize("subcommand", ["update-plan", "update-branch"])
def test_proxy_refuses_without_dispatching(monkeypatch, subcommand):
    monkeypatch.setattr("gitcode_cli.gh_proxy.find_real_gh", lambda _: pytest.fail("must not fall back to native gh"))
    monkeypatch.setattr("gitcode_cli.gh_proxy._exec", lambda *_: pytest.fail("neither backend may run"))
    with pytest.raises(ProxyError, match="refusing to fall back"):
        dispatch(["pr", subcommand, "7"], {"GC_GH_TARGET": "gitcode"})
