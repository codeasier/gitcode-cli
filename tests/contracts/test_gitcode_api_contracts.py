from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gitcode_cli.adapters import IssueAdapter, PullRequestAdapter
from gitcode_cli.services.issues import IssueService
from gitcode_cli.services.pulls import PullRequestService

RAW_DOCS_RELATIVE_PATH = Path("tests/fixtures/gitcode-api-contracts/raw")


def _find_raw_docs_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / RAW_DOCS_RELATIVE_PATH
        if candidate.exists():
            return candidate
    pytest.fail(f"Could not locate extracted GitCode API docs under {RAW_DOCS_RELATIVE_PATH}")


def _load_contract(*parts: str) -> dict:
    contract_path = _find_raw_docs_root().joinpath(*parts)
    return json.loads(contract_path.read_text(encoding="utf-8"))


def _contract_path(contract: dict, **path_params: str | int) -> str:
    return contract["path"].format(**path_params).removeprefix("/api/v5")


def _validate_body(contract: dict, body: dict) -> None:
    types = {"string": str, "boolean": bool, "integer": int}
    for field in contract["requestBodyFields"]:
        name = field["name"]
        if field.get("required"):
            assert name in body, f"Required field missing: {name}"
        if name in body and field["type"] in types:
            assert type(body[name]) is types[field["type"]], f"Wrong type: {name}"
            if "enum" in field:
                assert body[name] in field["enum"], f"Wrong enum: {name}"


@pytest.fixture
def issue_service() -> tuple[IssueService, MagicMock]:
    client = MagicMock()
    return IssueService(client), client


@pytest.fixture
def pull_service() -> tuple[PullRequestService, MagicMock]:
    client = MagicMock()
    client.get.return_value = []
    return PullRequestService(client), client


class TestIssueServiceContracts:
    @pytest.mark.parametrize("action", ["close", "reopen", "edit"])
    def test_partial_updates_preserve_required_title(self, issue_service, action):
        service, client = issue_service
        client.get.return_value = {"title": "Keep this title", "state": "open" if action == "close" else "closed"}
        adapter = IssueAdapter(service)
        if action == "close":
            adapter.close_issue("owner", "repo", "1", comment=None, reason=None)
        elif action == "reopen":
            adapter.reopen_issue("owner", "repo", "1")
        else:
            adapter.edit_issue(
                "owner",
                "repo",
                "1",
                title=None,
                body="new body",
                add_assignee=None,
                add_labels=None,
                remove_assignee=None,
                remove_labels=None,
                milestone=None,
                remove_milestone=False,
            )
        body = client.patch.call_args.kwargs["json"]
        assert body["title"] == "Keep this title"
        _validate_body(_load_contract("Issues", "patch-api-v-5-repos-owner-issues-number.json"), body)

    def test_list_matches_issue_list_contract(self, issue_service: tuple[IssueService, MagicMock]) -> None:
        service, client = issue_service
        contract = _load_contract("Issues", "get-api-v-5-repos-owner-repo-issues.json")

        service.list("owner", "repo", state="open", per_page=10)

        client.get.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo"),
            params={"state": "open", "per_page": 10},
        )
        assert contract["method"] == "GET"

    def test_get_matches_issue_get_contract(self, issue_service: tuple[IssueService, MagicMock]) -> None:
        service, client = issue_service
        contract = _load_contract("Issues", "get-api-v-5-repos-owner-repo-issues-number.json")

        service.get("owner", "repo", "42")

        client.get.assert_called_once_with(_contract_path(contract, owner="owner", repo="repo", number="42"))
        assert contract["method"] == "GET"

    def test_list_comments_matches_issue_comment_list_contract(
        self, issue_service: tuple[IssueService, MagicMock]
    ) -> None:
        service, client = issue_service
        contract = _load_contract("Issues", "get-api-v-5-repos-owner-repo-issues-number-comments.json")

        service.list_comments("owner", "repo", "42")

        client.get.assert_called_once_with(_contract_path(contract, owner="owner", repo="repo", number="42"))
        assert contract["method"] == "GET"

    def test_create_matches_issue_create_contract(self, issue_service: tuple[IssueService, MagicMock]) -> None:
        service, client = issue_service
        contract = _load_contract("Issues", "post-api-v-5-repos-owner-issues.json")

        service.create("owner", "repo", title="Bug", body="Broken", assignee=None, labels="bug")

        client.post.assert_called_once_with(
            _contract_path(contract, owner="owner"),
            json={"repo": "repo", "title": "Bug", "body": "Broken", "labels": "bug"},
        )
        assert contract["method"] == "POST"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert {"repo", "title", "body", "labels"}.issubset(request_fields)

    def test_update_matches_issue_update_contract(self, issue_service: tuple[IssueService, MagicMock]) -> None:
        service, client = issue_service
        contract = _load_contract("Issues", "patch-api-v-5-repos-owner-issues-number.json")

        service.update(
            "owner",
            "repo",
            "42",
            title="Updated",
            state="close",
            state_reason="completed",
            milestone=None,
        )

        client.patch.assert_called_once_with(
            _contract_path(contract, owner="owner", number="42"),
            json={"repo": "repo", "title": "Updated", "state": "close", "state_reason": "completed"},
        )
        assert contract["method"] == "PATCH"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert {"repo", "title", "state"}.issubset(request_fields)

    def test_comment_matches_issue_comment_create_contract(self, issue_service: tuple[IssueService, MagicMock]) -> None:
        service, client = issue_service
        contract = _load_contract("Issues", "post-api-v-5-repos-owner-repo-issues-number-comments.json")

        service.comment("owner", "repo", "42", "Nice issue")

        client.post.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo", number="42"),
            json={"body": "Nice issue"},
        )
        assert contract["method"] == "POST"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert "body" in request_fields

    def test_update_comment_matches_issue_comment_update_contract(
        self, issue_service: tuple[IssueService, MagicMock]
    ) -> None:
        service, client = issue_service

        service.update_comment("owner", "repo", "7", "Updated body")

        client.patch.assert_called_once_with(
            "/repos/owner/repo/issues/comments/7",
            json={"body": "Updated body"},
        )

    def test_delete_comment_matches_issue_comment_delete_contract(
        self, issue_service: tuple[IssueService, MagicMock]
    ) -> None:
        service, client = issue_service

        service.delete_comment("owner", "repo", "7")

        client.delete.assert_called_once_with(
            "/repos/owner/repo/issues/comments/7",
        )


