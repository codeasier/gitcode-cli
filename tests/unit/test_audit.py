from __future__ import annotations

from unittest.mock import MagicMock

from gitcode_cli.audit import (
    AuditThresholds,
    audit_pull_request,
    evaluate_audit,
    loc_and_paths_from_files,
    loc_from_diff,
    loc_from_list_item,
    paths_from_diff,
)


def _pr(**overrides):
    data = {
        "number": 42,
        "title": "Example",
        "html_url": "https://gitcode.com/owner/repo/merge_requests/42",
        "body": "",
        "milestone": None,
        "labels": [],
        "mergeable_state": {"resolve_discussion_passed": True},
    }
    data.update(overrides)
    return data


class TestEvaluateAuditReasons:
    def test_pass_with_milestone_small_loc(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "MindStudio 26.2.0"}),
            issues=[],
            comments=[],
            loc=12,
            file_paths=[],
        )
        assert result["overall"] is True
        assert result["verdict"] == "PASS"
        assert result["reasons"] == []
        assert result["failedRules"] == []

    def test_r1_fails_without_milestone_or_linked_issues(self):
        result = evaluate_audit(pr=_pr(), issues=[], comments=[], loc=12, file_paths=[])
        assert result["r1"] is False
        assert result["failedRules"] == ["R1"]
        assert result["reasons"] == ["R1: no milestone and no officially linked issues"]
        assert result["rules"]["R1"]["reasons"] == result["reasons"]

    def test_r1_ignores_body_issue_mentions(self):
        result = evaluate_audit(
            pr=_pr(body="Fixes #481"),
            issues=[],
            comments=[],
            loc=12,
            file_paths=[],
        )
        assert result["r1"] is False
        assert "R1:" in result["reasons"][0]

    def test_r1_passes_with_official_issue(self):
        result = evaluate_audit(
            pr=_pr(),
            issues=[{"number": 481}],
            comments=[],
            loc=12,
            file_paths=[],
        )
        assert result["r1"] is True
        assert result["issues"] == ["481"]

    def test_r2_reports_unresolved_diff_comments(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}),
            issues=[],
            comments=[
                {"comment_type": "diff_comment", "resolved": False},
                {"comment_type": "diff_comment", "resolved": False},
                {"comment_type": "pr_comment", "resolved": None},
            ],
            loc=12,
            file_paths=[],
        )
        assert result["r2"] is False
        assert result["unresolved"] == 2
        assert result["reasons"] == ["R2: 2 unresolved diff_comment(s)"]

    def test_r2_does_not_treat_missing_resolved_as_unresolved(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}),
            issues=[],
            comments=[{"comment_type": "diff_comment"}],
            loc=12,
            file_paths=[],
        )
        assert result["r2"] is True
        assert result["unresolved"] == 0

    def test_r2_reports_resolve_discussion_gate(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}, mergeable_state={"resolve_discussion_passed": False}),
            issues=[],
            comments=[],
            loc=12,
            file_paths=[],
        )
        assert result["r2"] is False
        assert result["reasons"] == ["R2: mergeable_state.resolve_discussion_passed=false"]

    def test_r3_does_not_count_review_keyword_comments(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}),
            issues=[],
            comments=[{"comment_type": "pr_comment", "body": "【review】looks good"}],
            loc=190,
            file_paths=["src/main.py"],
        )
        assert result["r3"] is False
        assert result["reviewCnt"] == 0
        assert result["reasons"] == ["R3: loc 190 > 100, no diff_comment, and no test-path files"]

    def test_r3_passes_with_diff_comment_or_test_path(self):
        reviewed = evaluate_audit(
            pr=_pr(milestone={"title": "m"}),
            issues=[],
            comments=[{"comment_type": "diff_comment", "resolved": True}],
            loc=190,
            file_paths=["src/main.py"],
        )
        tested = evaluate_audit(
            pr=_pr(milestone={"title": "m"}),
            issues=[],
            comments=[],
            loc=190,
            file_paths=["tests/foo_test.py"],
        )
        assert reviewed["r3"] is True
        assert tested["r3"] is True
        assert tested["hasTest"] is True

    def test_r4_passes_when_string_label_contains_keyword(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}, labels=["评审纪要"]),
            issues=[],
            comments=[],
            loc=2104,
            file_paths=["tests/foo_test.py"],
        )
        assert result["r4"] is True
        assert result["hasMinutes"] is True

    def test_r4_reports_missing_minutes(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}),
            issues=[],
            comments=[],
            loc=2104,
            file_paths=["tests/foo_test.py"],
        )
        assert result["r4"] is False
        assert result["reasons"] == ["R4: loc 2104 > 1000, and '评审纪要' not found in body, comments, or labels"]

    def test_multiple_failed_rules_keep_ordered_reasons(self):
        result = evaluate_audit(
            pr=_pr(mergeable_state={"resolve_discussion_passed": False}),
            issues=[],
            comments=[{"comment_type": "diff_comment", "resolved": False}],
            loc=2104,
            file_paths=["src/main.py"],
        )
        assert result["failedRules"] == ["R1", "R2", "R4"]
        assert result["reasons"] == [
            "R1: no milestone and no officially linked issues",
            "R2: 1 unresolved diff_comment(s); mergeable_state.resolve_discussion_passed=false",
            "R4: loc 2104 > 1000, and '评审纪要' not found in body, comments, or labels",
        ]


