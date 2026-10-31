"""Offline contracts for the transport producer, without adopting it in clients."""

import gzip
from contextlib import contextmanager
from enum import IntEnum

import httpx
import pytest

from gitcode_cli.transport import ResponseTooLargeError, read_response_bytes


class TrackedStream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.reads = 0
        self.closed = False

    def __iter__(self):
        for chunk in self.chunks:
            self.reads += 1
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.closed = True


@contextmanager
def streamed_response(chunks, *, headers=None, status=200):
    stream = TrackedStream(chunks)
    transport = httpx.MockTransport(lambda _: httpx.Response(status, headers=headers, stream=stream))
    with httpx.Client(transport=transport, trust_env=False) as client:
        with client.stream("GET", "https://transport.invalid/resource") as response:
            yield response, stream


@pytest.mark.parametrize(
    ("chunks", "limit", "expected"),
    [
        ([], 1, b""),
        ([b""], 1, b""),
        ([b"a"], 1, b"a"),
        ([b"a", b"bc"], 3, b"abc"),
        ([b"ab", b"", b"c"], 4, b"abc"),
        ([b"\xff", b"\x00"], 2, b"\xff\x00"),
        ([b"a" * 65_536, b"b"], 65_537, b"a" * 65_536 + b"b"),
        ([b"a" * 65_537, b"b"], None, b"a" * 65_537 + b"b"),
    ],
)
def test_empty_exact_limit_multichunk_and_unlimited_bodies(chunks, limit, expected):
    with streamed_response(chunks) as (response, stream):
        assert read_response_bytes(response, max_response_bytes=limit) == expected
    assert stream.closed


@pytest.mark.parametrize(
    ("chunks", "limit"),
    [
        ([b"abcd", b"unread"], 3),
        ([b"ab", b"cd", b"unread"], 3),
        ([b"a" * 65_537, b"unread"], 65_536),
    ],
)
def test_overflow_returns_no_partial_body_and_stops_before_later_chunks(chunks, limit):
    with streamed_response(chunks) as (response, stream):
        with pytest.raises(ResponseTooLargeError) as raised:
            read_response_bytes(response, max_response_bytes=limit)
        assert stream.reads == len(chunks) - 1
        assert raised.value.args == ("Response exceeds the configured byte limit.",)
        assert vars(raised.value) == {}
    assert stream.closed


@pytest.mark.parametrize("limit", [3, 65_536, 100_000])
def test_one_overflow_byte_is_detected_before_a_later_stream_error(limit):
    failure = httpx.ReadError("This chunk must not be consumed")
    with streamed_response([b"a" * limit, b"b", failure]) as (response, stream):
        with pytest.raises(ResponseTooLargeError):
            read_response_bytes(response, max_response_bytes=limit)
        assert stream.reads == 2
    assert stream.closed


class IntegerSubclass(int):
    pass


class LimitEnum(IntEnum):
    ONE = 1


@pytest.mark.parametrize("limit", [0, -1, True, False, 1.0, float("inf"), "1", [], IntegerSubclass(1), LimitEnum.ONE])
def test_invalid_limits_fail_before_consuming_the_response(limit):
    with streamed_response([b"not read"]) as (response, stream):
        with pytest.raises(ValueError, match="positive built-in int or None"):
            read_response_bytes(response, max_response_bytes=limit)
        assert stream.reads == 0
    assert stream.closed


def test_limit_is_explicit_not_an_implicit_unbounded_default():
    with streamed_response([b"not read"]) as (response, stream):
        with pytest.raises(TypeError):
            read_response_bytes(response)
        assert stream.reads == 0
    assert stream.closed


@pytest.mark.parametrize("declared_length", [None, "1", "999999"])
def test_content_length_does_not_replace_counting_decoded_bytes(declared_length):
    headers = {} if declared_length is None else {"Content-Length": declared_length}
    with streamed_response([b"abcd"], headers=headers) as (response, stream):
        with pytest.raises(ResponseTooLargeError):
            read_response_bytes(response, max_response_bytes=3)
    assert stream.closed


def test_compressed_body_is_limited_after_content_decoding():
    encoded = gzip.compress(b"a" * 1000)
    assert len(encoded) < 100
    headers = {"Content-Encoding": "gzip", "Content-Length": str(len(encoded))}
    with streamed_response([encoded], headers=headers) as (response, stream):
        with pytest.raises(ResponseTooLargeError):
            read_response_bytes(response, max_response_bytes=100)
    assert stream.closed


def test_status_and_json_are_not_interpreted():
    with streamed_response([b"not JSON"], status=503) as (response, stream):
        assert read_response_bytes(response, max_response_bytes=100) == b"not JSON"
    assert stream.closed


def test_stream_error_propagates_unchanged_without_retry_or_helper_logging(caplog):
    failure = httpx.ReadError("synthetic-upstream-error-never-display")
    with streamed_response([b"a", failure, b"unread"]) as (response, stream):
        with pytest.raises(httpx.ReadError) as raised:
            read_response_bytes(response, max_response_bytes=100)
        assert raised.value is failure
        assert stream.reads == 2
    assert stream.closed
    assert str(failure) not in caplog.text


def test_overflow_exception_has_no_response_fields_or_echoed_data(caplog):
    secret = b"synthetic-body-secret"
    with streamed_response([secret]) as (response, stream):
        with pytest.raises(ResponseTooLargeError) as raised:
            read_response_bytes(response, max_response_bytes=1)
        error = raised.value
        assert vars(error) == {}
        assert secret.decode() not in str(error) + repr(error) + repr(error.args) + caplog.text
        assert not hasattr(error, "response")
        assert not hasattr(error, "request")
        assert not hasattr(error, "content")
    assert stream.closed
