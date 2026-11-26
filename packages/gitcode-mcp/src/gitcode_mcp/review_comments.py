"""Immediate GitCode PR comments; neither pending reviews nor atomic SHA-bound writes."""

from __future__ import annotations

import re
from typing import Any

from .api import GitCodeAPI, GitCodeError

_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_HUNK = re.compile(
    r"@@ -([0-9]{1,10})(?:,([0-9]{1,10}))? \+([0-9]{1,10})(?:,([0-9]{1,10}))? @@(?: .*)?"
)


def _head_sha(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and _SHA.fullmatch(value) else None


def _has_omissions(data: dict[str, Any]) -> bool:
    return any(
        key in data and data[key] is not False and not (type(data[key]) is int and data[key] == 0)
        for key in ("truncated", "too_large", "collapsed")
    )


def _target_lines(file: dict[str, Any], position: int) -> bool:
    """Recognize complete observed text hunks, not ranges with omitted rows."""
    content = file.get("content")
    rows = content.get("text") if isinstance(content, dict) else None
    if _has_omissions(file) or not isinstance(content, dict) or _has_omissions(content):
        return False
    if not isinstance(rows, list) or not rows:
        return False
    added = removed = matches = 0
    old = new = old_left = new_left = 0
    last_old = last_new = 0
    saw_hunk = False
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("line_content"), str):
            return False
        kind = row.get("type")
        old_side, new_side = row.get("old_line"), row.get("new_line")
        if kind == "match":
            hunk = _HUNK.fullmatch(row["line_content"])
            if hunk is None or old_left or new_left or old_side != "..." or new_side != "...":
                return False
            old_start, old_count, new_start, new_count = hunk.groups()
            old, new = int(old_start), int(new_start)
            old_left, new_left = int(old_count or "1"), int(new_count or "1")
            if (old_left and (old <= last_old or old < 1)) or (
                new_left and (new <= last_new or new < 1)
            ):
                return False
            saw_hunk = True
            continue
        if not saw_hunk or kind not in (None, "new", "old"):
            return False
        if not isinstance(old_side, dict) or not isinstance(new_side, dict):
            return False
        old_line, new_line = old_side.get("line_num"), new_side.get("line_num")
        if kind == "new":
            if old_line != "":
                return False
            added += 1
        else:
            if old_left < 1 or type(old_line) is not int or old_line != old:
                return False
            last_old = old
            old += 1
            old_left -= 1
        if kind == "old":
            if new_line != "":
                return False
            removed += 1
        else:
            if new_left < 1 or type(new_line) is not int or new_line != new:
                return False
            matches += new == position
            last_new = new
            new += 1
            new_left -= 1
    return (
        saw_hunk
        and not old_left
        and not new_left
        and matches == 1
        and type(file.get("added_lines")) is int
        and file["added_lines"] == added
        and type(file.get("remove_lines")) is int
        and file["remove_lines"] == removed
    )


