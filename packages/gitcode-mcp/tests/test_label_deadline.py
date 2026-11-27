"""Whole scan cancellation: synthetic transports only."""

import anyio
import httpx
import pytest

from gitcode_mcp.api import GitCodeAPI, GitCodeError
from gitcode_mcp.label_catalog import label_page_async

PATH = "/repos/Team/r/labels"


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Drip(httpx.AsyncByteStream):
    def __init__(self):
        self.iterations = 0
        self.closed = False
        self.ended = False

    async def __aiter__(self):
        try:
            while True:
                self.iterations += 1
                yield b" "
                await anyio.sleep(0.005)
        finally:
            self.ended = True

    async def aclose(self):
        self.closed = True


@pytest.mark.anyio
@pytest.mark.parametrize("delay", ("first-headers", "later-headers", "later-body"))
async def test_one_deadline_cancels_headers_or_dripping_body_without_advance(delay):
    calls = []
    active = 0
    ended = 0
    drip = Drip()

    async def handle(req):
        nonlocal active, ended
        assert req.method == "GET"
        assert req.url.host == "api.gitcode.com" and req.url.path == "/api/v5" + PATH
        assert not {"cookie", "private-token"} & set(req.headers)
        assert req.headers["Authorization"] == "Bearer fixture-only"
        assert req.headers["Accept-Encoding"] == "identity"
        n = int(req.url.params["page"])
        calls.append(n)
        active += 1
        try:
            if delay == "first-headers" or (delay == "later-headers" and n == 2):
                await anyio.sleep_forever()
            if n == 1:
                return httpx.Response(
                    200, json=[{"id": 1, "name": "one"}], headers={"set-cookie": "a=b; Path=/"}
                )
            if delay == "later-body" and n == 2:
                return httpx.Response(
                    200, stream=drip, headers={"Content-Type": "application/json"}
                )
            pytest.fail(f"unexpected request {n}")
        finally:
            active -= 1
            ended += 1

    with GitCodeAPI("fixture-only", timeout=0.09, transport=httpx.MockTransport(handle)) as api:
        with anyio.fail_after(0.7), pytest.raises(GitCodeError) as failure:
            await label_page_async(api, PATH, page=1, per_page=2)
        assert failure.value.code == "timeout"
    assert calls == ([1] if delay == "first-headers" else [1, 2])
    assert active == 0 and ended == len(calls)
    if delay == "later-body":
        assert drip.iterations >= 2 and drip.closed and drip.ended


@pytest.mark.anyio
async def test_budget_is_not_restarted_between_individually_fast_pages():
    calls = []

    async def handle(req):
        n = int(req.url.params["page"])
        calls.append(n)
        await anyio.sleep(0.045)
        return httpx.Response(200, json=[{"id": n, "name": str(n)}] if n < 3 else [])

    with GitCodeAPI("fixture-only", timeout=0.115, transport=httpx.MockTransport(handle)) as api:
        with anyio.fail_after(0.9), pytest.raises(GitCodeError) as failure:
            await label_page_async(api, PATH, page=1, per_page=2)
        assert failure.value.code == "timeout"
    assert calls == [1, 2, 3]


@pytest.mark.anyio
async def test_proof_of_terminal_empty_page_is_required_and_uses_no_redirect():
    async def handle(req):
        n = int(req.url.params["page"])
        if n == 1:
            return httpx.Response(200, json=[{"id": 1, "name": "one"}], headers={"X-Total": "1"})
        if n == 2:
            return httpx.Response(302, headers={"Location": "https://never.example.test/"})
        pytest.fail("a provider location was used")

    with GitCodeAPI("fixture-only", transport=httpx.MockTransport(handle)) as api:
        with pytest.raises(GitCodeError) as failure:
            await label_page_async(api, PATH, page=1, per_page=2)
        assert failure.value.code == "upstream_redirect"


@pytest.mark.anyio
async def test_async_catalog_matches_legacy_result_and_uncertain_pages_fail_closed():
    def run(req):
        n = int(req.url.params["page"])
        rows = [{"id": 1, "name": "one"}] if n == 1 else []
        return httpx.Response(200, json=rows, headers={"X-Total": "1"})

    with GitCodeAPI("fixture-only", transport=httpx.MockTransport(run)) as api:
        result = await label_page_async(api, PATH, page=2, per_page=1)
    assert result["data"] == []
    assert result["total_items"] == 1
    assert result["next_page"] is None
