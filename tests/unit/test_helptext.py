"""Tests for gitcode_cli.helptext helpers."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.helptext import _argument_metavar


class TestArgumentMetavar:
    def test_uses_ctx_when_make_metavar_accepts_context(self):
        param = click.Argument(["identifier"], required=False)
        ctx = click.Context(click.Command("view"))

        assert _argument_metavar(param, ctx) == "[IDENTIFIER]"

    def test_uses_no_arg_make_metavar_when_signature_is_empty(self):
        param = click.Argument(["identifier"])
        param.make_metavar = lambda: "IDENT"  # type: ignore[method-assign]
        ctx = click.Context(click.Command("view"))

        assert _argument_metavar(param, ctx) == "IDENT"

    def test_falls_back_when_make_metavar_is_missing(self):
        param = click.Argument(["identifier"])
        param.make_metavar = None  # type: ignore[assignment]
        ctx = click.Context(click.Command("view"))

        assert _argument_metavar(param, ctx) == "identifier"

    def test_falls_back_when_signature_cannot_be_inspected(self, monkeypatch):
        param = click.Argument(["identifier"])
        ctx = click.Context(click.Command("view"))

        def boom(_obj: object) -> object:
            raise TypeError("no signature")

        monkeypatch.setattr("gitcode_cli.helptext.inspect.signature", boom)
        assert _argument_metavar(param, ctx) == "identifier"

    def test_propagates_type_error_from_make_metavar_body(self):
        param = click.Argument(["identifier"])

        def boom(ctx: click.Context) -> str:
            raise TypeError("internal metavar failure")

        param.make_metavar = boom  # type: ignore[method-assign]
        ctx = click.Context(click.Command("view"))

        with pytest.raises(TypeError, match="internal metavar failure"):
            _argument_metavar(param, ctx)

    def test_pr_view_help_usage_renders_identifier_metavar(self):
        result = CliRunner().invoke(main, ["pr", "view", "--help"])

        assert result.exit_code == 0
        assert "USAGE\n  gc pr view [IDENTIFIER] [flags]" in result.output
        assert "baseRefOid" in result.output
        assert "headRefOid" in result.output