def _verify_inline_diff(
    api: GitCodeAPI, owner: str, repo: str, pull_number: int, *, head: str, path: str, position: int
) -> None:
    diff = api.get(f"/repos/{owner}/{repo}/pulls/{pull_number}/files.json")
    if not isinstance(diff, dict):
        raise GitCodeError("invalid_response", "Could not verify the current PR diff.")
    refs, rows = diff.get("diff_refs"), diff.get("diffs")
    if (
        _has_omissions(diff)
        or type(diff.get("code")) is not int
        or diff["code"] != 0
        or not isinstance(refs, dict)
        or not isinstance(rows, list)
        or type(diff.get("count")) is not int
        or diff["count"] != len(rows)
    ):
        raise GitCodeError("invalid_response", "Could not verify a complete PR diff.")
    diff_head = _head_sha(refs.get("head_sha"))
    if diff_head is None:
        raise GitCodeError("invalid_response", "Could not verify the PR diff head.")
    if diff_head != head:
        raise GitCodeError(
            "conflict", "The PR diff head has changed. Review the current diff before posting."
        )
    candidates = []
    for row in rows:
        stat = row.get("statistic") if isinstance(row, dict) else None
        if not isinstance(stat, dict) or not isinstance(stat.get("new_path"), str):
            raise GitCodeError(
                "invalid_response", "Could not verify the file records in this PR diff."
            )
        if stat["new_path"] == path:
            candidates.append(row)
    if len(candidates) == 1:
        target = candidates[0]
        stat, file_head = target["statistic"], target.get("head")
        if (
            stat.get("type") == "text_type"
            and stat.get("path") == path
            and not _has_omissions(stat)
            and isinstance(file_head, dict)
            and _head_sha(file_head.get("commit_id")) == head
            and _target_lines(target, position)
        ):
            return
    raise GitCodeError(
        "diff_anchor_not_verified",
        "Could not verify this path and right-side line in the complete PR diff.",
    )


def _unknown_receipt() -> GitCodeError:
    return GitCodeError(
        "invalid_response",
        "GitCode did not return a recognizable comment receipt.",
        operation_may_have_completed=True,
    )


def write_inline_comment(
    api: GitCodeAPI,
    owner: str,
    repo: str,
    *,
    pull_number: int,
    body: str,
    expected_head_sha: str,
    path: str,
    position: int,
) -> dict[str, Any]:
    # The native endpoint accepts path and position, not a head/commit argument.
    # Check the latest point-in-time target and describe the race honestly.
    pr = api.pulls.get(owner, repo, pull_number)
    if not isinstance(pr, dict) or not isinstance(pr.get("head"), dict):
        raise GitCodeError("invalid_response", "Could not verify the PR head.")
    head = _head_sha(pr["head"].get("sha"))
    if head is None or str(pr.get("number")) != str(pull_number):
        raise GitCodeError("invalid_response", "Could not verify the PR identity and head.")
    if head.lower() != expected_head_sha.lower():
        raise GitCodeError(
            "conflict", "The PR head has changed. Review the current diff before posting."
        )
    _verify_inline_diff(api, owner, repo, pull_number, head=head, path=path, position=position)
    result = api.pulls.comment(owner, repo, pull_number, body, path=path, position=position)
    if not isinstance(result, dict) or result.get("body") != body:
        raise _unknown_receipt()
    response_id = result.get("id")
    if not (
        type(response_id) is int
        and response_id > 0
        or isinstance(response_id, str)
        and _OPAQUE_ID.fullmatch(response_id)
    ):
        raise _unknown_receipt()
    # The POST does not attest the final placement or an atomic PR head.
    return {"id": response_id, "observed_head_sha": head.lower(), "placement_verified": False}


def write_review_reply(
    api: GitCodeAPI,
    owner: str,
    repo: str,
    *,
    pull_number: int,
    body: str,
    discussion_id: str,
    page: int,
    per_page: int,
) -> dict[str, Any]:
    # A single caller-selected, server-read PR comment page proves membership.
    # A stale pagination hint is a read-only failure, never an invitation to post blindly.
    rows = api.page(
        f"/repos/{owner}/{repo}/pulls/{pull_number}/comments", page=page, per_page=per_page
    )["data"]
    if not any(isinstance(row, dict) and row.get("discussion_id") == discussion_id for row in rows):
        raise GitCodeError(
            "discussion_not_verified",
            "Find the discussion on this PR's current comment page before replying.",
        )
    reply = api.pulls.reply(owner, repo, pull_number, discussion_id, body)
    if not (
        isinstance(reply, dict)
        and reply.get("id") == discussion_id
        and type(reply.get("noteId")) is int
        and reply["noteId"] > 0
        and reply.get("body") == body
    ):
        raise _unknown_receipt()
    return {"discussion_id": discussion_id, "note_id": reply["noteId"]}
