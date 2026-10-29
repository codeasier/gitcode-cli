"""Focused GitCode tools with input schemas and enforced execution policies."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated, Any, Literal
from urllib.parse import quote

from mcp.types import Tool, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .api import GitCodeAPI, GitCodeError, segment
from .file_writes import (
    FILE_WRITE_METHODS,
    MAX_ENCODED_FILE_CHARS,
    MAX_MESSAGE_BYTES,
    encode_file_content,
    utf8_bytes,
    validate_commit_message,
    validate_write_branch,
    write_file,
)

PositiveNumber = Annotated[int, Field(ge=1)]
Name = Annotated[str, Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")]
Text = Annotated[str, Field(max_length=65_536)]
Title = Annotated[str, Field(min_length=1, max_length=1024)]
Reference = Annotated[str, Field(min_length=1, max_length=1024)]
Labels = Annotated[list[Annotated[str, Field(min_length=1, max_length=100)]], Field(max_length=100)]
BlobSHA = Annotated[str, Field(min_length=40, max_length=40, pattern=r"^[0-9a-fA-F]{40}$")]


def _safe_reference(value: str) -> str:
    if (
        any(character.isspace() or ord(character) < 32 for character in value)
        or any(character in value for character in "\\%?#")
        or any(part in {".", "..", ""} for part in value.split("/"))
    ):
        raise ValueError(
            "Use a literal branch, tag, or commit without path traversal or URL encoding."
        )
    return value


def _safe_file_path(value: str) -> str:
    if (
        value.startswith("/")
        or any(character in value for character in "\\%?#")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(part in {".", "..", ""} for part in value.split("/"))
    ):
        raise ValueError("Use a relative repository file path without traversal or URL encoding.")
    return value


class RepoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner: Name = Field(description="GitCode owner or organization path, for example Ascend.")
    repo: Name = Field(description="GitCode repository path, without a URL or .git suffix.")

    @field_validator("owner", "repo")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if ".." in value or value.endswith(".git"):
            raise ValueError("Repository names cannot contain '..' or end with '.git'.")
        return value


class PageArgs(RepoArgs):
    page: Annotated[int, Field(ge=1)] = 1
    per_page: Annotated[int, Field(ge=1, le=100)] = 30


class BranchArgs(RepoArgs):
    branch: Reference

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return _safe_reference(value)


class FileArgs(RepoArgs):
    path: Annotated[str, Field(min_length=1, max_length=4096)]
    ref: Reference | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _safe_file_path(value)

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        return None if value is None else _safe_reference(value)


class TreeArgs(PageArgs):
    sha: Reference = Field(description="Commit SHA, branch, or tag identifying the tree.")
    recursive: bool = False
    file_path: Annotated[str, Field(min_length=1, max_length=4096)] | None = None

    @field_validator("sha")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _safe_reference(value)

    @field_validator("file_path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else _safe_file_path(value)


class CommitArgs(RepoArgs):
    sha: Reference

    @field_validator("sha")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _safe_reference(value)


class CommitsArgs(PageArgs):
    sha: Reference | None = None
    path: Annotated[str, Field(max_length=4096)] | None = None

    @field_validator("sha")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        return None if value is None else _safe_reference(value)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else _safe_file_path(value)


class CreateBranchArgs(RepoArgs):
    branch_name: Reference
    refs: Reference = Field(description="Existing branch, tag, or commit to branch from.")
    description: Annotated[str, Field(max_length=4096)] | None = None

    @field_validator("branch_name", "refs")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _safe_reference(value)


class FileWriteArgs(RepoArgs):
    path: Annotated[str, Field(min_length=1, max_length=4096)] = Field(
        description="Relative repository file path, not a local filesystem path."
    )
    branch: Reference = Field(
        description="Explicit existing short branch name. Never defaults to the default branch."
    )
    message: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_BYTES)] = Field(
        description="Nonblank commit message, at most 4096 UTF-8 bytes."
    )

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        utf8_bytes(value, maximum=4096)
        return _safe_file_path(value)

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return validate_write_branch(value)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return validate_commit_message(value)


class CreateFileArgs(FileWriteArgs):
    content: Annotated[str, Field(max_length=MAX_ENCODED_FILE_CHARS)] = Field(
        description="Complete file content; at most 256 KiB of decoded bytes. Empty files are allowed."
    )
    encoding: Literal["utf-8", "base64"] = Field(
        default="utf-8", description="UTF-8 text or canonical, padded Base64 without whitespace."
    )

    @model_validator(mode="after")
    def validate_content(self) -> CreateFileArgs:
        encode_file_content(self.content, self.encoding)
        return self


class UpdateFileArgs(CreateFileArgs):
    sha: BlobSHA = Field(
        description="Existing file Blob SHA from get_file_contents at this branch; not a commit SHA."
    )

    @field_validator("sha")
    @classmethod
    def normalize_sha(cls, value: str) -> str:
        return value.lower()


class DeleteFileArgs(FileWriteArgs):
    sha: BlobSHA = Field(
        description="Existing file Blob SHA from get_file_contents at this branch; not a commit SHA."
    )

    @field_validator("sha")
    @classmethod
    def normalize_sha(cls, value: str) -> str:
        return value.lower()


class ListIssuesArgs(PageArgs):
    state: Literal["open", "closed", "all"] = "open"
    search: Annotated[str, Field(max_length=1024)] | None = None
    labels: Labels | None = None
    creator: Name | None = None
    assignee: Annotated[str, Field(min_length=1, max_length=100)] | None = Field(
        default=None,
        description="GitCode issue assignee ID, not a GitHub-style username assumption.",
    )


class IssueArgs(RepoArgs):
    issue_number: PositiveNumber


class IssuePageArgs(PageArgs):
    issue_number: PositiveNumber


class CreateIssueArgs(RepoArgs):
    title: Title
    body: Text = ""
    assignee: Name | None = Field(default=None, description="GitCode issue assignee username.")
    labels: Labels | None = None
    milestone: PositiveNumber | None = None


class UpdateIssueArgs(IssueArgs):
    title: Title = Field(
        description="GitCode requires a title on updates; preserve the existing title when unchanged."
    )
    body: Text | None = None
    state: Literal["close", "reopen"] | None = Field(
        default=None,
        description="GitCode update actions are close/reopen; list states are open/closed.",
    )
    assignee: Name | None = None
    labels: Labels | None = None
    milestone: PositiveNumber | None = None


class IssueCommentArgs(IssueArgs):
    body: Annotated[str, Field(min_length=1, max_length=65_536)]


class ListPullsArgs(PageArgs):
    state: Literal["open", "closed", "merged", "locked", "all"] = "open"
    base: Reference | None = None
    author: Name | None = None
    labels: Labels | None = None

    @field_validator("base")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        return None if value is None else _safe_reference(value)


class PullArgs(RepoArgs):
    pull_number: PositiveNumber


class PullPageArgs(PageArgs):
    pull_number: PositiveNumber


class CreatePullArgs(RepoArgs):
    title: Title
    head: Reference = Field(
        description="Source branch; use username:branch for a cross-repository PR."
    )
    base: Reference
    body: Text = ""
    draft: bool = False
    fork_path: Annotated[str, Field(max_length=511)] | None = Field(
        default=None, description="Required owner/repo source path for a cross-repository PR."
    )
    assignees: Annotated[list[Name], Field(max_length=100)] | None = Field(
        default=None, description="GitCode PR reviewers, not issue assignees."
    )
    testers: Annotated[list[Name], Field(max_length=100)] | None = None
    labels: Labels | None = None
    milestone_number: PositiveNumber | None = None
    issue_numbers: Annotated[list[PositiveNumber], Field(max_length=100)] = Field(
        default_factory=list,
        description="Linked issue numbers, mapped to GitCode inner_issue_nums.",
    )

    @field_validator("head", "base")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _safe_reference(value)

    @model_validator(mode="after")
    def check_fork(self) -> CreatePullArgs:
        if ":" in self.head and not self.fork_path:
            raise ValueError("Cross-repository PRs require fork_path.")
        if self.fork_path:
            parts = self.fork_path.split("/")
            if len(parts) != 2:
                raise ValueError("fork_path must be owner/repo.")
            RepoArgs(owner=parts[0], repo=parts[1])
        return self


class UpdatePullArgs(PullArgs):
    title: Title | None = None
    body: Text | None = None
    state: Literal["open", "closed"] | None = None
    draft: bool | None = None
    labels: Labels | None = None
    milestone_number: PositiveNumber | None = None

    @model_validator(mode="after")
    def require_change(self) -> UpdatePullArgs:
        if not any(
            getattr(self, field) is not None
            for field in ("title", "body", "state", "draft", "labels", "milestone_number")
        ):
            raise ValueError("Provide at least one PR field to update.")
        return self


class PullCommentArgs(PullArgs):
    body: Annotated[str, Field(min_length=1, max_length=65_536)]


class MergePullArgs(PullArgs):
    merge_method: Literal["merge", "rebase"] = "merge"
    squash: bool = False
    title: Title | None = None
    description: Text | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: type[RepoArgs]
    read_only: bool = True
    destructive: bool = False


SPECS = (
    ToolSpec("get_repository", "Read a GitCode repository's metadata and permissions.", RepoArgs),
    ToolSpec(
        "get_clone_info",
        "Get credential-free Git URLs and execution-environment guidance; does not clone files.",
        RepoArgs,
    ),
    ToolSpec("list_branches", "Read one page of GitCode repository branches.", PageArgs),
    ToolSpec("get_branch", "Read a GitCode branch and its current commit.", BranchArgs),
    ToolSpec(
        "get_file_contents",
        "Read a repository file at a chosen ref; preserves the API content encoding.",
        FileArgs,
    ),
    ToolSpec(
        "get_repository_tree",
        "Read one upstream page of a Git tree, optionally recursive or under file_path. Follow next_page to inspect the remaining entries.",
        TreeArgs,
    ),
    ToolSpec(
        "list_commits",
        "Read one page of repository commits, optionally filtered by ref or path.",
        CommitsArgs,
    ),
    ToolSpec("get_commit", "Read one repository commit and its API-provided details.", CommitArgs),
    ToolSpec(
        "create_branch",
        "Create a new GitCode branch from an existing reference.",
        CreateBranchArgs,
        False,
    ),
    ToolSpec(
        "create_file",
        "Create a file and publish one commit on an explicit existing GitCode branch. Accepts UTF-8 or Base64, up to 256 KiB decoded. Use update_file for existing files. No automatic retries or multi-file atomicity.",
        CreateFileArgs,
        False,
    ),
    ToolSpec(
        "update_file",
        "Replace a file and publish one commit. First read it at the target branch and supply its Blob SHA. Up to 256 KiB decoded; no force, automatic retry, or branch-head CAS guarantee.",
        UpdateFileArgs,
        False,
        True,
    ),
    ToolSpec(
        "delete_file",
        "Delete a file and publish one commit on an explicit branch. Requires the file's current Blob SHA from that branch. No force, automatic retry, or multi-file rollback.",
        DeleteFileArgs,
        False,
        True,
    ),
    ToolSpec(
        "list_issues",
        "Read one page of GitCode issues, with state, labels, or text filters.",
        ListIssuesArgs,
    ),
    ToolSpec("get_issue", "Read a GitCode issue by its repository issue number.", IssueArgs),
    ToolSpec("list_issue_comments", "Read one page of comments on a GitCode issue.", IssuePageArgs),
    ToolSpec(
        "create_issue",
        "Create a GitCode issue with title, body, and optional labels or assignee.",
        CreateIssueArgs,
        False,
    ),
    ToolSpec(
        "update_issue",
        "Update an issue; title is required and state actions are close or reopen.",
        UpdateIssueArgs,
        False,
        True,
    ),
    ToolSpec(
        "add_issue_comment", "Post a new comment on a GitCode issue.", IssueCommentArgs, False
    ),
    ToolSpec(
        "list_labels",
        "Read a client-side page of labels after one size-bounded unpaged upstream fetch. Each page re-fetches the collection.",
        PageArgs,
    ),
    ToolSpec(
        "list_milestones",
        "Read a client-side page of milestones after one size-bounded unpaged upstream fetch. Each page re-fetches the collection.",
        PageArgs,
    ),
    ToolSpec(
        "list_pull_requests",
        "Read one page of GitCode pull requests; reviewer semantics follow GitCode.",
        ListPullsArgs,
    ),
    ToolSpec(
        "get_pull_request",
        "Read a GitCode pull request and its current merge/review state.",
        PullArgs,
    ),
    ToolSpec(
        "list_pull_request_files",
        "Read a client-side page of changed PR files after one size-bounded unpaged upstream fetch. Pages are not a stable snapshot; oversized responses require local git diff.",
        PullPageArgs,
    ),
    ToolSpec(
        "get_pull_request_diff",
        "Read GitCode's structured PR diff from files.json with a hard response-size limit. Preserves native diff_refs and content; use local git diff for oversized or omitted content.",
        PullArgs,
    ),
    ToolSpec(
        "list_pull_request_comments",
        "Read one page of GitCode pull-request comments.",
        PullPageArgs,
    ),
    ToolSpec(
        "list_pull_request_commits",
        "Read one page of commits in a GitCode pull request.",
        PullPageArgs,
    ),
    ToolSpec(
        "create_pull_request",
        "Create a PR; use fork_path for forks. GitCode assignees are reviewers. Verify source changes already exist remotely, through file tools or Git push.",
        CreatePullArgs,
        False,
    ),
    ToolSpec(
        "update_pull_request",
        "Update supported PR fields without changing the base branch or forcing a merge.",
        UpdatePullArgs,
        False,
        True,
    ),
    ToolSpec(
        "add_pull_request_comment",
        "Post a general PR comment; does not create a GitHub request-changes review.",
        PullCommentArgs,
        False,
    ),
    ToolSpec(
        "approve_pull_request",
        "Submit GitCode's native review/approval with force=false. Post review text separately using add_pull_request_comment; request-changes is not emulated.",
        PullArgs,
        False,
    ),
    ToolSpec(
        "merge_pull_request",
        "Merge a PR using GitCode checks; never force-merges. Squash is a separate boolean, not a merge method.",
        MergePullArgs,
        False,
        True,
    ),
)


class GitCodeTools:
    """Synchronous catalog; the server runs calls in a bounded worker thread."""

    def __init__(
        self,
        api: GitCodeAPI,
        *,
        allowed_repositories: Iterable[str] = (),
        read_only: bool = False,
    ) -> None:
        self.api = api
        self.read_only = read_only
        self.allowed_repositories = frozenset(allowed_repositories)
        for repository in self.allowed_repositories:
            parts = repository.split("/")
            try:
                if len(parts) != 2:
                    raise ValueError
                RepoArgs(owner=parts[0], repo=parts[1])
            except (ValueError, ValidationError):
                raise GitCodeError(
                    "invalid_configuration", "Repository allowlist entries must be owner/repo."
                ) from None
        self._specs = {f"gitcode_{spec.name}": spec for spec in SPECS}

    def list_tools(self) -> list[Tool]:
        return [
            Tool(
                name=name,
                description=spec.description,
                inputSchema=spec.arguments.model_json_schema(),
                outputSchema={"type": "object", "additionalProperties": True},
                annotations=ToolAnnotations(
                    readOnlyHint=spec.read_only,
                    destructiveHint=spec.destructive,
                    idempotentHint=spec.read_only,
                    openWorldHint=True,
                ),
            )
            for name, spec in self._specs.items()
            if not self.read_only or spec.read_only
        ]

    def _authorize_repository(self, owner: str, repo: str) -> None:
        if self.allowed_repositories and f"{owner}/{repo}" not in self.allowed_repositories:
            raise GitCodeError(
                "repository_not_allowed", "This repository is outside the configured allowlist."
            )

    def call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        spec = self._specs.get(name)
        if spec is None:
            raise GitCodeError("unknown_tool", "The requested GitCode tool does not exist.")
        if self.read_only and not spec.read_only:
            raise GitCodeError(
                "read_only", "Write tools are disabled by the server's read-only policy."
            )
        try:
            model = spec.arguments.model_validate(arguments if arguments is not None else {})
        except ValidationError:
            raise GitCodeError(
                "invalid_arguments", "Tool arguments do not match the tool's JSON schema."
            ) from None
        data = model.model_dump(exclude_none=True)
        owner, repo = data.pop("owner"), data.pop("repo")
        self._authorize_repository(owner, repo)
        if spec.name == "create_pull_request" and data.get("fork_path"):
            source_owner, source_repo = data["fork_path"].split("/")
            self._authorize_repository(source_owner, source_repo)
        result = self._execute(spec.name, owner, repo, data)
        if not isinstance(result, dict) or "data" not in result:
            result = {"data": result}
        return {"repository": f"{owner}/{repo}", **result}

    def _execute(self, action: str, owner: str, repo: str, data: dict[str, Any]) -> Any:
        # owner/repo are schema-validated literal path names; all other path
        # values are encoded as segments and never interpolated as API URLs.
        prefix = f"/repos/{segment(owner)}/{segment(repo)}"
        for field in ("labels", "assignees", "testers"):
            if isinstance(data.get(field), list):
                data[field] = ",".join(data[field])
        if action in {"get_repository", "get_clone_info"}:
            repository = self.api.get(prefix)
            if action == "get_repository":
                return {"data": repository}
            if not isinstance(repository, dict):
                raise GitCodeError(
                    "invalid_response", "GitCode did not return repository metadata."
                )
            return {
                "data": {
                    "https_url": f"https://gitcode.com/{owner}/{repo}.git",
                    "ssh_url": f"git@gitcode.com:{owner}/{repo}.git",
                    "default_branch": repository.get("default_branch"),
                    "cloned": False,
                    "execution_note": "Run git clone in the same execution environment that will edit and test the code. A remote MCP server's filesystem is not the dot workspace.",
                    "authentication_note": "Use a local credential helper or SSH agent; never embed a token in a clone URL.",
                }
            }
        if action == "list_branches":
            return self.api.page(f"{prefix}/branches", **data)
        if action == "get_branch":
            return self.api.get(f"{prefix}/branches/{segment(data['branch'])}")
        if action == "get_file_contents":
            path = quote(data.pop("path"), safe="/")
            return self.api.get(f"{prefix}/contents/{path}", params=data)
        if action == "get_repository_tree":
            sha = data.pop("sha")
            data["recursive"] = 1 if data["recursive"] else 0
            tree = self.api.get(f"{prefix}/git/trees/{segment(sha)}", params=data)
            if not isinstance(tree, dict):
                raise GitCodeError(
                    "invalid_response", "GitCode did not return the expected tree object."
                )
            result = self.api.page_result(
                tree.get("tree"), page=data["page"], per_page=data["per_page"]
            )
            result["upstream_metadata"] = {
                key: value for key, value in tree.items() if key != "tree"
            }
            result["upstream_truncated"] = tree.get("truncated")
            return result
        if action == "list_commits":
            return self.api.page(f"{prefix}/commits", **data)
        if action == "get_commit":
            return self.api.get(f"{prefix}/commits/{segment(data['sha'])}")
        if action == "create_branch":
            return self.api.post(f"{prefix}/branches", json=data)
        if action in FILE_WRITE_METHODS:
            return write_file(self.api, prefix, action, data)
        if action == "list_issues":
            items = self.api.issues.list(owner, repo, **data)
            return self.api.page_result(items, page=data["page"], per_page=data["per_page"])
        if action == "get_issue":
            return self.api.issues.get(owner, repo, str(data["issue_number"]))
        if action == "list_issue_comments":
            number = data.pop("issue_number")
            return self.api.page(f"{prefix}/issues/{number}/comments", **data)
        if action == "create_issue":
            return self.api.issues.create(owner, repo, **data)
        if action == "update_issue":
            number = data.pop("issue_number")
            return self.api.issues.update(owner, repo, str(number), **data)
        if action == "add_issue_comment":
            return self.api.issues.comment(owner, repo, str(data["issue_number"]), data["body"])
        if action == "list_labels":
            items = self.api.issues.list_labels(owner, repo)
            return self.api.collection_page_result(items, **data)
        if action == "list_milestones":
            items = self.api.issues.list_milestones(owner, repo)
            return self.api.collection_page_result(items, **data)
        if action == "list_pull_requests":
            items = self.api.pulls.list(owner, repo, **data)
            return self.api.page_result(items, page=data["page"], per_page=data["per_page"])
        if action == "get_pull_request":
            return self.api.pulls.get(owner, repo, data["pull_number"])
        if action == "list_pull_request_files":
            number = data.pop("pull_number")
            items = self.api.get(f"{prefix}/pulls/{number}/files")
            return self.api.collection_page_result(items, **data)
        if action in {"list_pull_request_comments", "list_pull_request_commits"}:
            number = data.pop("pull_number")
            resource = action.rsplit("_", 1)[1]
            # The upstream comments service eagerly fetches all pages.
            # Keep MCP calls bounded by using its client for one page.
            return self.api.page(f"{prefix}/pulls/{number}/{resource}", **data)
        if action == "get_pull_request_diff":
            diff = self.api.get(f"{prefix}/pulls/{data['pull_number']}/files.json")
            if not isinstance(diff, dict) or not isinstance(diff.get("diffs"), list):
                raise GitCodeError(
                    "invalid_response", "GitCode did not return the expected structured diff."
                )
            return {"data": diff, "format": "gitcode_structured_diff"}
        if action == "create_pull_request":
            data["inner_issue_nums"] = ";".join(str(number) for number in data.pop("issue_numbers"))
            return self.api.pulls.create(owner, repo, **data)
        if action == "update_pull_request":
            number = data.pop("pull_number")
            return self.api.pulls.update(owner, repo, number, **data)
        if action == "add_pull_request_comment":
            return self.api.pulls.comment(owner, repo, data["pull_number"], data["body"])
        if action == "approve_pull_request":
            return self.api.pulls.review(owner, repo, data["pull_number"], force=False)
        if action == "merge_pull_request":
            number = data.pop("pull_number")
            return self.api.pulls.merge(owner, repo, number, **data)
        raise GitCodeError("unknown_tool", "The requested GitCode tool does not exist.")
