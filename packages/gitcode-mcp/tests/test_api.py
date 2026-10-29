import json

import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError

SECRET = "test-private-token-do-not-return"


def test_bearer_auth_and_upstream_service_contract():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"number": "23", "title": "Example"})

    with GitCodeAPI(SECRET, transport=httpx.MockTransport(handler)) as api:
        result = api.issues.create("team", "repo", title="Example", body="Description")

    request = requests[0]
    assert request.url == "https://api.gitcode.com/api/v5/repos/team/issues"
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in str(request.url)
    assert json.loads(request.content) == {
        "repo": "repo",
        "title": "Example",
        "body": "Description",
    }
    assert result["number"] == "23"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (404, "not_found"),
        (409, "conflict"),
        (422, "upstream_validation"),
        (429, "rate_limited"),
        (500, "upstream_error"),
    ],
)
def test_http_errors_are_safe_and_writes_are_not_retried(status, code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, json={"message": f"upstream echoed {SECRET}"}, headers={"Retry-After": "27"}
        )

    with GitCodeAPI(SECRET, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            api.pulls.create("team", "repo", title="Example", head="feature", base="main")

    assert len(requests) == 1
    assert raised.value.code == code
    assert raised.value.status_code == status
    assert SECRET not in str(raised.value)
    assert SECRET not in json.dumps(raised.value.to_dict())
    if status == 500:
        assert raised.value.to_dict()["operation_may_have_completed"] is True
    else:
        assert "operation_may_have_completed" not in raised.value.to_dict()
    if status == 429:
        assert raised.value.retry_after == 27


def test_redirect_is_not_followed_and_does_not_forward_auth():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": f"https://other.example/{SECRET}"})

    with GitCodeAPI(SECRET, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError, match="redirect") as raised:
            api.get("/repos/team/repo")
    assert raised.value.code == "upstream_redirect"
    assert len(requests) == 1
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_error_never_exposes_exception_message(error_type):
    def handler(request):
        raise error_type(f"credentials in exception: {SECRET}", request=request)

    with GitCodeAPI(SECRET, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            api.get("/repos/team/repo")
    assert raised.value.code in {"timeout", "network_error"}
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize("body", [b"x" * 101, b'[{"large":"' + b"x" * 100 + b'"}]'])
def test_response_size_limit_never_silently_truncates(body):
    with GitCodeAPI(
        SECRET,
        max_response_bytes=100,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body)),
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            api.get("/repos/team/repo")
    assert raised.value.code == "response_too_large"


def test_success_response_redacts_accidentally_reflected_credential():
    with GitCodeAPI(
        SECRET,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"a": [SECRET, {"body": f"echo {SECRET}"}]})
        ),
    ) as api:
        result = api.get("/repos/team/repo")
    assert SECRET not in json.dumps(result)
    assert result["a"][0] == "[REDACTED]"


def test_missing_credential_fails_before_network():
    def handler(_):
        pytest.fail("Unauthenticated calls must not reach the network")

    with GitCodeAPI("", transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            api.get("/repos/team/repo")
    assert raised.value.code == "configuration_error"


@pytest.mark.parametrize(
    "path",
    [
        "https://other.example/",
        "//other.example/",
        "/repos/team/../user",
        "/repos/team/%2e%2e/user",
        "/repos/team/repo?access_token=oops",
    ],
)
def test_client_refuses_non_repository_or_traversal_paths(path):
    with GitCodeAPI(
        SECRET, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            api.get(path)
    assert raised.value.code == "invalid_path"


def test_query_credentials_are_rejected():
    with GitCodeAPI(
        SECRET, transport=httpx.MockTransport(lambda _: pytest.fail("unexpected request"))
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            api.get("/repos/team/repo", params={"access_token": "another-secret"})
    assert raised.value.code == "invalid_arguments"


def test_invalid_success_json_is_a_safe_error():
    with GitCodeAPI(
        SECRET,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=f"not JSON {SECRET}")),
    ) as api:
        with pytest.raises(GitCodeError) as raised:
            api.get("/repos/team/repo")
    assert raised.value.code == "invalid_response"
    assert SECRET not in str(raised.value)


def test_page_does_not_fetch_or_claim_an_unseen_page():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[{"id": 1}, {"id": 2}])

    with GitCodeAPI(SECRET, transport=httpx.MockTransport(handler)) as api:
        result = api.page("/repos/team/repo/issues", page=3, per_page=2)
    assert len(requests) == 1
    assert result["next_page"] == 4
    assert requests[0].url.params["page"] == "3"
    assert requests[0].url.params["per_page"] == "2"
    assert "can be empty" in result["pagination_note"]


