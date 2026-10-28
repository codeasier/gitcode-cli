"""Contracts for publishing individual files through GitCode's Contents API."""

import base64
import json
from contextlib import contextmanager
from urllib.parse import quote

import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.tools import GitCodeTools

REPOSITORY = {"owner": "team", "repo": "project"}
TOKEN = "private-token-for-file-contract-tests"
OLD_SHA = "a" * 40
NEW_SHA = "b" * 40
COMMIT_SHA = "c" * 40
FILE_LIMIT = 262_144
OPERATIONS = ("create", "update", "delete")


def arguments(operation, **overrides):
    result = {
        **REPOSITORY,
        "path": "src/example.py",
        "branch": "feature/file-api",
        "message": "Publish the reviewed change",
    }
    if operation != "delete":
        result["content"] = "print('hello')\n"
    if operation != "create":
        result["sha"] = OLD_SHA
    return {**result, **overrides}


@contextmanager
def catalog(response=None, *, read_only=False, allowed=()):
    requests = []

    def handler(request):
        requests.append(request)
        if callable(response):
            return response(request)
        return httpx.Response(200, json={} if response is None else response)

    with GitCodeAPI(TOKEN, transport=httpx.MockTransport(handler)) as api:
        yield GitCodeTools(api, allowed_repositories=allowed, read_only=read_only), requests


@pytest.mark.parametrize("operation", OPERATIONS)
def test_file_write_schemas_require_a_target_branch_and_declare_mutation(operation):
    with catalog() as (tools, _):
        schema = next(
            tool for tool in tools.list_tools() if tool.name == f"gitcode_{operation}_file"
        )
    required = {"owner", "repo", "path", "branch", "message"}
    if operation != "delete":
        required.add("content")
    if operation != "create":
        required.add("sha")
    assert required <= set(schema.input_schema["required"])
    assert schema.input_schema["additionalProperties"] is False
    assert schema.annotations.read_only_hint is False
    assert schema.annotations.idempotent_hint is False
    if operation == "delete":
        assert schema.annotations.destructive_hint is True


@pytest.mark.parametrize(
    ("operation", "method"), [("create", "POST"), ("update", "PUT"), ("delete", "DELETE")]
)
def test_file_write_uses_documented_endpoint_body_and_bearer_auth(operation, method):
    path = "source files/中文.py"
    args = arguments(operation, path=path)
    if operation != "delete":
        args["content"] = "# 中文\nprint('hello')\n"
    if operation != "create":
        args["sha"] = OLD_SHA.upper()
    response = {"commit": {"sha": COMMIT_SHA}, "content": {"sha": NEW_SHA}}
    with catalog(response) as (tools, requests):
        result = tools.call(f"gitcode_{operation}_file", args)

    assert len(requests) == 1
    request = requests[0]
    assert request.method == method
    assert request.url.host == "api.gitcode.com"
    assert request.url.raw_path == (
        "/api/v5/repos/team/project/contents/" + quote(path, safe="/")
    ).encode("ascii")
    assert not request.url.params
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Content-Type"] == "application/json"
    expected = {"branch": args["branch"], "message": args["message"]}
    if operation != "delete":
        expected["content"] = base64.b64encode(args["content"].encode("utf-8")).decode("ascii")
    if operation != "create":
        expected["sha"] = OLD_SHA
    assert json.loads(request.content) == expected
    assert TOKEN not in str(request.url)
    assert TOKEN.encode() not in request.content
    assert result["repository"] == "team/project"
    assert result["data"]["operation"] == operation
    assert result["data"]["branch"] == args["branch"]
    assert result["data"]["path"] == path
    assert result["data"]["commit_sha"] == COMMIT_SHA
    assert result["data"]["content_sha"] == NEW_SHA
    assert result["data"]["verification_required"] is False


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("encoding", ["utf-8", "base64"])
def test_empty_files_are_valid_and_are_not_dropped(operation, encoding):
    with catalog({"commit": {"sha": COMMIT_SHA}}) as (tools, requests):
        tools.call(f"gitcode_{operation}_file", arguments(operation, content="", encoding=encoding))
    assert json.loads(requests[0].content)["content"] == ""
    assert "encoding" not in json.loads(requests[0].content)


