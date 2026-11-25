"""Read-only native name ordering. In-process HTTP; no credentials or live repository."""

from __future__ import annotations

import json
from inspect import signature

import httpx
import pytest
from click.testing import CliRunner

from gitcode_cli import repo_read
from gitcode_cli.cli import main
from gitcode_cli.services import label_order

TOKEN = "mock-label-reader"


def label(i, name, **fields):
    return {"id": i, "name": name, "color": "#123456", "repository_id": 42, **fields}


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    real_client = httpx.Client
    runner = CliRunner(**({"mix_stderr": False} if "mix_stderr" in signature(CliRunner).parameters else {}))

    def run(pages, args=("--sort", "name"), *, token=TOKEN, repo="Acme/tools", root=()):
        seen = []

        def handle(request):
            seen.append(request)
            page = len(seen)
            assert (request.method, request.url.scheme, request.url.host, str(request.url.path)) == (
                "GET",
                "https",
                "api.gitcode.com",
                "/api/v5/repos/Acme/tools/labels",
            )
            assert dict(request.url.params) == {"page": str(page), "per_page": "100"}
            assert "private-token" not in request.headers and "cookie" not in request.headers and not request.content
            assert request.headers.get("authorization") == (f"Bearer {token}" if token else None)
            row = pages[page - 1]
            return row if isinstance(row, httpx.Response) else httpx.Response(200, json=row)

        monkeypatch.setattr(
            repo_read.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)
        )
        result = runner.invoke(main, [*root, "label", "list", "-R", repo, *args], env={"GC_TOKEN": token})
        return result, len(seen)

    return run


@pytest.mark.parametrize(
    ("direction", "expected"), [((), ["A", "a"]), (("--order", "asc"), ["A", "a"]), (("--order", "desc"), ["中", "z"])]
)
def test_sort_after_exhaustion_even_if_first_page_short(cli, direction, expected):
    first = httpx.Response(200, headers={"X-Total": "4", "X-Next-Page": "2"}, json=[label(2, "z"), label(3, "a")])
    result, count = cli(
        [first, [label(1, "A"), label(4, "中")], []], ["--sort", "name", *direction, "-L", "2", "--json", "name"]
    )
    assert result.exit_code == 0, result.output
    assert [r["name"] for r in json.loads(result.output)] == expected
    assert count == 3


def test_exact_boundary_unicode_and_projection(cli):
    rows = [label(i, f"B{i:03d}") for i in range(1, 101)]
    result, count = cli(
        [rows, [label(101, "A"), label(102, "a\u0301"), label(103, "á")], []],
        ["--sort", "name", "-L", "1", "--json", "name,id,color"],
    )
    assert result.exit_code == 0 and count == 3
    assert json.loads(result.output) == [{"name": "A", "id": 101, "color": "123456"}]
    result, _ = cli([[label(102, "a\u0301"), label(103, "á")], []], ["--sort", "name", "--json", "name"])
    assert [r["name"] for r in json.loads(result.output)] == ["a\u0301", "á"]


def test_empty_and_text(cli):
    result, count = cli([[]], ["--sort", "name", "--json", "name"], token="")
    assert result.exit_code == 0 and json.loads(result.output) == [] and count == 1
    result, count = cli([[label(1, "X", color="#AAA")], []], token="")
    assert result.exit_code == 0 and result.output == "X\tAAA\n" and count == 2