class TestLocHelpers:
    def test_loc_from_list_item_requires_integer_counts(self):
        assert loc_from_list_item(None) is None
        assert loc_from_list_item({"added_lines": "1", "removed_lines": 2}) is None
        assert loc_from_list_item({"added_lines": 1, "removed_lines": 2}) == 3

    def test_loc_from_diff_skips_file_headers(self):
        diff = "diff --git a/a b/a\n--- a/a\n+++ b/a\n+added\n-removed\n context\n"
        assert loc_from_diff(diff) == 2
        assert paths_from_diff(diff) == ["diff --git a/a b/a"]

    def test_loc_and_paths_from_files_coerces_string_counts(self):
        loc, paths = loc_and_paths_from_files(
            [
                {
                    "filename": "tests/foo_test.py",
                    "additions": "3",
                    "deletions": "1",
                    "patch": {"new_path": "tests/foo_test.py"},
                }
            ]
        )
        assert loc == 4
        assert "tests/foo_test.py" in paths

    def test_loc_and_paths_from_files_skips_invalid_entries(self):
        loc, paths = loc_and_paths_from_files(["skip", {"additions": object(), "deletions": 1}])
        assert loc == 1
        assert paths == []

    def test_loc_and_paths_from_files_missing_counts_return_none(self):
        loc, paths = loc_and_paths_from_files([{"filename": "src/main.py"}])
        assert loc is None
        assert paths == ["src/main.py"]


class TestAuditPullRequest:
    def test_collects_api_data_and_returns_reasons(self):
        service = MagicMock()
        service.get.return_value = _pr(added_lines=None)
        service.list_issues.return_value = []
        service.list_comments.return_value = []
        service.list_files.return_value = [{"filename": "src/main.py", "additions": 12, "deletions": 0}]
        service.diff.return_value = ""

        result = audit_pull_request(
            service,
            "owner",
            "repo",
            42,
            listed={"number": 42, "added_lines": 12, "removed_lines": 0},
        )

        assert result["reasons"] == ["R1: no milestone and no officially linked issues"]
        assert result["hasTest"] is None
        service.list_files.assert_not_called()
        service.diff.assert_not_called()

    def test_uses_custom_minutes_keyword(self):
        service = MagicMock()
        service.get.return_value = _pr(milestone={"title": "m"}, body="reviewed-by alice")
        service.list_issues.return_value = []
        service.list_comments.return_value = []
        service.list_files.return_value = [{"filename": "tests/a_test.py", "additions": 50, "deletions": 2000}]

        result = audit_pull_request(
            service,
            "owner",
            "repo",
            42,
            listed={"added_lines": 50, "removed_lines": 2000},
            thresholds=AuditThresholds(minutes_keyword="reviewed-by"),
        )
        assert result["r4"] is True
        assert result["hasMinutes"] is True

    def test_falls_back_to_listed_fields_and_diff_when_detail_is_sparse(self):
        service = MagicMock()
        service.get.return_value = None
        service.list_issues.return_value = ["skip", {"number": 9}]
        service.list_comments.return_value = None
        service.list_files.return_value = []
        service.diff.return_value = "diff --git a/src/a.py b/src/a.py\n+one\n"

        result = audit_pull_request(
            service,
            "owner",
            "repo",
            42,
            listed={
                "number": 42,
                "title": "From list",
                "html_url": "https://example.com/42",
                "body": "评审纪要: ok",
                "milestone": {"title": "m"},
                "labels": ["docs"],
            },
        )

        assert result["title"] == "From list"
        assert result["url"] == "https://example.com/42"
        assert result["milestone"] == "m"
        assert result["issues"] == ["9"]
        assert result["loc"] == 1
        assert result["hasMinutes"] is True
        assert result["overall"] is True

    def test_uses_list_files_counts_when_list_item_has_no_loc(self):
        service = MagicMock()
        service.get.return_value = _pr(milestone={"title": "m"})
        service.list_issues.return_value = []
        service.list_comments.return_value = []
        service.list_files.return_value = [{"filename": "src/main.py", "additions": 12, "deletions": 3}]
        service.diff.return_value = ""

        result = audit_pull_request(service, "owner", "repo", 42)

        assert result["loc"] == 15
        assert result["hasTest"] is False
        service.diff.assert_not_called()

    def test_falls_back_to_diff_when_file_counts_are_missing(self):
        service = MagicMock()
        service.get.return_value = _pr(milestone={"title": "m"})
        service.list_issues.return_value = []
        service.list_comments.return_value = []
        service.list_files.return_value = [{"filename": "src/main.py"}]
        service.diff.return_value = "diff --git a/src/main.py b/src/main.py\n+one\n+two\n"

        result = audit_pull_request(service, "owner", "repo", 42)

        assert result["loc"] == 2
        service.diff.assert_called_once_with("owner", "repo", 42)

    def test_tolerates_non_dict_mergeable_state_and_non_string_body(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}, mergeable_state="clean", body=12),
            issues=[],
            comments=[{"comment_type": "pr_comment", "body": None}],
            loc=12,
            file_paths=[],
        )
        assert result["r2"] is True
        assert result["hasMinutes"] is False
        assert result["reasons"] == []

    def test_treats_null_resolve_discussion_as_passed(self):
        result = evaluate_audit(
            pr=_pr(milestone={"title": "m"}, mergeable_state={"resolve_discussion_passed": None}),
            issues=[],
            comments=[],
            loc=12,
            file_paths=[],
        )
        assert result["r2"] is True
        assert result["reasons"] == []