def test_overfull_page_is_rejected_rather_than_silently_sliced():
    with pytest.raises(GitCodeError):
        GitCodeAPI.page_result([1, 2, 3], page=1, per_page=2)


@pytest.mark.parametrize("method", ["POST", "GET"])
@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        ("timeout", "timeout"),
        ("connection_error", "network_error"),
        ("redirect", "upstream_redirect"),
        ("server_error", "upstream_error"),
        ("unavailable", "upstream_error"),
        ("invalid_json", "invalid_response"),
        ("invalid_unicode_json", "invalid_response"),
        ("invalid_unicode_text", "invalid_response"),
        ("oversized", "response_too_large"),
    ],
)
def test_uncertain_outcomes_are_reported_only_for_writes_without_retrying(
    method, outcome, expected_code
):
    requests = []
    file_content = "private-file-content-never-return-in-errors"
    reflected = f"{SECRET} {file_content}"

    def handler(request):
        requests.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout(reflected, request=request)
        if outcome == "connection_error":
            raise httpx.ConnectError(reflected, request=request)
        if outcome == "redirect":
            return httpx.Response(302, headers={"Location": f"https://other.example/{SECRET}"})
        if outcome in {"server_error", "unavailable"}:
            return httpx.Response(
                500 if outcome == "server_error" else 503, json={"message": reflected}
            )
        if outcome == "invalid_json":
            return httpx.Response(201, content=reflected)
        if outcome.startswith("invalid_unicode"):
            return httpx.Response(201, content=b"\xff" + reflected.encode())
        assert outcome == "oversized"
        return httpx.Response(201, content=(reflected * 10).encode())

    with GitCodeAPI(SECRET, max_response_bytes=128, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            api.request(
                method,
                "/repos/team/repo/contents/file.txt",
                json={"content": file_content} if method == "POST" else None,
                response_format="text" if outcome == "invalid_unicode_text" else "json",
            )

    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == f"Bearer {SECRET}"
    error = raised.value
    assert error.code == expected_code
    serialized = json.dumps(error.to_dict())
    assert SECRET not in serialized
    assert file_content not in serialized
    assert SECRET not in str(error)
    assert file_content not in str(error)
    if method == "POST":
        assert error.to_dict()["operation_may_have_completed"] is True
        assert "write may have completed" in error.message
        assert "Verify remote state" in error.message
        assert "do not automatically retry" in error.message
    else:
        assert "operation_may_have_completed" not in error.to_dict()
        assert "write may have completed" not in error.message


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "post"])
def test_all_mutation_methods_report_uncertain_server_outcomes(method):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(502, json={"message": SECRET})

    with GitCodeAPI(SECRET, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(GitCodeError) as raised:
            api.request(method, "/repos/team/repo/contents/file.txt")

    assert len(requests) == 1
    assert raised.value.code == "upstream_error"
    assert raised.value.status_code == 502
    assert raised.value.operation_may_have_completed is True
    assert SECRET not in str(raised.value)


def test_legacy_error_payload_does_not_gain_outcome_metadata():
    error = GitCodeError("invalid_arguments", "Invalid input.")
    assert error.to_dict() == {"code": "invalid_arguments", "message": "Invalid input."}