@pytest.mark.parametrize(
    "page",
    [
        [label(1, "renamed")],
        [label(2, "old")],
        [label(2, "x", repository_id=15)],
        [label(2, "x", repository_id=True)],
        [label(True, "invalid")],
        [label(2, "\x1b[2J")],
        [label(2, TOKEN)],
        [label(2, "x", color="not color")],
        [None],
        [label(2, "A")] * 101,
        {"items": []},
        httpx.Response(206, json=[]),
        httpx.Response(403, json={}),
        httpx.Response(302, headers={"Location": "https://elsewhere.invalid/"}),
        httpx.Response(200, content=b'[{"id":1,"id":2,"name":"x"}]'),
        httpx.Response(200, headers={"X-Total": "3"}, json=[]),
        httpx.Response(200, headers={"X-Next-Page": "3"}, json=[]),
        httpx.Response(200, headers={"X-Truncated": "true"}, json=[]),
        httpx.Response(200, headers={"X-Total-Pages": "4"}, json=[]),
        httpx.Response(200, headers={"X-Page": "1"}, json=[]),
        httpx.Response(200, headers={"X-Per-Page": "1"}, json=[]),
        httpx.Response(200, headers={"X-Total": "01"}, json=[]),
        httpx.Response(200, headers={"Content-Range": "labels 0-1/10"}, json=[]),
        httpx.Response(200, headers={"link": '<https://other.invalid/next>; rel="next"'}, json=[]),
    ],
)
def test_bad_later_page_produces_no_partial_output(cli, page):
    result, count = cli([[label(1, "old")], page])
    assert count == 2 and result.exit_code == 1 and result.stdout == "" and TOKEN not in result.stderr


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ({"X-Total": "1"}, {"X-Total": "2"}),
        ({"X-Next-Page": "2"}, {}),
        ({"X-Total-Pages": "2"}, {"X-Total-Pages": "1"}),
    ],
)
def test_changed_totals_and_failed_continuation(cli, first, second):
    r, n = cli([httpx.Response(200, headers=first, json=[label(1, "x")]), httpx.Response(200, headers=second, json=[])])
    assert n == 2 and r.exit_code == 1 and r.stdout == ""


def test_page_bound_requires_empty_probe(cli, monkeypatch):
    monkeypatch.setattr(label_order, "MAX_DATA_PAGES", 2)
    result, n = cli([[label(1, "z")], [label(2, "b")], []])
    assert result.exit_code == 0 and n == 3
    result, n = cli([[label(1, "z")], [label(2, "b")], [label(3, "a")]])
    assert result.exit_code == 1 and n == 3 and result.stdout == ""


@pytest.mark.parametrize(
    "args",
    [
        ["--sort", "created"],
        ["--order", "asc"],
        ["--sort", "name", "--search", "x"],
        ["-S", "", "--sort", "name"],
        ["--sort", "name", "--order", "reverse"],
        ["--sort", "name", "--json", "createdAt"],
    ],
)
def test_unsupported_options_before_transport(cli, args):
    result, n = cli([], args)
    assert result.exit_code != 0 and n == 0 and not result.stdout


def test_foreign_repo_before_transport(cli):
    result, n = cli([], repo="github.com/Acme/tools")
    assert result.exit_code != 0 and n == 0 and not result.stdout


@pytest.mark.parametrize("root", ["Other/tools", "Acme/other", "github.com/Acme/tools", ""])
def test_conflicting_repository_before_request(cli, root):
    result, count = cli([], root=["-R", root])
    assert result.exit_code != 0 and count == 0 and result.stdout == ""


def test_consistent_explicit_repositories(cli):
    result, count = cli([[]], root=["-R", "gitcode.com/acme/Tools"])
    assert result.exit_code == 0 and count == 1


def test_actual_1000_label_limit_accepts_empty_and_refuses_nonempty_probe(cli):
    pages = [[label(i + j + 1, f"L{i + j:04d}") for j in range(100)] for i in range(0, 1000, 100)]
    args = ["--sort", "name", "--order", "desc", "-L", "1", "--json", "id,name"]
    result, count = cli([*pages, []], args)
    assert count == 11 and result.exit_code == 0 and json.loads(result.output) == [{"id": 1000, "name": "L0999"}]
    result, count = cli([*pages, [label(1001, "new")]], args)
    assert count == 11 and result.exit_code == 1 and result.stdout == ""


