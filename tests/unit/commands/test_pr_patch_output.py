"""Patch output is lossless data, not terminal-renderable text."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main

PATCH_HEADER = "From " + "1" * 40 + " Mon Sep 17 00:00:00 2001\n"


@pytest.fixture
def patch_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("gitcode_cli.context.AppContext.client", lambda self: client)
    return client


def _runner():
    if "mix_stderr" in inspect.signature(CliRunner.__init__).parameters:
        return CliRunner(mix_stderr=False)
    return CliRunner()


@pytest.mark.parametrize(
    "body",
    [
        "+\x1b[31mred\x1b[0m\n",
        "+\x1b]0;untrusted title\x07\n",
        "+\x1b]52;c;dW50cnVzdGVk\x1b\\\n",
        "+Unicode 雪\r\n+\x1b[2J\r\n",
        "+\x1b[31mno trailing newline",
    ],
)
def test_redirected_patch_preserves_control_bytes_and_newlines(patch_client, body):
    patch_text = PATCH_HEADER + body
    patch_client.request.return_value = patch_text

    result = _runner().invoke(
        main, ["--token", "synthetic-patch-token", "pr", "diff", "42", "-R", "owner/repo", "--patch"]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == patch_text.encode("utf-8")
    assert result.stderr_bytes == b""
    patch_client.request.assert_called_once_with(
        "GET", "/repos/owner/repo/pulls/42/patch", accept="text/plain", response_format="text"
    )


@pytest.mark.parametrize("body", ["+plain\n", "+\x1b[31mred\x1b[0m\n", "+\x1b]52;c;dW50cnVzdGVk\x07\n"])
def test_patch_rejects_terminal_without_writing_any_patch_bytes(patch_client, monkeypatch, body):
    patch_client.request.return_value = PATCH_HEADER + body
    terminal = MagicMock()
    terminal.isatty.return_value = True
    monkeypatch.setattr("gitcode_cli.commands.pr.click.get_binary_stream", lambda name: terminal)

    result = _runner().invoke(
        main, ["--token", "synthetic-patch-token", "pr", "diff", "42", "-R", "owner/repo", "--patch"]
    )

    assert result.exit_code == 1
    assert result.stdout_bytes == b""
    assert b"--patch requires redirected stdout" in result.stderr_bytes
    assert b"\x1b" not in result.stderr_bytes
    terminal.write.assert_not_called()
    terminal.flush.assert_not_called()
    patch_client.request.assert_not_called()
