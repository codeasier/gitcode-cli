from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .services import PullRequestService

TEST_PATH_RE = re.compile(
    r"(^|/)(test|tests|__tests__|spec|__mocks__)/|_test\.|\.test\.|\.spec\.|Test\.cpp",
    re.I,
)

AUDIT_JSON_FIELDS = [
    "number",
    "title",
    "url",
    "overall",
    "verdict",
    "loc",
    "r1",
    "r2",
    "r3",
    "r4",
    "failedRules",
    "reasons",
    "rules",
    "milestone",
    "issues",
    "unresolved",
    "reviewCnt",
    "hasTest",
    "hasMinutes",
]


@dataclass(frozen=True)
class AuditThresholds:
    th1: int = 100
    th2: int = 1000
    minutes_keyword: str = "评审纪要"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_discussion_passed(pr: dict[str, Any]) -> bool:
    mergeable_state = pr.get("mergeable_state")
    if not isinstance(mergeable_state, dict):
        return True
    resolve_pass = mergeable_state.get("resolve_discussion_passed", True)
    if resolve_pass is None:
        return True
    return bool(resolve_pass)


def loc_from_list_item(item: dict[str, Any] | None) -> int | None:
    if not item:
        return None
    added = item.get("added_lines")
    removed = item.get("removed_lines")
    if isinstance(added, int) and isinstance(removed, int):
        return added + removed
    return None


def loc_from_diff(diff_text: str) -> int:
    return sum(
        1
        for line in diff_text.splitlines()
        if (line.startswith("+") and not line.startswith("+++"))
        or (line.startswith("-") and not line.startswith("---"))
    )


def paths_from_diff(diff_text: str) -> list[str]:
    return [line for line in diff_text.splitlines() if line.startswith("diff --git ")]


def loc_and_paths_from_files(files: list[Any]) -> tuple[int | None, list[str]]:
    paths: list[str] = []
    loc = 0
    have_counts = False
    for item in files:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if filename:
            paths.append(str(filename))
        patch = item.get("patch") or {}
        if isinstance(patch, dict):
            for key in ("new_path", "old_path"):
                path = patch.get(key)
                if path:
                    paths.append(str(path))
        if "additions" not in item and "deletions" not in item:
            continue
        additions = _optional_int(item["additions"]) if "additions" in item else None
        deletions = _optional_int(item["deletions"]) if "deletions" in item else None
        if additions is None and deletions is None:
            continue
        loc += (additions or 0) + (deletions or 0)
        have_counts = True
    return (loc if have_counts else None), paths


def _label_names(labels: Any) -> list[str]:
    names: list[str] = []
    for label in _as_list(labels):
        if isinstance(label, dict):
            names.append(str(label.get("name") or ""))
        elif label is not None:
            names.append(str(label))
    return names


def _issue_numbers(issues: list[Any]) -> list[str]:
    numbers: list[str] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        number = issue.get("number")
        if number is not None:
            numbers.append(str(number))
    return numbers


def _milestone_title(milestone: Any) -> str | None:
    if isinstance(milestone, dict):
        title = milestone.get("title")
        return str(title) if title else None
    return None


