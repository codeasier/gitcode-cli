"""Offline contracts through the actual Click command; never query a live repository."""

import json
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.compat import CompatStatus, iter_entries
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command

TOKEN = "synthetic-related-pat"
ARGS = ["issue", "related-prs", "21", "-R", "TEAM/project"]
URL = "https://api.gitcode.com/api/v5/repos/TEAM/project/issues/21/pull_requests"


def row(number=3, pr_id=91):
    return {
        "id": pr_id,
        "number": number,
        "html_url": f"https://gitcode.com/team/project/merge_requests/{number}",
        "diff_url": f"https://gitcode.com/team/project/merge_requests/{number}/diffs",
        "url": f"https://api.gitcode.com/api/v5/repos/Team/project/pulls/{number}",
        "base": {
            "repo": {"full_name": "Team/project", "path": "project", "html_url": "https://gitcode.com/team/project.git"}
        },
        "head": {"repo": {"full_name": "different/fork"}},
        "assignees": [{"login": "do-not-print"}],
        "body": "do-not-print " + TOKEN,
        "can_merge_check": True,  # Deliberately does not indicate closure.
    }


@pytest.fixture
def invoke(tmp_config_dir, monkeypatch):
    monkeypatch.delenv("GC_TOKEN", raising=False)
    cls = httpx.Client
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))

    def run(responder=None, *, args=None, secret=TOKEN, expected_token=TOKEN, url=URL):
        calls = []

        def respond(request):
            calls.append(request)
            assert len(calls) == 1 and responder is not None, "unexpected GET/retry"
            assert request.url == httpx.URL(url) and not request.url.query
            assert request.method == "GET" and not request.content
            assert request.headers.get("authorization") == (f"Bearer {expected_token}" if expected_token else None)
            assert "private-token" not in request.headers and "cookie" not in request.headers
            assert request.headers["accept"] == "application/json"
            assert request.headers["accept-encoding"] == "identity"
            return responder(request)

        def make_client(**kwargs):
            assert kwargs.get("trust_env") is False and kwargs.get("follow_redirects") is False
            return cls(**kwargs, cookies={"do-not-forward": "poison"}, transport=httpx.MockTransport(respond))

        monkeypatch.setattr("gitcode_cli.repo_read.httpx.Client", make_client)
        result = runner.invoke(
            main, [*(["--token", secret] if secret is not None else []), *(ARGS if args is None else args)]
        )
        if result.exception is not None and not isinstance(result.exception, SystemExit):
            raise result.exception
        assert len(calls) == (responder is not None)
        assert TOKEN not in result.stdout + result.stderr
        assert "do-not-print" not in result.stdout + result.stderr
        return result

    return run


def payload(data, *, status=200, headers=None):
    return lambda _: httpx.Response(status, json=data, headers=headers)


def fail(result):
    assert result.exit_code != 0 and not result.stdout and result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("selection", ["global", "command", "both"])
def test_minimal_ordered_projection_not_closing_or_fork_filtered(invoke, selection):
    opts = ["-R", "TEAM/project"]
    args = [
        *(opts if selection != "command" else []),
        "issue",
        "related-prs",
        "21",
        *(opts if selection != "global" else []),
    ]
    result = invoke(payload([row(7, 109), row(2, 88)], headers={"x-total": "2", "x-total-pages": "1"}), args=args)
    assert result.exit_code == 0 and not result.stderr
    assert json.loads(result.stdout) == [
        {"id": 109, "number": 7, "repository": "Team/project"},
        {"id": 88, "number": 2, "repository": "Team/project"},
    ]


def test_anonymous_or_saved_token_without_new_credential_sources(invoke, tmp_config_dir, monkeypatch):
    monkeypatch.setenv("GITCODE_TOKEN", "not-a-credential-source")
    result = invoke(payload([]), secret=None, expected_token=None)
    assert result.exit_code == 0 and result.stdout == "[]\n" and not result.stderr
    (tmp_config_dir / "config.json").write_text(json.dumps({"token": TOKEN}))
    assert invoke(payload([]), secret=None).exit_code == 0


@pytest.mark.parametrize("config", ['{"active_account":null,"accounts":{"user":"saved-token"}}', "{bad"])
def test_ambiguous_saved_identity_never_falls_back_to_anonymous(invoke, tmp_config_dir, config):
    (tmp_config_dir / "config.json").write_text(config)
    fail(invoke(secret=None))


