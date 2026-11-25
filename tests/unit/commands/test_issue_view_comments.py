"""The public CLI must not confuse an issue's comment count with comment objects."""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main

PATH = "/api/v5/repos/owner/repo/issues/42"
DETAIL = {"id": 312, "number": 42, "html_url": "https://gitcode.com/owner/repo/issues/42", "comments": 0}
ARGS = ["issue", "view", "42", "-R", "owner/repo", "--json", "number, comments"]
SECRET = "fixture-only-token"


def row(cid):
    return {
        "id": cid,
        "body": f"body-{cid}",
        "user": {"login": "alice", "name": "A"},
        "target": {"issue": {"id": 312, "nubmer": 42}},
        "created_at": "2026-04-30T12:06:04Z",
    }


@pytest.fixture
def invoke(monkeypatch, tmp_config_dir):
    monkeypatch.delenv("GC_TOKEN", raising=False)

    def run(pages, *, detail=None, args=ARGS, token=SECRET, detail_path=PATH):
        calls = []

        def send(self, request, **kwargs):
            assert request.method == "GET" and request.url.host == "api.gitcode.com"
            assert "access_token" not in request.url.params and "private-token" not in request.headers
            assert SECRET not in str(request.url)
            assert request.headers.get("Authorization") == (f"Bearer {token}" if token else None)
            calls.append(request)
            if request.url.path == detail_path:
                assert len(calls) == 1 and not request.url.params
                return httpx.Response(200, json=detail if detail is not None else DETAIL, request=request)
            assert request.url.path == PATH + "/comments"
            assert request.url.params == httpx.QueryParams(page=len(calls) - 1, per_page=50)
            data = pages[len(calls) - 2]
            if type(data) is int:
                return httpx.Response(data, request=request)
            if isinstance(data, tuple):
                data, headers = data
            else:
                headers = {}
            return httpx.Response(200, json=data, headers=headers, request=request)

        monkeypatch.setattr(httpx.Client, "send", send)
        result = CliRunner().invoke(main, (["--token", token] if token else []) + args)
        return result, calls

    return run


@pytest.mark.parametrize("comments_flag", [[], ["--comments"]])
def test_fetches_rows_instead_of_detail_counter(invoke, comments_flag):
    result, calls = invoke([[row(1)], [row(2)], []], args=ARGS + comments_flag)
    assert result.exit_code == 0, (result.output, result.exception)
    assert len(calls) == 4
    data = json.loads(result.output)
    assert data["number"] == 42
    assert [r["id"] for r in data["comments"]] == [1, 2]
    assert data["comments"][0]["body"] == "body-1"
    assert data["comments"][0]["author"]["login"] == "alice"
    assert data["comments"][0]["createdAt"] == "2026-04-30T12:06:04Z"
    assert "viewerDidAuthor" not in data["comments"][0]


def test_empty_is_an_array_after_anonymous_scoped_get(invoke):
    result, calls = invoke([[]], token="")
    assert result.exit_code == 0 and json.loads(result.output)["comments"] == []
    assert len(calls) == 2


@pytest.mark.parametrize(
    "bad_page",
    [
        [row(1)],
        [dict(row(2), target={"issue": {"id": 313, "number": 42}})],
        [dict(row(2), target={"issue": {"id": 312, "number": 42, "nubmer": 43}})],
        [dict(row(2), id=True)],
        [dict(row(2), body=None)],
        [dict(row(2), target={})],
        ([row(2)], {"X-Truncated": "true"}),
        ([], {"X-Next-Page": "3"}),
        403,
        None,
    ],
)
def test_late_bad_data_never_emits_partial_rows(invoke, bad_page):
    result, calls = invoke([[row(1)], bad_page])
    assert result.exit_code == 1 and "body-1" not in result.output and SECRET not in result.output
    assert len(calls) == 3


def test_next_page_link_is_validated_not_followed(invoke):
    result, calls = invoke([([row(1)], {"Link": '<https://other.invalid/next>; rel="next"'})])
    assert result.exit_code == 1 and len(calls) == 2 and "body-1" not in result.output


