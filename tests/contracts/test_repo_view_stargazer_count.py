"""The opt-in gh count is projected from the existing repository detail GET."""

import json
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.context import AppContext


@pytest.fixture
def run(monkeypatch):
    client = Mock(spec_set=["get"])
    monkeypatch.setattr(AppContext, "client", lambda self: client)

    def invoke(*args):
        return CliRunner().invoke(main, ["--token", "synthetic", "repo", *args])

    return client, invoke


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"stargazers_count": 2}, 2),
        ({"stargazers_count": 0}, 0),
        ({}, None),
        ({"stargazers_count": None}, None),
        ({"stargazers_count": True}, None),
        ({"stargazers_count": False}, None),
        ({"stargazers_count": "2"}, None),
        ({"stargazers_count": 2.0}, None),
        ({"stargazers_count": -1}, None),
    ],
)
def test_view_count_uses_only_native_integer_and_preserves_old_field(run, raw, expected):
    client, invoke = run
    client.get.return_value = {"name": "widget", "watchers_count": 9, "stargazerCount": 99, **raw}
    result = invoke("view", "example/widget", "--json", "stargazers, stargazerCount,name")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert list(data) == ["stargazers", "stargazerCount", "name"]
    assert data == {"stargazers": raw.get("stargazers_count"), "stargazerCount": expected, "name": "widget"}
    if expected is not None:
        assert type(data["stargazerCount"]) is int
    client.get.assert_called_once_with("/repos/example/widget")


def test_view_count_is_discoverable_but_list_help_does_not_advertise_it(run):
    client, invoke = run
    for name in ("view", "list"):
        result = invoke(name, "--json")
        assert result.exit_code == 1
        assert result.output.startswith("Available fields: ")
        fields = result.output.removeprefix("Available fields: ").strip().split(", ")
        assert "stargazers" in fields
        assert ("stargazerCount" in fields) == (name == "view")
    client.get.assert_not_called()


def test_implicit_view_jq_keeps_existing_object_shape(run, monkeypatch):
    client, invoke = run
    client.get.return_value = {"name": "widget", "stargazers_count": 5}
    # Capture the real projection passed to jq without requiring an external binary.
    monkeypatch.setattr("gitcode_cli.formatters.apply_jq", lambda data, query: [data])
    result = invoke("view", "example/widget", "--jq", ".")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "stargazerCount" not in data
    assert data["stargazers"] == 5
    client.get.assert_called_once_with("/repos/example/widget")


def test_view_selected_count_can_be_formatted_as_template(run):
    client, invoke = run
    client.get.return_value = {"stargazers_count": 4}
    result = invoke("view", "example/widget", "--json", "stargazerCount", "--template", "{{.stargazerCount}}")
    assert result.exit_code == 0, result.output
    assert result.output == "4\n"
    client.get.assert_called_once_with("/repos/example/widget")