@pytest.mark.parametrize("value", ["", "0", "01", "-1", "２１", "9" * 21, "a/b", "https://gitcode.com/t/r/issues/21"])
def test_target_is_literal_issue_number(invoke, value):
    fail(invoke(args=["issue", "related-prs", "--repo", "TEAM/project", "--", value]))


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["-R", ""],
        ["-R", "TEAM/../project"],
        ["-R", "github.com/TEAM/project"],
        ["-R", "T@host/project"],
        ["-R", f"TEAM/{TOKEN}"],
    ],
)
def test_target_must_be_explicit_and_safe(invoke, options):
    fail(invoke(args=["issue", "related-prs", "21", *options]))


def test_conflicting_global_local_repositories_or_malformed_auth_no_network(invoke):
    fail(invoke(args=["-R", "foreign/repo", *ARGS]))
    fail(invoke(secret="bad token\n"))


@pytest.mark.parametrize(
    "field,invalid",
    [
        ("id", True),
        ("id", "91"),
        ("id", 0),
        ("id", -1),
        ("number", False),
        ("number", 2.5),
        ("number", 10**20),
        ("html_url", None),
        ("html_url", "https://gitcode.com/team/project/merge_requests/4"),
        ("html_url", "https://gitcode.com/team/Project/merge_requests/3"),
        ("html_url", "https://gitcode.com.foreign.invalid/team/project/merge_requests/3"),
        ("html_url", "https://user@gitcode.com/team/project/merge_requests/3"),
        ("html_url", "https://gitcode.com/team/project/merge_requests/3?access_token=do-not-print"),
        ("html_url", "https://gitcode.com/team/project/merge_requests/3#frag"),
        ("html_url", "https://gitcode.com/team/%70roject/merge_requests/3"),
        ("url", "https://api.gitcode.com/api/v5/repos/Team/project/pulls/4"),
        ("diff_url", "https://gitcode.com/other/project/merge_requests/3/diffs"),
        ("base", {}),
        ("base", {"repo": {"path": "project"}}),
        ("base", {"repo": {"full_name": "other/project"}}),
        ("base", {"repo": {"full_name": "Team/project", "path": "other"}}),
        ("base", {"repo": {"full_name": "Team/project", "full_path": "Other/project"}}),
        ("base", {"repo": {"full_name": "Team/project", "namespace": {"path": "other"}}}),
        ("base", {"repo": {"full_name": "Team/project", "html_url": "https://gitcode.com/t/p.git"}}),
    ],
)
def test_rejects_whole_list_if_later_row_cannot_be_proven(invoke, field, invalid):
    fail(invoke(payload([row(10, 1), {**row(), field: invalid}])))


@pytest.mark.parametrize(
    "rows",
    [
        [row(), row()],
        [row(), row(3, 20)],
        [row(), row(9, 91)],
        {},
        {"items": [], "total_count": 0},
        [None],
        list(range(101)),
    ],
)
def test_duplicate_row_identity_bad_envelope_and_row_limit(invoke, rows):
    fail(invoke(payload(rows)))


def test_exactly_100_accepted_without_claiming_completeness(invoke):
    many = [row(i, 500 + i) for i in range(1, 101)]
    assert len(json.loads(invoke(payload(many)).stdout)) == 100


@pytest.mark.parametrize(
    "headers",
    [
        {"link": "<https://foreign.invalid/do-not-print>; rel=next"},
        {"content-range": "items 0-0/2"},
        {"x-page": "2"},
        {"x-next-page": "2"},
        {"x-prev-page": "1"},
        {"x-total": "3"},
        {"x-total-count": "0"},
        {"x-total-pages": "0"},
        {"x-truncated": "true"},
        {"x-has-more": "1"},
        {"x-incomplete-results": "true"},
        {"x-per-page": "0"},
        [("x-total", "1"), ("x-total", "1")],
    ],
)
def test_no_partial_pages_or_ambiguous_metadata(invoke, headers):
    fail(invoke(payload([row()], headers=headers)))


@pytest.mark.parametrize("status", [201, 204, 206, 302, 307, 401, 403, 404, 429, 500])
def test_only_200_never_retries_or_follows_redirect(invoke, status):
    fail(
        invoke(
            payload(
                {"error": "do-not-print"}, status=status, headers={"location": "https://foreign.invalid/do-not-print"}
            )
        )
    )


@pytest.mark.parametrize(
    "raw,headers",
    [
        (b"[]", {"content-type": "text/html"}),
        (b"[]", {"content-type": "application/json; charset=iso-8859-1"}),
        (b"not-json", {}),
        (b'["\xff"]', {}),
        (b'[{"id":1,"id":2}]', {}),
        (b"[NaN]", {}),
        (b" " * (2 * 1024 * 1024) + b"[]", {}),
        (b"[]", {"content-encoding": "unexpected"}),
    ],
)
def test_strict_transport_and_bounded_bytes(invoke, raw, headers):
    fail(invoke(lambda _: httpx.Response(200, content=raw, headers={"content-type": "application/json", **headers})))