def evaluate_audit(
    *,
    pr: dict[str, Any],
    issues: list[Any],
    comments: list[Any],
    loc: int,
    file_paths: list[str] | None,
    thresholds: AuditThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or AuditThresholds()
    keyword = thresholds.minutes_keyword

    has_milestone = pr.get("milestone") is not None
    has_issue = bool(issues)
    r1 = has_milestone or has_issue
    r1_reasons: list[str] = []
    if not r1:
        r1_reasons.append("R1: no milestone and no officially linked issues")

    unresolved = [
        comment
        for comment in comments
        if isinstance(comment, dict)
        and comment.get("comment_type") == "diff_comment"
        and comment.get("resolved") is False
    ]
    resolve_pass = _resolve_discussion_passed(pr)
    r2 = len(unresolved) == 0 and resolve_pass
    r2_reasons: list[str] = []
    if not r2:
        parts: list[str] = []
        if unresolved:
            parts.append(f"{len(unresolved)} unresolved diff_comment(s)")
        if not resolve_pass:
            parts.append("mergeable_state.resolve_discussion_passed=false")
        r2_reasons.append("R2: " + "; ".join(parts))

    review_cnt = sum(
        1 for comment in comments if isinstance(comment, dict) and comment.get("comment_type") == "diff_comment"
    )
    has_test = None if file_paths is None else any(TEST_PATH_RE.search(_as_text(path)) for path in file_paths)
    r3 = loc <= thresholds.th1 or review_cnt > 0 or bool(has_test)
    r3_reasons: list[str] = []
    if not r3:
        r3_reasons.append(f"R3: loc {loc} > {thresholds.th1}, no diff_comment, and no test-path files")

    has_minutes = (
        keyword in _as_text(pr.get("body"))
        or any(keyword in _as_text(comment.get("body") if isinstance(comment, dict) else "") for comment in comments)
        or any(keyword in name for name in _label_names(pr.get("labels")))
    )
    r4 = loc <= thresholds.th2 or has_minutes
    r4_reasons: list[str] = []
    if not r4:
        r4_reasons.append(f"R4: loc {loc} > {thresholds.th2}, and '{keyword}' not found in body, comments, or labels")

    overall = r1 and r2 and r3 and r4
    reasons = [*r1_reasons, *r2_reasons, *r3_reasons, *r4_reasons]
    failed_rules = [rule for rule, passed in (("R1", r1), ("R2", r2), ("R3", r3), ("R4", r4)) if not passed]
    return {
        "number": pr.get("number"),
        "title": pr.get("title") or "",
        "url": pr.get("html_url") or pr.get("url"),
        "overall": overall,
        "verdict": "PASS" if overall else "FAIL",
        "loc": loc,
        "r1": r1,
        "r2": r2,
        "r3": r3,
        "r4": r4,
        "failedRules": failed_rules,
        "reasons": reasons,
        "rules": {
            "R1": {"pass": r1, "reasons": r1_reasons},
            "R2": {"pass": r2, "reasons": r2_reasons},
            "R3": {"pass": r3, "reasons": r3_reasons},
            "R4": {"pass": r4, "reasons": r4_reasons},
        },
        "milestone": _milestone_title(pr.get("milestone")),
        "issues": _issue_numbers(issues),
        "unresolved": len(unresolved),
        "reviewCnt": review_cnt,
        "hasTest": has_test,
        "hasMinutes": has_minutes,
    }


def resolve_loc_and_paths(
    service: PullRequestService,
    owner: str,
    repo: str,
    number: int,
    listed: dict[str, Any] | None,
    comments: list[Any],
    thresholds: AuditThresholds,
) -> tuple[int, list[str] | None]:
    loc = loc_from_list_item(listed)
    paths: list[str] | None = None
    needs_paths = loc is None or (
        loc > thresholds.th1
        and not any(isinstance(comment, dict) and comment.get("comment_type") == "diff_comment" for comment in comments)
    )
    if loc is None or needs_paths:
        files = _as_list(service.list_files(owner, repo, number))
        file_loc, paths = loc_and_paths_from_files(files)
        if loc is None:
            loc = file_loc
    if loc is None or (needs_paths and not paths):
        diff_text = service.diff(owner, repo, number)
        if loc is None:
            loc = loc_from_diff(diff_text)
        if not paths:
            paths = paths_from_diff(diff_text)
    return loc or 0, paths


def audit_pull_request(
    service: PullRequestService,
    owner: str,
    repo: str,
    number: int,
    listed: dict[str, Any] | None = None,
    thresholds: AuditThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or AuditThresholds()
    detail = service.get(owner, repo, number)
    if not isinstance(detail, dict):
        detail = {}
    if listed:
        if detail.get("milestone") is None and listed.get("milestone") is not None:
            detail = {**detail, "milestone": listed.get("milestone")}
        if not detail.get("labels") and listed.get("labels"):
            detail = {**detail, "labels": listed.get("labels")}
        if not detail.get("body") and listed.get("body"):
            detail = {**detail, "body": listed.get("body")}
        if detail.get("number") is None:
            detail = {**detail, "number": listed.get("number")}
        if not detail.get("title") and listed.get("title"):
            detail = {**detail, "title": listed.get("title")}
        if not detail.get("html_url") and not detail.get("url"):
            detail = {**detail, "html_url": listed.get("html_url") or listed.get("url")}

    issues = _as_list(service.list_issues(owner, repo, number))
    comments = _as_list(service.list_comments(owner, repo, number))
    loc, file_paths = resolve_loc_and_paths(service, owner, repo, number, listed, comments, thresholds)
    return evaluate_audit(
        pr=detail,
        issues=issues,
        comments=comments,
        loc=loc,
        file_paths=file_paths,
        thresholds=thresholds,
    )
