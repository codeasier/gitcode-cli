"""File primitives keep the original tokenless request-override contract."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

import pytest

from gitcode_cli.client import GitCodeClient
from gitcode_cli.services import FileService, RepoService

SHA = "A" * 40
PAYLOAD = {"branch": "feature/files", "message": "Publish file"}


class RecordingClient(GitCodeClient):
    def __init__(self):
        self.calls = []
        self.result = {"content": {"sha": SHA}}
        self.error = None

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        accept: str = "application/json",
        response_format: Literal["json", "text"] = "json",
    ) -> Any:
        self.calls.append((method, path, params, json, accept, response_format))
        if self.error is not None:
            raise self.error
        return self.result


def _arguments(operation):
    if operation == "get":
        return {"ref": "feature/files?literal#%", "page": 2, "omitted": None}
    result = dict(PAYLOAD)
    if operation != "delete":
        result["content"] = "AP+A\r\n"
    if operation != "create":
        result["sha"] = SHA
    return result


@pytest.mark.parametrize(
    ("operation", "method"), [("get", "GET"), ("create", "POST"), ("update", "PUT"), ("delete", "DELETE")]
)
def test_single_request_preserves_values_and_response(operation, method):
    client = RecordingClient()
    arguments = _arguments(operation)
    before = dict(arguments)

    result = getattr(FileService(client), operation)("owner", "repo", "docs/说明 #?%.md", **arguments)

    assert result is client.result
    assert arguments == before
    assert client.calls == [
        (
            method,
            "/repos/owner/repo/contents/docs/%E8%AF%B4%E6%98%8E%20%23%3F%25.md",
            arguments if operation == "get" else None,
            None if operation == "get" else arguments,
            "application/json",
            "json",
        )
    ]
    assert not hasattr(client, "token")
    assert not hasattr(client, "_client")


@pytest.mark.parametrize("path", ["README.md", "docs/hello world.md", "文档/说明.md", "docs/#?%.md", "%2F", "%2e%2e/file"])
def test_decoded_paths_are_encoded_exactly_once_without_unquoting(path):
    client = RecordingClient()
    FileService(client).get("owner", "repo", path)
    assert client.calls[0][1] == "/repos/owner/repo/contents/" + quote(path, safe="/")


def test_owner_and_repo_are_encoded_as_single_segments():
    client = RecordingClient()
    FileService(client).get("team name", "项目%2F", "README.md")
    assert client.calls[0][1] == "/repos/team%20name/%E9%A1%B9%E7%9B%AE%252F/contents/README.md"


def test_empty_get_path_preserves_root_listing_and_query_contract():
    client = RecordingClient()
    FileService(client).get("owner", "repo", "", ref=None)
    assert client.calls == [("GET", "/repos/owner/repo/contents/", {"ref": None}, None, "application/json", "json")]


def test_repo_contents_delegates_to_the_canonical_file_service(monkeypatch):
    client = RecordingClient()
    calls = []
    expected = object()

    def get(service, owner, repo, path, **params):
        calls.append((service.client, owner, repo, path, params))
        return expected

    monkeypatch.setattr(FileService, "get", get)
    assert RepoService(client).contents("owner", "repo", "文档/read me.md", ref="feature/a", extra=None) is expected
    assert calls == [(client, "owner", "repo", "文档/read me.md", {"ref": "feature/a", "extra": None})]
    assert client.calls == []


@pytest.mark.parametrize("operation", ["get", "create", "update", "delete"])
@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "a/",
        "a//b",
        ".",
        "..",
        "a/../b",
        "a/./b",
        "a\\b",
        "bad\x00path",
        "bad\x7fpath",
        "bad\ud800path",
        "https://example/file",
        None,
    ],
)
def test_unsafe_path_structure_fails_before_request(operation, path):
    client = RecordingClient()
    with pytest.raises(ValueError):
        getattr(FileService(client), operation)("owner", "repo", path, **_arguments(operation))
    assert client.calls == []


@pytest.mark.parametrize(
    ("owner", "repo"),
    [("", "repo"), ("owner", ""), ("a/b", "repo"), ("owner", "a/b"), ("..", "repo"), ("owner", None)],
)
def test_invalid_repository_segments_fail_before_request(owner, repo):
    client = RecordingClient()
    with pytest.raises(ValueError):
        FileService(client).get(owner, repo, "README.md")
    assert client.calls == []


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_mutations_reject_empty_paths(operation):
    client = RecordingClient()
    with pytest.raises(ValueError):
        getattr(FileService(client), operation)("owner", "repo", "", **_arguments(operation))
    assert client.calls == []


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
@pytest.mark.parametrize("field", ["branch", "message"])
@pytest.mark.parametrize("value", ["", " \n", None, True])
def test_mutations_require_explicit_nonblank_branch_and_message(operation, field, value):
    client = RecordingClient()
    arguments = {**_arguments(operation), field: value}
    with pytest.raises(ValueError):
        getattr(FileService(client), operation)("owner", "repo", "file", **arguments)
    assert client.calls == []


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_required_keyword_arguments_cannot_fall_back_to_remote_state(operation):
    client = RecordingClient()
    complete = _arguments(operation)
    for field in complete:
        arguments = {key: value for key, value in complete.items() if key != field}
        with pytest.raises(TypeError):
            getattr(FileService(client), operation)("owner", "repo", "file", **arguments)
    assert client.calls == []


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("content", ["", "AP+A\r\n", "YmluYXJ5", "caller validates Base64"])
def test_content_is_preserved_without_encoding_or_entry_point_policy(operation, content):
    client = RecordingClient()
    arguments = {**_arguments(operation), "content": content}
    getattr(FileService(client), operation)("owner", "repo", "file", **arguments)
    assert client.calls[0][3]["content"] == content


@pytest.mark.parametrize("operation", ["create", "update"])
def test_content_must_be_a_string(operation):
    client = RecordingClient()
    with pytest.raises(ValueError):
        getattr(FileService(client), operation)("owner", "repo", "file", **{**_arguments(operation), "content": None})
    assert client.calls == []


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("sha", ["", "a" * 39, "a" * 41, "g" * 40, "a" * 40 + "\n", None, True])
def test_expected_blob_sha_syntax_is_required_without_lookup(operation, sha):
    client = RecordingClient()
    with pytest.raises(ValueError):
        getattr(FileService(client), operation)("owner", "repo", "file", **{**_arguments(operation), "sha": sha})
    assert client.calls == []


@pytest.mark.parametrize("operation", ["get", "create", "update", "delete"])
def test_transport_errors_pass_through_without_lookup_or_retry(operation):
    client = RecordingClient()
    client.error = RuntimeError("transport owns outcome semantics")
    with pytest.raises(RuntimeError) as raised:
        getattr(FileService(client), operation)("owner", "repo", "file", **_arguments(operation))
    assert raised.value is client.error
    assert len(client.calls) == 1


@pytest.mark.parametrize("operation", ["get", "create", "update", "delete"])
@pytest.mark.parametrize("response", [None, {}, [], {"commit": {"sha": SHA}}])
def test_response_is_not_interpreted_or_supplemented(operation, response):
    client = RecordingClient()
    client.result = response
    assert getattr(FileService(client), operation)("owner", "repo", "file", **_arguments(operation)) is response
    assert len(client.calls) == 1
