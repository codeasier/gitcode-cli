"""Synthetic OAuth input preflight contracts: no broker, credentials or native vault."""

from __future__ import annotations

import builtins
import hashlib
import os
import shutil
import socket
import ssl
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock

import pytest

from gitcode_cli import oauth_web_inputs as entry
from gitcode_cli.errors import AuthError
from gitcode_cli.oauth_broker_client import BrokerTrust, _broker_context

_LOGIN = "Exact.User_Name"
_ORIGIN = "https://broker.example.invalid:8443"
_BAD = "DO-NOT-ECHO"


def _prepare(pem=b"fixture", **options):
    spec = {
        "expected_login": _LOGIN,
        "broker_origin": _ORIGIN,
        "ca_pem": pem,
        "ca_sha256": hashlib.sha256(pem).hexdigest(),
        **options,
    }
    return entry.prepare_oauth_web_inputs(**spec)


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    if any(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).cert_store_stats().values()):
        pytest.skip("this runtime pre-seeds broker TLS contexts; trust must fail closed")
    executable = shutil.which("openssl")
    if executable is None:
        pytest.skip("generating a disposable CA and non-CA requires openssl")
    directory = tmp_path_factory.mktemp("oauth-input-pki")
    for name, constraints in (("ca", "TRUE"), ("leaf", "FALSE")):
        subprocess.run(
            [
                executable,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=fixture",
                "-addext",
                f"basicConstraints=critical,CA:{constraints}",
                "-keyout",
                f"{name}.key",
                "-out",
                f"{name}.pem",
            ],
            cwd=directory,
            timeout=20,
            check=True,
            capture_output=True,
        )
    return directory


def test_real_ca_uses_exact_bytes_on_portable_entry_without_ambient_trust(pki, monkeypatch):
    source = (pki / "ca.pem").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    deny = Mock(side_effect=AssertionError("environment CA files, network, and fallback are unavailable"))
    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(os, "open", deny)
    monkeypatch.setattr(Path, "open", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setenv("SSL_CERT_FILE", f"{_BAD}.pem")
    monkeypatch.setenv("SSLKEYLOGFILE", f"{_BAD}.log")
    monkeypatch.setenv("GC_TOKEN", _BAD)
    result = _prepare(source, ca_sha256=hashlib.sha256(source).hexdigest().upper())
    assert result.expected_login == _LOGIN
    assert result.broker_trust == BrokerTrust(_ORIGIN, source.decode("ascii"))
    assert _broker_context(_ORIGIN, result.broker_trust).cert_store_stats()["x509_ca"] == 1
    deny.assert_not_called()
    with pytest.raises(FrozenInstanceError):
        result.expected_login = "other"
    with pytest.raises(FrozenInstanceError):
        result.broker_trust.origin = "https://other.invalid"


def test_portable_gate_validates_result_with_exact_pin_and_no_os_or_network(monkeypatch):
    validate = Mock()
    deny = Mock(side_effect=AssertionError("unexpected OS or network operation"))
    source = b"x" * 16_384
    monkeypatch.setattr(entry, "_broker_context", validate)
    monkeypatch.setattr(builtins, "open", deny)
    monkeypatch.setattr(os, "open", deny)
    monkeypatch.setattr(Path, "open", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "socket", deny)
    result = _prepare(source)
    assert result.expected_login == _LOGIN
    assert result.broker_trust == BrokerTrust(_ORIGIN, source.decode("ascii"))
    validate.assert_called_once_with(_ORIGIN, result.broker_trust)
    deny.assert_not_called()


def test_native_trust_failure_does_not_leak_input_or_fall_back(monkeypatch):
    validating = Mock(side_effect=OSError(_BAD))
    monkeypatch.setattr(entry, "_broker_context", validating)
    with pytest.raises(AuthError, match="one valid CA") as error:
        _prepare()
    assert error.value.__context__ is None
    assert _BAD not in str(error.value)
    validating.assert_called_once()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("expected_login", None),
        ("expected_login", 1),
        ("expected_login", ".."),
        ("expected_login", "Exact/User"),
        ("expected_login", " " + _LOGIN),
        ("expected_login", _LOGIN + " "),
        ("expected_login", "姓"),
        ("broker_origin", None),
        ("broker_origin", 1),
        ("broker_origin", "http://broker.example.invalid"),
        ("broker_origin", _ORIGIN + "/"),
        ("broker_origin", _ORIGIN + "?"),
        ("broker_origin", _ORIGIN + "#"),
        ("broker_origin", _ORIGIN + "?key=" + _BAD),
        ("broker_origin", "https://Broker.example.invalid"),
        ("broker_origin", "https://broker.example.invalid:443"),
        ("broker_origin", "https://x@broker.example.invalid"),
        ("broker_origin", "https://broker.example.invalid:-1"),
        ("broker_origin", "https://127.000.0.1"),
        ("broker_origin", "https://localhost\r@broker.example.invalid"),
        ("broker_origin", "https://localhost:65536"),
        ("broker_origin", "https://broker.example.invalid."),
        ("ca_sha256", None),
        ("ca_sha256", 1),
        ("ca_sha256", b"0" * 64),
        ("ca_sha256", "0" * 63),
        ("ca_sha256", "0" * 65),
        ("ca_sha256", "g" * 64),
        ("ca_sha256", " " + "0" * 64),
        ("ca_sha256", ":".join("00" for _ in range(32))),
        ("ca_pem", None),
        ("ca_pem", "pem"),
        ("ca_pem", bytearray(b"fixture")),
        ("ca_pem", memoryview(b"fixture")),
        ("ca_pem", b""),
        ("ca_pem", b"a" * 16_385),
    ],
)
def test_reject_invalid_types_and_untrusted_spelling_without_ca_parsing(monkeypatch, key, value):
    forbidden = Mock(side_effect=AssertionError("CA was parsed without complete input validation"))
    monkeypatch.setattr(entry, "_broker_context", forbidden)
    with pytest.raises(AuthError) as error:
        _prepare(**{key: value})
    assert error.value.__context__ is None
    assert _BAD not in str(error.value)
    forbidden.assert_not_called()