@pytest.mark.parametrize("operation", ["create", "update"])
def test_base64_transmits_binary_bytes_without_double_encoding(operation):
    content = base64.b64encode(b"\x00\xff\x80\r\n").decode("ascii")
    with catalog({"commit": {"sha": COMMIT_SHA}}) as (tools, requests):
        tools.call(
            f"gitcode_{operation}_file", arguments(operation, content=content, encoding="base64")
        )
    assert json.loads(requests[0].content)["content"] == content


@pytest.mark.parametrize("encoding", ["utf-8", "base64"])
def test_exact_decoded_file_limit_is_accepted(encoding):
    # Different character and byte counts catch limits that accidentally count code points.
    text = "界" * (FILE_LIMIT // 3) + "x" * (FILE_LIMIT % 3)
    raw = text.encode("utf-8")
    assert len(raw) == FILE_LIMIT
    content = text if encoding == "utf-8" else base64.b64encode(raw).decode("ascii")
    with catalog({"commit": {"sha": COMMIT_SHA}}) as (tools, requests):
        tools.call("gitcode_create_file", arguments("create", content=content, encoding=encoding))
    assert base64.b64decode(json.loads(requests[0].content)["content"]) == raw


@pytest.mark.parametrize(
    ("content", "encoding"),
    [
        ("x" * (FILE_LIMIT + 1), "utf-8"),
        ("é" * (FILE_LIMIT // 2 + 1), "utf-8"),
        (base64.b64encode(b"x" * (FILE_LIMIT + 1)).decode("ascii"), "base64"),
    ],
    ids=["ascii-byte-overflow", "utf8-byte-overflow", "decoded-base64-overflow"],
)
def test_oversized_content_is_rejected_before_network(content, encoding):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call(
                "gitcode_create_file", arguments("create", content=content, encoding=encoding)
            )
    assert raised.value.code == "invalid_arguments"
    assert not requests


@pytest.mark.parametrize(
    "content",
    ["Zg", "Zg===", " Zg==", "Zg==\n", "Zh==", "Zm9=", "-_8=", "é===", "====", "Zg==junk"],
)
def test_base64_must_be_strict_and_canonical(content):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call(
                "gitcode_create_file", arguments("create", content=content, encoding="base64")
            )
    assert raised.value.code == "invalid_arguments"
    assert not requests


@pytest.mark.parametrize("operation", OPERATIONS)
def test_branch_is_required_without_default_branch_fallback(operation):
    args = arguments(operation)
    args.pop("branch")
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call(f"gitcode_{operation}_file", args)
    assert raised.value.code == "invalid_arguments"
    assert not requests


@pytest.mark.parametrize(
    "branch",
    [
        "",
        "HEAD",
        "refs/heads/main",
        "refs/tags/v1",
        "-option",
        "/main",
        "main/",
        "feature//name",
        "feature/../main",
        "feature..main",
        "feature/.hidden",
        "feature.lock",
        "feature.",
        "feature@{1}",
        "feature:name",
        "feature?name",
        "feature*name",
        "feature[name",
        "feature^name",
        "feature~1",
        "feature\\name",
        "feature%2Fname",
        "with space",
        "with\tcontrol",
        "with\x7fcontrol",
        "bad\ud800unicode",
    ],
)
def test_invalid_branch_names_are_rejected_before_network(branch):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_update_file", arguments("update", branch=branch))
    assert raised.value.code == "invalid_arguments"
    assert not requests


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/absolute.py",
        "../outside.py",
        "src/../outside.py",
        "src//file.py",
        "src/",
        "src/./file.py",
        "%2e%2e/file.py",
        "src\\file.py",
        "src/file?query",
        "src/file#fragment",
        "bad\x00path",
        "bad\udfffpath",
    ],
)
def test_invalid_file_paths_are_rejected_before_network(path):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_delete_file", arguments("delete", path=path))
    assert raised.value.code == "invalid_arguments"
    assert not requests


@pytest.mark.parametrize(
    "sha",
    ["", "a" * 39, "a" * 41, "g" * 40, " " + OLD_SHA, OLD_SHA + "\n", True, 123, "bad\ud800sha"],
)
def test_update_and_delete_need_a_literal_blob_sha(sha):
    with catalog() as (tools, requests):
        for operation in ("update", "delete"):
            with pytest.raises(GitCodeError) as raised:
                tools.call(f"gitcode_{operation}_file", arguments(operation, sha=sha))
            assert raised.value.code == "invalid_arguments"
    assert not requests


def test_commit_message_limit_uses_utf8_bytes_and_preserves_text():
    message = "é" * 2048
    assert len(message.encode("utf-8")) == 4096
    with catalog({"commit": {"sha": COMMIT_SHA}}) as (tools, requests):
        tools.call("gitcode_create_file", arguments("create", message=message))
    assert json.loads(requests[0].content)["message"] == message


@pytest.mark.parametrize("message", ["", " \t\n", "x" * 4097, "é" * 2049, "bad\ud800message", True])
def test_invalid_commit_messages_do_not_reach_gitcode(message):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_create_file", arguments("create", message=message))
    assert raised.value.code == "invalid_arguments"
    assert not requests


@pytest.mark.parametrize(
    "extra",
    [
        {"content": "bad\ud800content"},
        {"content": True},
        {"content": b"bytes are not a JSON string"},
        {"encoding": "hex"},
        {"token": "sensitive-extra-input"},
        {"access_token": "sensitive-extra-input"},
        {"author": {"name": "Override"}},
        {"author[name]": "Override"},
        {"expected_head_sha": COMMIT_SHA},
        {"force": True},
    ],
)
def test_unrecognized_or_invalid_inputs_fail_without_disclosing_values(extra):
    with catalog() as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_create_file", arguments("create", **extra))
    assert raised.value.code == "invalid_arguments"
    assert "sensitive-extra-input" not in str(raised.value)
    assert not requests


@pytest.mark.parametrize("operation", OPERATIONS)
def test_file_writes_are_hidden_and_refused_in_read_only_mode(operation):
    with catalog(read_only=True) as (tools, requests):
        assert f"gitcode_{operation}_file" not in {tool.name for tool in tools.list_tools()}
        with pytest.raises(GitCodeError) as raised:
            tools.call(f"gitcode_{operation}_file", arguments(operation))
    assert raised.value.code == "read_only"
    assert not requests


@pytest.mark.parametrize("operation", OPERATIONS)
def test_file_write_repository_allowlist_is_enforced_before_network(operation):
    with catalog(allowed=["allowed/project"]) as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call(f"gitcode_{operation}_file", arguments(operation))
    assert raised.value.code == "repository_not_allowed"
    assert not requests


@pytest.mark.parametrize(
    ("response", "content_sha"),
    [
        ({}, None),
        ({"content": {"path": "src/example.py"}}, None),
        ({"content": {"sha": NEW_SHA}}, NEW_SHA),
        ({"commit": {"sha": "not-a-commit-sha"}}, None),
        ({"commit": {"sha": 123}}, None),
    ],
)
def test_incomplete_success_requires_verification_without_inventing_sha_or_retry(
    response, content_sha
):
    with catalog(response) as (tools, requests):
        result = tools.call("gitcode_update_file", arguments("update"))["data"]
    assert len(requests) == 1
    assert result["commit_sha"] is None
    assert result["content_sha"] == content_sha
    assert result["verification_required"] is True


def test_empty_success_body_is_ambiguous_without_retrying_the_delete():
    with catalog(lambda _: httpx.Response(204)) as (tools, requests):
        result = tools.call("gitcode_delete_file", arguments("delete"))["data"]
    assert len(requests) == 1
    assert result["commit_sha"] is None
    assert result["content_sha"] is None
    assert result["verification_required"] is True


def test_normalized_result_does_not_echo_source_content_or_unrelated_upstream_fields():
    echoed_source = "private source body only intended for the file"
    response = {
        "commit": {"sha": COMMIT_SHA, "unrelated_secret": TOKEN},
        "content": {"sha": NEW_SHA, "content": echoed_source},
        "unexpected": TOKEN,
    }
    with catalog(response) as (tools, _):
        result = tools.call("gitcode_update_file", arguments("update"))
    assert TOKEN not in json.dumps(result)
    assert echoed_source not in json.dumps(result)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (409, "conflict"),
        (422, "upstream_validation"),
    ],
)
def test_write_failures_are_reported_without_refreshing_sha_or_retrying(status, code):
    with catalog(lambda _: httpx.Response(status, json={"message": f"echo {TOKEN}"})) as (
        tools,
        requests,
    ):
        with pytest.raises(GitCodeError) as raised:
            tools.call("gitcode_update_file", arguments("update"))
    assert len(requests) == 1
    assert raised.value.code == code
    assert TOKEN not in str(raised.value)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_timeout_after_dispatch_is_not_retried(operation):
    def timeout(request):
        raise httpx.ReadTimeout(f"upstream included {TOKEN}", request=request)

    with catalog(timeout) as (tools, requests):
        with pytest.raises(GitCodeError) as raised:
            tools.call(f"gitcode_{operation}_file", arguments(operation))
    assert len(requests) == 1
    assert raised.value.code == "timeout"
    assert "may have completed" in str(raised.value)
    assert TOKEN not in str(raised.value)