def test_probe_limit_counts_and_suppresses_all_data(invoke):
    result, calls = invoke([[row(i)] for i in range(1, 12)])
    assert result.exit_code == 1 and len(calls) == 12 and "body-1" not in result.output


def test_other_issue_id_is_not_substituted(invoke):
    result, calls = invoke([], detail={**DETAIL, "number": 43})
    assert result.exit_code == 1 and len(calls) == 1 and "body-" not in result.output


def test_credential_is_not_emitted_in_comment(invoke):
    result, _ = invoke([[dict(row(1), body=SECRET)], []])
    assert SECRET not in result.output
    assert result.exit_code == 1


def test_owner_alias_uses_canonical_comment_route_and_page_links(invoke):
    detail = {**DETAIL, "repository": {"path": "repo", "full_name": "Owner / repo", "namespace": {"path": "owner"}}}
    result, calls = invoke(
        [
            ([row(1)], {"Link": f'<https://api.gitcode.com{PATH}/comments?page=2&per_page=50>; rel="next"'}),
            [row(2)],
            [],
        ],
        detail=detail,
        args=["issue", "view", "42", "-R", "Owner/repo", "--json", "comments"],
        detail_path=PATH.replace("/owner/", "/Owner/"),
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 4 and [r["id"] for r in json.loads(result.output)["comments"]] == [1, 2]


@pytest.mark.parametrize(
    "url",
    [
        DETAIL["html_url"] + "?",
        DETAIL["html_url"].replace("gitcode.com/", "api.gitcode.com/"),
        DETAIL["html_url"] + "#",
        DETAIL["html_url"] + "/",
        DETAIL["html_url"].replace("/repo/", "/Repo/"),
        DETAIL["html_url"].replace("/owner/", "/Ｏwner/"),
        DETAIL["html_url"].replace(".com/", ".com:443/"),
        DETAIL["html_url"].replace("https://", "https://user@"),
        DETAIL["html_url"].replace("/42", "/43"),
        None,
        [],
    ],
)
def test_strict_issue_identity_before_comment_lookup(invoke, url):
    result, calls = invoke([], detail={**DETAIL, "html_url": url})
    assert result.exit_code == 1 and len(calls) == 1


@pytest.mark.parametrize(
    "repository",
    [
        {"path": "Repo"},
        {"full_name": "other/repo"},
        {"path_with_namespace": "owner/Repo"},
        {"full_path": "other/repo"},
        {"namespace": {"path": "other"}},
        {"namespace": {"full_path": "Öwner"}},
        {"full_name": "Ｏwner/repo"},
        {"full_name": "/repo"},
    ],
)
def test_conflicting_advertised_repository_fails_before_comments(invoke, repository):
    result, calls = invoke([], detail={**DETAIL, "repository": repository})
    assert result.exit_code == 1 and len(calls) == 1


@pytest.mark.parametrize(
    ("options", "expected"),
    [(["--jq", ".comments | length"], "2"), (["--template", "{{.number}}"], "42")],
)
def test_selected_comments_with_existing_formatters(invoke, options, expected):
    result, calls = invoke([[row(1), row(2)], []], args=ARGS + options)
    assert result.exit_code == 0 and result.output.strip() == expected
    assert len(calls) == 3


def test_unicode_kelvin_owner_is_not_an_ascii_alias(invoke):
    result, calls = invoke([], args=["issue", "view", "42", "-R", "Kowner/repo", "--json", "comments"])
    assert result.exit_code == 1 and calls == []


def test_documented_atomgit_api_html_url_is_identity_only(invoke):
    detail = {**DETAIL, "html_url": "https://api.atomgit.com/owner/repo/issues/42"}
    result, calls = invoke([[]], detail=detail)
    assert result.exit_code == 0 and json.loads(result.output)["comments"] == []
    assert [call.url.host for call in calls] == ["api.gitcode.com", "api.gitcode.com"]