@pytest.mark.parametrize(
    "link",
    [
        '<https://api.gitcode.com/api/v5/repos/Acme/tools/labels?page=2&per_page=100>; rel="next"',
        "</api/v5/repos/Acme/tools/labels?per_page=100&page=2>; rel=next",
        '<?page=2&per_page=100>; rel="next"',
    ],
)
def test_adjacent_link_confirms_independent_numbered_request(cli, link):
    page = httpx.Response(200, headers={"Link": link, "X-Next-Page": "2"}, json=[label(1, "z")])
    result, count = cli([page, [label(2, "A")], []], ["--sort", "name", "-L", "1", "--json", "name"])
    assert count == 3 and result.exit_code == 0
    assert json.loads(result.stdout) == [{"name": "A"}]


@pytest.mark.parametrize(
    "link",
    [
        '<?page=4&per_page=100>; rel="next"',
        '<?page=2&per_page=99>; rel="next"',
        '<?page=2&page=4&per_page=100>; rel="next"',
        '</api/v5/repos/Acme/other/labels?page=2&per_page=100>; rel="next"',
        '<https://elsewhere.invalid/api/v5/repos/Acme/tools/labels?page=2&per_page=100>; rel="next"',
        "<?page=4&per_page=100>; rel=next, <?page=2&per_page=100>; rel=next",
        '<?page=4&per_page=100>; rel="alternate next"',
    ],
)
def test_contradictory_next_link_fails_without_another_request_or_output(cli, link):
    page = httpx.Response(200, headers={"Link": link}, json=[label(1, "z")])
    result, count = cli([page, [label(2, "A")], []], ["--sort", "name", "--json", "name"])
    assert count == 1 and result.exit_code == 1 and result.stdout == ""
    assert "Cannot verify a complete repository label catalog" in result.stderr


@pytest.mark.parametrize("extra", [{}, {"X-Total-Pages": "2"}])
def test_last_link_without_next_confirms_terminal_page(cli, extra):
    first = httpx.Response(
        200,
        headers={"Link": '<?page=2&per_page=100>; rel="last"', **extra},
        json=[label(1, "z")],
    )
    result, count = cli([first, [label(2, "A")], []], ["--sort", "name", "-L", "1", "--json", "name"])
    assert count == 3 and result.exit_code == 0
    assert json.loads(result.stdout) == [{"name": "A"}]


def test_last_link_without_next_refuses_early_empty_page(cli):
    first = httpx.Response(200, headers={"Link": '<?page=4&per_page=100>; rel="last"'}, json=[label(1, "z")])
    result, count = cli([first, [label(2, "A")], []], ["--sort", "name", "--json", "name"])
    assert count == 3 and result.exit_code == 1 and result.stdout == ""


def test_last_link_cannot_disagree_with_total_pages(cli):
    first = httpx.Response(
        200, headers={"Link": '<?page=4&per_page=100>; rel="last"', "X-Total-Pages": "2"}, json=[label(1, "z")]
    )
    result, count = cli([first, [label(2, "A")], []], ["--sort", "name", "--json", "name"])
    assert count == 1 and result.exit_code == 1 and result.stdout == ""


def test_changed_last_link_refuses_catalog(cli):
    first = httpx.Response(200, headers={"Link": '<?page=2&per_page=100>; rel="last"'}, json=[label(1, "z")])
    second = httpx.Response(200, headers={"Link": '<?page=3&per_page=100>; rel="last"'}, json=[label(2, "A")])
    result, count = cli([first, second, []], ["--sort", "name", "--json", "name"])
    assert count == 2 and result.exit_code == 1 and result.stdout == ""


def test_last_link_on_probe_cannot_deny_a_page_already_seen(cli):
    last = httpx.Response(200, headers={"Link": '<?page=1&per_page=100>; rel="last"'}, json=[])
    result, count = cli([[label(1, "z")], [label(2, "A")], last], ["--sort", "name", "--json", "name"])
    assert count == 3 and result.exit_code == 1 and result.stdout == ""