class TestPullRequestServiceContracts:
    def test_list_matches_pr_list_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "get-api-v-5-repos-owner-repo-pulls.json")

        service.list("owner", "repo", state="open")

        client.get.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo"), params={"state": "open"}
        )
        assert contract["method"] == "GET"

    def test_get_matches_pr_get_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "get-api-v-5-repos-owner-repo-pulls-number.json")

        service.get("owner", "repo", 42)

        client.get.assert_called_once_with(_contract_path(contract, owner="owner", repo="repo", number=42))
        assert contract["method"] == "GET"

    def test_create_matches_pr_create_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "post-api-v-5-repos-owner-repo-pulls.json")

        service.create("owner", "repo", title="Feature", head="feature", base="main", body=None, labels="bug")

        client.post.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo"),
            json={"title": "Feature", "head": "feature", "base": "main", "labels": "bug"},
        )
        assert contract["method"] == "POST"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert {"title", "head", "base", "labels"}.issubset(request_fields)

    def test_update_matches_pr_update_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "patch-api-v-5-repos-owner-repo-pulls-number.json")

        service.update("owner", "repo", 42, title="Updated", state="closed", reviewer=None)

        client.patch.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo", number=42),
            json={"title": "Updated", "state": "closed"},
        )
        assert contract["method"] == "PATCH"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert {"title", "state"}.issubset(request_fields)

    def test_merge_matches_pr_merge_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "put-api-v-5-repos-owner-repo-pulls-number-merge.json")

        service.merge("owner", "repo", 42, merge_method="merge", squash=True)

        client.put.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo", number=42),
            json={"merge_method": "merge", "squash": True},
        )
        assert contract["method"] == "PUT"
        _validate_body(contract, client.put.call_args.kwargs["json"])

    @pytest.mark.parametrize("method", ["merge", "squash", "rebase"])
    def test_adapter_merge_body_matches_types_and_enum(self, pull_service, method):
        service, client = pull_service
        client.put.return_value = {"merged": True}
        PullRequestAdapter(service).merge_pr("o", "r", 1, merge_method=method, body=None, subject=None, admin=False)
        body = client.put.call_args.kwargs["json"]
        _validate_body(_load_contract("Pull Requests", "put-api-v-5-repos-owner-repo-pulls-number-merge.json"), body)
        assert body.get("squash", False) is (method == "squash")

    def test_comment_matches_pr_comment_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "post-api-v-5-repos-owner-repo-pulls-number-comments.json")

        service.comment("owner", "repo", 42, "Fix this", path="main.py", position=7)

        client.post.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo", number=42),
            json={"body": "Fix this", "path": "main.py", "position": 7},
        )
        assert contract["method"] == "POST"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert {"body", "path", "position"}.issubset(request_fields)

    def test_review_matches_pr_review_contract(self, pull_service: tuple[PullRequestService, MagicMock]) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "post-api-v-5-repos-owner-repo-pulls-number-review.json")

        service.review("owner", "repo", 42, body=None, force=True)

        client.post.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo", number=42),
            json={"force": True},
        )
        assert contract["method"] == "POST"
        request_fields = {field["name"] for field in contract["requestBodyFields"]}
        assert "force" in request_fields

    def test_list_comments_matches_pr_comment_list_contract(
        self, pull_service: tuple[PullRequestService, MagicMock]
    ) -> None:
        service, client = pull_service
        contract = _load_contract("Pull Requests", "get-api-v-5-repos-owner-repo-pulls-number-comments.json")

        service.list_comments("owner", "repo", 42)

        client.get.assert_called_once_with(
            _contract_path(contract, owner="owner", repo="repo", number=42),
            params={"page": 1, "per_page": 100},
        )
        assert contract["method"] == "GET"
        query_fields = {field["name"] for field in contract["queryParams"]}
        assert {"page", "per_page"}.issubset(query_fields)