def test_sanitized_transport_failure_and_output_token_echo(invoke):
    def broken(request):
        raise httpx.ReadError("do-not-print " + TOKEN)

    fail(invoke(broken))
    fail(invoke(payload([row(18, 97359133)]), secret="97359133", expected_token="97359133"))


def test_group_discovery_native_only_no_gh_proxy_routing(invoke):
    group = invoke(args=["issue", "--help"])
    help_text = invoke(args=["issue", "related-prs", "--help"])
    assert "related-prs" in group.stdout and "Associations do not imply" in help_text.stdout
    (entry,) = (item for item in iter_entries(groups=["issue"]) if item.command == "issue related-prs")
    assert entry.flag is None and entry.status is CompatStatus.IMPLEMENTED and entry.gc_extension
    assert not entry.proxy_allowed
    with pytest.raises(ProxyError, match="use gc issue related-prs directly"):
        validate_gitcode_command(["issue", "related-prs", "21", "-R", "TEAM/project"])
    rendered = invoke(args=["compat", "report", "--stdout"])
    assert rendered.exit_code == 0 and not rendered.stderr
    assert (
        "GitCode-only: bounded single-response PR associations, not closing relationships. (direct gc only)"
        in rendered.stdout
    )


def test_legacy_issue_view_number_never_calls_related_prs(invoke, monkeypatch):
    from unittest.mock import Mock

    client = Mock()
    client.get.return_value = {"number": "21", "state": "open"}
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda _: client)
    result = invoke(args=["issue", "view", "21", "-R", "TEAM/project", "--json", "number"])
    assert result.exit_code == 0 and json.loads(result.stdout) == {"number": 21}
    client.get.assert_called_once_with("/repos/TEAM/project/issues/21")


def _base_id(entry, value):
    entry["base"]["repo"]["id"] = value
    return entry


@pytest.mark.parametrize("case", ["multiple-base-ids", "mismatched-iid", "mismatched-target-project-id"])
def test_related_optional_identity_contradiction_is_atomic(invoke, case):
    first = _base_id(row(7, 107), 33)
    second = _base_id(row(1, 101), 33)
    if case == "multiple-base-ids":
        second["base"]["repo"].update(id=44, full_name="TEAM/project")
    elif case == "mismatched-iid":
        second.update(iid=11)
    else:
        second.update(target_project_id=44)
    fail(invoke(payload([first, second])))


@pytest.mark.parametrize("key", ["base.repo.id", "iid", "target_project_id", "project_id"])
@pytest.mark.parametrize("invalid", [None, True, False, "33", 33.0, 0, -1, 10**20])
def test_present_optional_ids_must_be_bounded_positive_json_integers(invoke, key, invalid):
    item = _base_id(row(33), 33)
    if key == "base.repo.id":
        _base_id(item, invalid)
    else:
        item[key] = invalid
    fail(invoke(payload([item])))


def test_base_identity_is_independent_of_fork_and_omitted_fields(invoke):
    first = _base_id(row(5, 123), 33)
    first.update(iid=5, target_project_id=33, project_id=33, source_project_id=44)
    first["head"]["repo"]["id"] = 44
    third = _base_id(row(4, 125), 33)
    third["base"]["repo"]["full_name"] = "TEAM/project"
    fourth = {**row(3, 126), "target_project_id": 33, "project_id": 33}
    result = invoke(payload([first, row(2, 124), third, fourth]))
    assert result.exit_code == 0 and not result.stderr
    assert json.loads(result.stdout) == [
        {"id": 123, "number": 5, "repository": "Team/project"},
        {"id": 124, "number": 2, "repository": "Team/project"},
        {"id": 125, "number": 4, "repository": "TEAM/project"},
        {"id": 126, "number": 3, "repository": "Team/project"},
    ]


def test_omission_cannot_erase_a_contradicted_explicit_id(invoke):
    fail(invoke(payload([_base_id(row(1, 101), 33), row(2, 102), {**row(3, 103), "target_project_id": 44}])))


@pytest.mark.parametrize(
    "claim,expected_ok",
    [
        ({"project_id": 33}, False),
        ({"target_project_id": 33}, True),
        ({"target_project_id": 33, "project_id": 33}, True),
        ({"target_project_id": 33, "project_id": 44}, False),
    ],
)
def test_unqualified_project_id_needs_explicit_base_identity(invoke, claim, expected_ok):
    result = invoke(payload([{**row(), **claim}]))
    if expected_ok:
        assert result.exit_code == 0 and json.loads(result.stdout) == [
            {"id": 91, "number": 3, "repository": "Team/project"}
        ]
    else:
        fail(result)
