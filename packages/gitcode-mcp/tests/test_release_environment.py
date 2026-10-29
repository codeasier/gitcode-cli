"""Mocked release protection API contracts; never inspect real settings here."""

import copy
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/release_environment.py"
SPEC = importlib.util.spec_from_file_location("release_environment", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def responses():
    return [
        {
            "name": "mcp-pypi",
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "prevent_self_review": True,
                    "reviewers": [{"type": "User", "reviewer": {"id": 1}}],
                }
            ],
            "deployment_branch_policy": {
                "protected_branches": False,
                "custom_branch_policies": True,
            },
        },
        {"total_count": 1, "branch_policies": [{"name": "mcp-v*", "type": "tag"}]},
    ]


def test_existing_environment_requires_independent_review_and_exact_tag_policy():
    data = responses()
    seen = []

    def read(url):
        seen.append(url)
        return data[len(seen) - 1]

    release.verify_environment(read)
    assert seen == [release.BASE, release.BASE + "/deployment-branch-policies?per_page=100&page=1"]


@pytest.mark.parametrize(
    "case",
    [
        "wrong_name",
        "no_review",
        "self_review",
        "no_reviewers",
        "open_refs",
        "extra_policy",
        "branch",
        "wide_tag",
        "no_type",
    ],
)
def test_missing_or_weakened_protection_fails_closed(case):
    data = copy.deepcopy(responses())
    environment, policies = data
    if case == "wrong_name":
        environment["name"] = "other"
    elif case == "no_review":
        environment["protection_rules"] = []
    elif case == "self_review":
        environment["protection_rules"][0]["prevent_self_review"] = False
    elif case == "no_reviewers":
        environment["protection_rules"][0]["reviewers"] = []
    elif case == "open_refs":
        environment["deployment_branch_policy"] = None
    elif case == "extra_policy":
        policies["total_count"] = 101
    elif case == "branch":
        policies["branch_policies"][0]["type"] = "branch"
    elif case == "wide_tag":
        policies["branch_policies"][0]["name"] = "*"
    else:
        del policies["branch_policies"][0]["type"]
    iterator = iter(data)
    with pytest.raises(ValueError):
        release.verify_environment(lambda _: next(iterator))


def test_unavailable_public_api_is_not_bypassed_or_retried():
    calls = []

    def refused(url):
        calls.append(url)
        raise PermissionError("Public read denied")

    with pytest.raises(PermissionError):
        release.verify_environment(refused)
    assert calls == [release.BASE]
