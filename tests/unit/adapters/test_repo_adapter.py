from __future__ import annotations

import base64
from unittest.mock import MagicMock, call

import click
import pytest

from gitcode_cli.adapters.repos import RepoAdapter
from gitcode_cli.errors import APIError


@pytest.fixture
def service():
    return MagicMock()


@pytest.fixture
def adapter(service):
    return RepoAdapter(service)


def _contents_payload(text: str) -> dict:
    return {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


class TestRepoAdapterView:
    def test_view_returns_service_get(self, adapter, service):
        service.get.return_value = {"full_name": "owner/repo"}
        assert adapter.view("owner", "repo") == {"full_name": "owner/repo"}
        service.get.assert_called_once_with("owner", "repo")

    def test_get_readme_uses_readme_url_path(self, adapter, service):
        service.contents.return_value = _contents_payload("# Hello")
        item = {"readme_url": "https://gitcode.com/owner/repo/blob/main/docs/README.md"}

        assert adapter.get_readme("owner", "repo", item) == "# Hello"
        service.contents.assert_called_once_with("owner", "repo", "docs/README.md")

    def test_get_readme_falls_back_to_readme_md(self, adapter, service):
        service.contents.return_value = _contents_payload("readme body")
        assert adapter.get_readme("owner", "repo") == "readme body"
        service.contents.assert_called_once_with("owner", "repo", "README.md")

    def test_get_readme_returns_none_on_api_error(self, adapter, service):
        service.contents.side_effect = APIError("Not Found", 404)
        assert adapter.get_readme("owner", "repo") is None

    def test_get_readme_returns_none_on_unexpected_payload(self, adapter, service):
        service.contents.return_value = []
        assert adapter.get_readme("owner", "repo") is None

    def test_get_readme_returns_none_on_empty_content(self, adapter, service):
        service.contents.return_value = {"content": ""}
        assert adapter.get_readme("owner", "repo") is None

    def test_get_readme_returns_none_on_invalid_base64(self, adapter, service):
        service.contents.return_value = {"content": "not base64!!!"}
        assert adapter.get_readme("owner", "repo") is None


class TestRepoAdapterList:
    def test_list_defaults_to_authenticated_user(self, adapter, service):
        service.list_own.return_value = [{"full_name": "me/repo"}]

        items = adapter.list_repos(None, limit=30, fork=False, source=False, visibility=None, language=None)

        service.list_own.assert_called_once_with(page=1, per_page=30)
        assert items == [{"full_name": "me/repo"}]

    def test_list_owner_uses_users_endpoint(self, adapter, service):
        service.list_user.return_value = [{"full_name": "owner/repo"}]

        items = adapter.list_repos("owner", limit=30, fork=False, source=False, visibility=None, language=None)

        service.list_user.assert_called_once_with("owner", page=1, per_page=30)
        assert items == [{"full_name": "owner/repo"}]

    def test_list_owner_falls_back_to_orgs_on_404(self, adapter, service):
        service.list_user.side_effect = APIError("Not Found", 404)
        service.list_org.return_value = [{"full_name": "org/repo"}]

        items = adapter.list_repos("org", limit=30, fork=False, source=False, visibility=None, language=None)

        service.list_org.assert_called_once_with("org", page=1, per_page=30)
        assert items == [{"full_name": "org/repo"}]

    def test_list_owner_reraises_non_404_errors(self, adapter, service):
        service.list_user.side_effect = APIError("Forbidden", 403)

        with pytest.raises(APIError):
            adapter.list_repos("owner", limit=30, fork=False, source=False, visibility=None, language=None)
        service.list_org.assert_not_called()

    def test_list_paginates_until_limit_met(self, adapter, service):
        service.list_own.side_effect = [
            [{"full_name": f"me/repo-{index}"} for index in range(1, 101)],
            [{"full_name": f"me/repo-{index}"} for index in range(101, 131)],
        ]

        items = adapter.list_repos(None, limit=130, fork=False, source=False, visibility=None, language=None)

        assert service.list_own.call_args_list == [
            call(page=1, per_page=100),
            call(page=2, per_page=100),
        ]
        assert len(items) == 130

    def test_list_stops_on_short_page(self, adapter, service):
        service.list_own.side_effect = [
            [{"full_name": "me/repo"}],
        ]

        items = adapter.list_repos(None, limit=100, fork=False, source=False, visibility=None, language=None)

        assert service.list_own.call_count == 1
        assert items == [{"full_name": "me/repo"}]

    def test_list_stops_on_empty_page(self, adapter, service):
        service.list_own.side_effect = [
            [{"full_name": f"me/repo-{index}"} for index in range(1, 101)],
            [],
        ]

        items = adapter.list_repos(None, limit=None, fork=False, source=False, visibility=None, language=None)

        assert service.list_own.call_count == 2
        assert len(items) == 100

    def test_list_filters_forks(self, adapter, service):
        service.list_own.return_value = [
            {"full_name": "me/source", "fork": False},
            {"full_name": "me/fork", "fork": True},
        ]

        items = adapter.list_repos(None, limit=30, fork=True, source=False, visibility=None, language=None)
        assert items == [{"full_name": "me/fork", "fork": True}]

    def test_list_filters_sources(self, adapter, service):
        service.list_own.return_value = [
            {"full_name": "me/source", "fork": False},
            {"full_name": "me/fork", "fork": True},
        ]

        items = adapter.list_repos(None, limit=30, fork=False, source=True, visibility=None, language=None)
        assert items == [{"full_name": "me/source", "fork": False}]

    @pytest.mark.parametrize(
        ("visibility", "expected"),
        [
            ("public", "me/public"),
            ("private", "me/private"),
            ("internal", "me/internal"),
        ],
    )
    def test_list_filters_visibility(self, adapter, service, visibility, expected):
        service.list_own.return_value = [
            {"full_name": "me/public", "private": False, "internal": False},
            {"full_name": "me/private", "private": True},
            {"full_name": "me/internal", "internal": True},
        ]

        items = adapter.list_repos(None, limit=30, fork=False, source=False, visibility=visibility, language=None)
        assert [item["full_name"] for item in items] == [expected]

    def test_list_filters_language_case_insensitively(self, adapter, service):
        service.list_own.return_value = [
            {"full_name": "me/py", "language": "Python"},
            {"full_name": "me/go", "language": "Go"},
        ]

        items = adapter.list_repos(None, limit=30, fork=False, source=False, visibility=None, language="python")
        assert [item["full_name"] for item in items] == ["me/py"]

    def test_list_filter_counts_matched_items_towards_limit(self, adapter, service):
        service.list_own.side_effect = [
            [
                {"full_name": "me/source-1", "fork": False},
                {"full_name": "me/fork-1", "fork": True},
                {"full_name": "me/fork-2", "fork": True},
            ],
        ]

        items = adapter.list_repos(None, limit=2, fork=True, source=False, visibility=None, language=None)
        assert [item["full_name"] for item in items] == ["me/fork-1", "me/fork-2"]


class TestRepoAdapterCreate:
    def test_create_personal_sends_only_provided_fields(self, adapter, service):
        service.create_personal.return_value = {"full_name": "me/repo"}

        adapter.create_repo("repo", None, description="desc", private=True)

        service.create_personal.assert_called_once_with(name="repo", description="desc", private=True)

    def test_create_maps_flags_to_api_params(self, adapter, service):
        adapter.create_repo(
            "repo",
            None,
            description="desc",
            private=False,
            auto_init=True,
            homepage="https://example.com",
            has_issues=False,
            has_wiki=False,
            gitignore_template="Python",
            license_template="mit",
        )

        service.create_personal.assert_called_once_with(
            name="repo",
            description="desc",
            private=False,
            auto_init=True,
            homepage="https://example.com",
            has_issues=False,
            has_wiki=False,
            gitignore_template="Python",
            license_template="mit",
        )

    @pytest.mark.parametrize("private", [True, None])
    def test_create_org_defaults_to_private(self, adapter, service, private):
        service.create_org.return_value = {"full_name": "my-org/repo", "visibility": "private"}
        adapter.create_repo("repo", "my-org", private=private)

        service.create_org.assert_called_once_with("my-org", name="repo", public=0)
        service.create_personal.assert_not_called()


class TestRepoAdapterWrite:
    def test_fork_posts_and_wraps_result(self, adapter, service):
        service.fork.return_value = {"full_name": "my-org/repo"}

        result = adapter.fork_repo("owner", "repo", org="my-org")

        service.fork.assert_called_once_with("owner", "repo", organization="my-org")
        assert result.item == {"full_name": "my-org/repo"}
        assert result.message == "forked"

    def test_fork_without_org_omits_parameter(self, adapter, service):
        service.fork.return_value = {}
        adapter.fork_repo("owner", "repo", org=None)
        service.fork.assert_called_once_with("owner", "repo", organization=None)

    @pytest.mark.parametrize(
        "item",
        [
            {"namespace": {"path": "my-org"}},
            {"namespace": {"full_path": "my-org", "path": "my-org"}},
            {"full_name": "my-org/repo", "namespace": {"full_path": "my-org"}},
        ],
    )
    def test_fork_accepts_matching_canonical_namespace(self, adapter, service, item):
        service.fork.return_value = item

        result = adapter.fork_repo("owner", "repo", org="my-org")

        assert result.item == {**item, "full_name": "my-org/repo"}
        service.fork.assert_called_once_with("owner", "repo", organization="my-org")

    def test_fork_nested_organization_uses_full_path_not_leaf_name(self, adapter, service):
        service.fork.return_value = {
            "full_name": "parent/team/repo",
            "namespace": {"path": "team", "full_path": "parent/team"},
        }

        adapter.fork_repo("owner", "repo", org="parent/team")

        service.fork.assert_called_once_with("owner", "repo", organization="parent/team")

    @pytest.mark.parametrize(
        "item",
        [
            None,
            [],
            {},
            {"full_name": "repo"},
            {"full_name": "", "namespace": {"full_path": "my-org"}},
            {"full_name": 42, "namespace": {"full_path": "my-org"}},
            {"full_name": "my-org/"},
            {"full_name": "my-org/.."},
            {"full_name": "my-org/repo?other"},
            {"namespace": {"full_path": "my-org"}, "path": "../other"},
            {"namespace": {"full_path": "my-org"}, "path": []},
            {"namespace": {"full_path": 42}},
            {"namespace": {"name": "my-org"}},
            {"full_name": "personal/repo"},
            {"namespace": {"path": "personal"}},
            {"full_name": "my-org/repo", "namespace": {"full_path": "personal"}},
            {"full_name": "personal/repo", "namespace": {"full_path": "my-org"}},
        ],
    )
    def test_fork_unconfirmed_destination_fails_without_retry(self, adapter, service, item):
        service.fork.return_value = item

        with pytest.raises(click.ClickException, match="verify your GitCode repositories before retrying"):
            adapter.fork_repo("owner", "repo", org="my-org")

        assert service.mock_calls == [call.fork("owner", "repo", organization="my-org")]

    @pytest.mark.parametrize("org", ["", " ", "\t\n"])
    def test_fork_empty_org_does_not_fall_back_to_personal_namespace(self, adapter, service, org):
        with pytest.raises(click.UsageError, match="nonempty organization"):
            adapter.fork_repo("owner", "repo", org=org)

        service.fork.assert_not_called()

    def test_fork_http_error_is_not_retried(self, adapter, service):
        service.fork.side_effect = APIError("Organization is unavailable", 403)

        with pytest.raises(APIError, match="Organization is unavailable"):
            adapter.fork_repo("owner", "repo", org="my-org")

        assert service.mock_calls == [call.fork("owner", "repo", organization="my-org")]

    def test_edit_sends_only_changed_fields(self, adapter, service):
        service.update.return_value = {"full_name": "owner/repo"}

        adapter.edit_repo("owner", "repo", description="new", private=True)

        service.update.assert_called_once_with("owner", "repo", description="new", private=True)

    def test_edit_rejects_empty_payload(self, adapter, service):
        with pytest.raises(Exception, match="must specify at least one field to edit"):
            adapter.edit_repo("owner", "repo")
        service.update.assert_not_called()

    def test_rename_patches_name_and_path(self, adapter, service):
        service.update.return_value = {"full_name": "owner/new"}

        result = adapter.rename_repo("owner", "repo", "new")

        service.update.assert_called_once_with("owner", "repo", name="new", path="new")
        assert result.message == "renamed"

    def test_delete_calls_service_delete(self, adapter, service):
        result = adapter.delete_repo("owner", "repo")
        service.delete.assert_called_once_with("owner", "repo")
        assert result.message == "deleted"

    def test_sync_puts_sync_repo(self, adapter, service):
        service.get.return_value = {"fork": True}
        service.sync.return_value = {"repo_sync_result": True}

        result = adapter.sync_repo("owner", "repo", branch="main")

        service.sync.assert_called_once_with("owner", "repo", branch="main")
        service.get.assert_called_once_with("owner", "repo")
        assert result.message == "synced"
        assert result.item == {"repo_sync_result": True}


@pytest.mark.parametrize("fork", [False, 0])
def test_sync_non_fork_is_clear_and_never_sends_write(adapter, service, fork):
    service.get.return_value = {"fork": fork}
    with pytest.raises(click.ClickException, match="owner/repo is not a fork; no synchronization request"):
        adapter.sync_repo("owner", "repo")
    service.get.assert_called_once_with("owner", "repo")
    service.sync.assert_not_called()


@pytest.mark.parametrize(
    "item",
    [
        None,
        [],
        {},
        {"fork": None},
        {"fork": "false"},
        {"fork": "true"},
        {"fork": "1"},
        {"fork": 1.0},
        {"fork": 0.0},
        {"fork": 2},
        {"fork": -1},
        {"fork": []},
    ],
)
def test_sync_unknown_forkness_is_not_guessed(adapter, service, item):
    service.get.return_value = item
    with pytest.raises(click.ClickException, match="Cannot verify whether owner/repo is a fork"):
        adapter.sync_repo("owner", "repo")
    service.sync.assert_not_called()


@pytest.mark.parametrize("fork", [True, 1])
def test_sync_confirmed_fork_selects_upstream_default_not_fork_default(adapter, service, fork):
    service.get.side_effect = [
        {"fork": fork, "parentfull_name": "up/src", "default_branch": "not-this"},
        {"default_branch": "main"},
    ]
    service.sync.return_value = {"repo_sync_result": True}
    result = adapter.sync_repo("owner", "repo")
    assert result.message == "synced"
    assert service.mock_calls == [
        call.get("owner", "repo"),
        call.get("up", "src"),
        call.sync("owner", "repo", branch="main"),
    ]


@pytest.mark.parametrize("response", [None, {}, {"repo_sync_result": False}, {"repo_sync_result": 1}])
def test_sync_requires_explicit_provider_success(adapter, service, response):
    service.get.return_value = {"fork": True}
    service.sync.return_value = response
    with pytest.raises(click.ClickException, match="did not confirm"):
        adapter.sync_repo("owner", "repo", branch="main")
    service.sync.assert_called_once_with("owner", "repo", branch="main")


@pytest.mark.parametrize(
    "fork",
    [
        {"fork": True},
        {"fork": True, "parentfull_name": "other"},
        {"fork": True, "parent": {"full_name": "x/y"}, "parentfull_name": "z/y"},
    ],
)
def test_sync_missing_or_conflicting_parent_does_not_sync_all(adapter, service, fork):
    service.get.return_value = fork
    with pytest.raises(click.ClickException, match="Cannot verify the upstream"):
        adapter.sync_repo("owner", "repo")
    service.sync.assert_not_called()


@pytest.mark.parametrize("branch", [None, "", " ", "main\nnext", "release/*", "../main", "empty//branch"])
def test_sync_missing_or_invalid_upstream_default_never_requests_all_branches(adapter, service, branch):
    service.get.side_effect = [{"fork": True, "parentfull_name": "up/src"}, {"default_branch": branch}]
    with pytest.raises(click.ClickException, match="Cannot verify a single branch"):
        adapter.sync_repo("owner", "repo")
    service.sync.assert_not_called()


def test_sync_read_failure_never_reaches_write(adapter, service):
    service.get.side_effect = APIError("synthetic unavailable", status_code=403)
    with pytest.raises(APIError):
        adapter.sync_repo("owner", "repo")
    service.sync.assert_not_called()


def test_sync_write_failure_is_not_retried(adapter, service):
    service.get.return_value = {"fork": True}
    service.sync.side_effect = APIError("synthetic failure", status_code=500)
    with pytest.raises(APIError):
        adapter.sync_repo("owner", "repo", branch="main")
    service.sync.assert_called_once_with("owner", "repo", branch="main")


@pytest.mark.parametrize(
    ("url_path", "expected"),
    [
        ("docs/README%23x.md?ref=main#section", "docs/README#x.md"),
        ("docs/README%3Fx.md", "docs/README?x.md"),
        ("docs/100%25.md", "docs/100%.md"),
        ("docs/hello%20world.md", "docs/hello world.md"),
        ("docs/literal%252F.md", "docs/literal%2F.md"),
    ],
)
def test_readme_url_decodes_once_for_the_service_boundary(adapter, service, url_path, expected):
    service.contents.return_value = _contents_payload("readme body")
    item = {"readme_url": "https://gitcode.com/owner/repo/blob/main/" + url_path}
    assert adapter.get_readme("owner", "repo", item) == "readme body"
    service.contents.assert_called_once_with("owner", "repo", expected)


def test_malformed_readme_url_remains_best_effort(adapter, service):
    assert adapter.get_readme("owner", "repo", {"readme_url": "https://[invalid"}) is None
    service.contents.assert_not_called()