def test_branch_read_modify_create_delete_and_pr_form_a_sequential_workflow():
    """A multi-file change uses separate commits, preserving the untouched base branch."""
    initial = {
        "README.md": {"content": b"before\n", "sha": OLD_SHA},
        "obsolete.txt": {"content": b"obsolete\n", "sha": "d" * 40},
    }
    branches = {"main": dict(initial)}
    writes = []
    branch = "feature/file-api"

    def handler(request):
        prefix = "/api/v5/repos/team/project/"
        endpoint = request.url.path.removeprefix(prefix)
        body = json.loads(request.content) if request.content else {}
        if request.method == "POST" and endpoint == "branches":
            assert body == {"branch_name": branch, "refs": "main"}
            branches[branch] = dict(branches[body["refs"]])
            return httpx.Response(200, json={"name": branch})
        if endpoint.startswith("contents/"):
            path = endpoint.removeprefix("contents/")
            if request.method == "GET":
                assert request.url.params["ref"] == branch
                item = branches[branch][path]
                return httpx.Response(
                    200,
                    json={
                        "type": "file",
                        "path": path,
                        "sha": item["sha"],
                        "encoding": "base64",
                        "content": base64.b64encode(item["content"]).decode(),
                    },
                )
            assert body["branch"] == branch
            assert "encoding" not in body
            files = branches[branch]
            if request.method == "POST":
                assert path not in files
            else:
                assert body["sha"] == files[path]["sha"]
            commit_sha = f"{len(writes) + 1:040x}"
            if request.method == "DELETE":
                del files[path]
                response = {"commit": {"sha": commit_sha}}
            else:
                content_sha = f"{len(writes) + 100:040x}"
                files[path] = {
                    "content": base64.b64decode(body["content"], validate=True),
                    "sha": content_sha,
                }
                response = {"commit": {"sha": commit_sha}, "content": {"sha": content_sha}}
            writes.append((request.method, path, commit_sha))
            return httpx.Response(200, json=response)
        if request.method == "POST" and endpoint == "pulls":
            assert body["head"] == branch
            assert body["base"] == "main"
            assert branches[branch]["README.md"]["content"] == b"after\n"
            assert branches[branch]["docs/new.md"]["content"] == b"new documentation\n"
            assert "obsolete.txt" not in branches[branch]
            assert branches["main"] == initial
            assert len(writes) == 3
            return httpx.Response(201, json={"number": 42, "head": {"ref": branch}})
        pytest.fail(f"Unexpected workflow request: {request.method} {request.url.path}")

    with catalog(handler) as (tools, requests):
        tools.call("gitcode_create_branch", {**REPOSITORY, "branch_name": branch, "refs": "main"})
        read = tools.call(
            "gitcode_get_file_contents", {**REPOSITORY, "path": "README.md", "ref": branch}
        )["data"]
        updated = tools.call(
            "gitcode_update_file",
            arguments("update", path="README.md", content="after\n", sha=read["sha"]),
        )["data"]
        created = tools.call(
            "gitcode_create_file",
            arguments("create", path="docs/new.md", content="new documentation\n"),
        )["data"]
        obsolete = tools.call(
            "gitcode_get_file_contents", {**REPOSITORY, "path": "obsolete.txt", "ref": branch}
        )["data"]
        deleted = tools.call(
            "gitcode_delete_file", arguments("delete", path="obsolete.txt", sha=obsolete["sha"])
        )["data"]
        pr = tools.call(
            "gitcode_create_pull_request",
            {
                **REPOSITORY,
                "title": "Publish reviewed file changes",
                "head": branch,
                "base": "main",
            },
        )["data"]

    assert pr["number"] == 42
    assert len(requests) == 7
    assert [(method, path) for method, path, _ in writes] == [
        ("PUT", "README.md"),
        ("POST", "docs/new.md"),
        ("DELETE", "obsolete.txt"),
    ]
    assert len({item["commit_sha"] for item in (updated, created, deleted)}) == 3
    assert all(item["verification_required"] is False for item in (updated, created, deleted))
