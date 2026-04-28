"""Tests for gitcode_cli.formatters module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import click
import pytest

from gitcode_cli.formatters import (
    _filter_fields,
    apply_jq,
    dump_json,
    format_issue_detail,
    format_issue_list,
    format_pr_detail,
    format_pr_list,
    output_result,
    render_template,
)


class TestDumpJson:
    def test_without_fields(self):
        data = {"id": 1, "title": "Test"}
        result = dump_json(data)
        parsed = json.loads(result)
        assert parsed == {"id": 1, "title": "Test"}

    def test_with_fields(self):
        data = {"id": 1, "title": "Test", "body": "Body"}
        result = dump_json(data, fields=["id", "title"])
        parsed = json.loads(result)
        assert parsed == {"id": 1, "title": "Test"}

    def test_with_nested_fields(self):
        data = {"id": 1, "user": {"login": "alice", "id": 99}}
        result = dump_json(data, fields=["id", "user.login"])
        parsed = json.loads(result)
        assert parsed == {"id": 1, "user.login": "alice"}

    def test_list_without_fields(self):
        data = [{"id": 1}, {"id": 2}]
        result = dump_json(data)
        parsed = json.loads(result)
        assert parsed == [{"id": 1}, {"id": 2}]

    def test_list_with_fields(self):
        data = [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]
        result = dump_json(data, fields=["id"])
        parsed = json.loads(result)
        assert parsed == [{"id": 1}, {"id": 2}]

    def test_ensure_ascii_false(self):
        data = {"title": "中文"}
        result = dump_json(data)
        assert "中文" in result


class TestFilterFields:
    def test_simple_fields(self):
        item = {"id": 1, "title": "Test", "body": "Body"}
        assert _filter_fields(item, ["id", "title"]) == {"id": 1, "title": "Test"}

    def test_nested_field(self):
        item = {"user": {"login": "alice", "id": 99}}
        assert _filter_fields(item, ["user.login"]) == {"user.login": "alice"}

    def test_deeply_nested_field(self):
        item = {"a": {"b": {"c": "deep"}}}
        assert _filter_fields(item, ["a.b.c"]) == {"a.b.c": "deep"}

    def test_nested_field_missing_intermediate(self):
        item = {"user": "string"}
        assert _filter_fields(item, ["user.login"]) == {"user.login": None}

    def test_missing_field(self):
        item = {"id": 1}
        assert _filter_fields(item, ["missing"]) == {"missing": None}

    def test_field_without_dot(self):
        item = {"simple": "value"}
        assert _filter_fields(item, ["simple"]) == {"simple": "value"}


class TestRenderTemplate:
    def test_simple_field(self):
        data = {"title": "Hello", "id": 1}
        result = render_template(data, "{{.title}}")
        assert result == "Hello"

    def test_nested_field(self):
        data = {"user": {"login": "alice"}}
        result = render_template(data, "{{.user.login}}")
        assert result == "alice"

    def test_nested_field_intermediate_not_dict(self):
        data = {"user": "string"}
        result = render_template(data, "{{.user.login}}")
        assert result == ""

    def test_multiple_placeholders(self):
        data = {"title": "Hello", "body": "World"}
        result = render_template(data, "{{.title}}: {{.body}}")
        assert result == "Hello: World"

    def test_missing_field_returns_empty(self):
        data = {"title": "Hello"}
        result = render_template(data, "{{.missing}}")
        assert result == ""

    def test_non_dict_data(self):
        result = render_template("not a dict", "{{.key}}")
        assert result == ""

    def test_no_placeholders(self):
        data = {"title": "Hello"}
        result = render_template(data, "no placeholders")
        assert result == "no placeholders"


class TestListAndDetailFormatters:
    def test_format_issue_list_includes_author_when_available(self):
        items = [
            {"number": "12", "state": "open", "title": "Fix login", "author": {"login": "alice"}},
            {"number": "13", "state": "closed", "title": "Tidy docs"},
        ]

        assert format_issue_list(items).splitlines() == [
            "#12\topen\tFix login\talice",
            "#13\tclosed\tTidy docs\t",
        ]

    def test_format_pr_list_includes_author_when_available(self):
        items = [
            {"number": 7, "state": "open", "title": "Add feature", "user": {"login": "bob"}},
        ]

        assert format_pr_list(items) == "#7\topen\tAdd feature\tbob"

    def test_format_issue_detail_includes_metadata_lines(self):
        item = {
            "number": "42",
            "title": "Investigate timeout",
            "state": "open",
            "author": {"login": "alice"},
            "created_at": "2026-04-24T12:00:00Z",
            "body": "Issue body",
        }

        result = format_issue_detail(item)

        assert "Title:\tInvestigate timeout" in result
        assert "State:\topen" in result
        assert "Author:\talice" in result
        assert "Body:\nIssue body" in result

    def test_format_pr_detail_includes_branch_metadata_lines(self):
        item = {
            "number": 101,
            "title": "Ship formatter upgrade",
            "state": "open",
            "user": {"login": "carol"},
            "head": {"label": "carol:task-7", "ref": "task-7"},
            "base": {"label": "owner:main", "ref": "main"},
            "body": "PR body",
        }

        result = format_pr_detail(item)

        assert "Title:\tShip formatter upgrade" in result
        assert "State:\topen" in result
        assert "Author:\tcarol" in result
        assert "Branch:\tcarol:task-7 -> owner:main" in result
        assert "Body:\nPR body" in result


class TestOutputResult:
    def test_json_fields(self, capsys):
        data = {"id": 1, "title": "Test"}
        output_result(data, json_fields="id,title", jq_query=None, template=None, default_formatter=lambda x: None)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"id": 1, "title": "Test"}

    def test_template_single_item(self, capsys):
        data = {"title": "Hello"}
        output_result(data, json_fields=None, jq_query=None, template="{{.title}}", default_formatter=lambda x: None)
        captured = capsys.readouterr()
        assert captured.out.strip() == "Hello"

    def test_template_list(self, capsys):
        data = [{"title": "A"}, {"title": "B"}]
        output_result(data, json_fields=None, jq_query=None, template="{{.title}}", default_formatter=lambda x: None)
        captured = capsys.readouterr()
        assert captured.out.strip().splitlines() == ["A", "B"]

    def test_default_formatter_called(self):
        mock_formatter = MagicMock()
        data = {"id": 1}
        output_result(data, json_fields=None, jq_query=None, template=None, default_formatter=mock_formatter)
        mock_formatter.assert_called_once_with(data)

    def test_jq_query(self, capsys, mocker):
        mock_apply_jq = mocker.patch("gitcode_cli.formatters.apply_jq", return_value=[{"id": 1}])
        data = {"items": [{"id": 1}]}
        output_result(data, json_fields=None, jq_query=".items[]", template=None, default_formatter=lambda x: None)
        captured = capsys.readouterr()
        mock_apply_jq.assert_called_once_with(data, ".items[]")
        assert json.loads(captured.out) == [{"id": 1}]


class TestApplyJq:
    def test_pyjq_import_success(self, mocker):
        mock_jq_module = MagicMock()
        mock_compile = MagicMock()
        mock_compile.input.return_value.all.return_value = [{"id": 1}]
        mock_jq_module.compile.return_value = mock_compile
        mocker.patch.dict("sys.modules", {"jq": mock_jq_module})
        result = apply_jq({"id": 1}, ".id")
        assert result == [{"id": 1}]

    def test_jq_cli_success(self, mocker):
        mocker.patch.dict("sys.modules", {"jq": None})
        mock_run = mocker.patch("gitcode_cli.formatters.subprocess.run")
        mock_run.return_value = MagicMock(stdout='[{"id":1}]')
        mocker.patch("gitcode_cli.formatters.shutil.which", return_value="/usr/bin/jq")
        result = apply_jq({"id": 1}, ".id")
        assert result == [{"id": 1}]

    def test_jq_not_available_raises_click_exception(self, mocker):
        mocker.patch.dict("sys.modules", {"jq": None})
        mocker.patch("gitcode_cli.formatters.shutil.which", return_value=None)
        with pytest.raises(click.ClickException, match="jq is required"):
            apply_jq({"id": 1}, ".id")

    def test_import_error_and_no_jq_bin(self, mocker):
        mocker.patch.dict("sys.modules", {"jq": None})
        mocker.patch("gitcode_cli.formatters.shutil.which", return_value=None)
        with pytest.raises(click.ClickException, match="jq is required"):
            apply_jq({"data": "test"}, ".data")


class TestUnicodeOutput:
    def test_format_issue_detail_with_emoji(self):
        item = {
            "number": "42",
            "title": "Bug with 📚 emoji",
            "state": "open",
            "author": {"login": "alice"},
            "body": "Issue body with 🎉 emoji",
        }
        result = format_issue_detail(item)
        assert "📚" in result
        assert "🎉" in result

    def test_format_pr_detail_with_emoji(self):
        item = {
            "number": 101,
            "title": "Feature with 🚀 emoji",
            "state": "open",
            "user": {"login": "bob"},
            "head": {"label": "bob:task-7", "ref": "task-7"},
            "base": {"label": "owner:main", "ref": "main"},
            "body": "PR body with ✨ emoji",
        }
        result = format_pr_detail(item)
        assert "🚀" in result
        assert "✨" in result

    def test_format_issue_list_with_emoji(self):
        items = [
            {"number": "12", "state": "open", "title": "Fix 🐛 bug", "author": {"login": "alice"}},
        ]
        result = format_issue_list(items)
        assert "🐛" in result

    def test_format_pr_list_with_emoji(self):
        items = [
            {"number": 7, "state": "open", "title": "Add 🎯 feature", "user": {"login": "bob"}},
        ]
        result = format_pr_list(items)
        assert "🎯" in result