def test_pin_checked_before_ca_parser_and_normalization(monkeypatch):
    root = b"-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n"
    forbidden = Mock(side_effect=AssertionError("CA was parsed despite incorrect exact bytes"))
    monkeypatch.setattr(entry, "_broker_context", forbidden)
    with pytest.raises(AuthError, match="does not match"):
        _prepare(root, ca_sha256=hashlib.sha256(root.rstrip(b"\n")).hexdigest())
    with pytest.raises(AuthError, match="does not match"):
        _prepare(root, ca_sha256=hashlib.sha256(root.replace(b"\n", b"\r\n")).hexdigest())
    forbidden.assert_not_called()


@pytest.mark.parametrize("kind", ["leaf", "multiple", "private", "bad_der", "embedded_null", "non_ascii", "empty_cert"])
def test_matching_fingerprint_is_not_sufficient_for_tls_trust(pki, kind):
    ca = (pki / "ca.pem").read_bytes()
    material = {
        "leaf": (pki / "leaf.pem").read_bytes(),
        "multiple": ca + ca,
        "private": (pki / "ca.key").read_bytes(),
        "bad_der": b"-----BEGIN CERTIFICATE-----\nYQ==\n-----END CERTIFICATE-----\n",
        "embedded_null": ca + b"\0",
        "non_ascii": ca + b"\xff",
        "empty_cert": b"-----BEGIN CERTIFICATE-----\n-----END CERTIFICATE-----\n",
    }[kind]
    with pytest.raises(AuthError, match="one valid CA") as error:
        _prepare(material)
    assert error.value.__context__ is None
    assert "BEGIN" not in str(error.value)


def test_caller_supplies_expected_login_and_origin_never_discovered_from_environment(monkeypatch):
    monkeypatch.setenv("GC_TOKEN", _BAD)
    monkeypatch.setenv("GC_OAUTH_BROKER_ORIGIN", _ORIGIN)
    monkeypatch.setenv("GC_OAUTH_EXPECTED_LOGIN", _LOGIN)
    with pytest.raises(AuthError, match="explicit valid"):
        _prepare(expected_login="")
    with pytest.raises(AuthError, match="canonical HTTPS"):
        _prepare(broker_origin="")
