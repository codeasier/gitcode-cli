"""Read-only, fail-closed checks of the pre-existing public release environment.

No token, authentication fallback, environment creation or setting update exists
here. Network/API errors stop the release; only mocked readers are used in tests.
"""

from __future__ import annotations

import json
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = "https://api.github.com/repos/codeasier/gitcode-cli/environments/mcp-pypi"
MAX_RESPONSE_BYTES = 1_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Release protection API redirected unexpectedly")


def read_public_json(url: str) -> dict:
    if url != BASE and not url.startswith(BASE + "/deployment-branch-policies?"):
        raise ValueError("Unexpected release protection API URL")
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "codeasier-gitcode-mcp-release-check",
        },
        method="GET",
    )
    # The source repository is public. Do not request new credentials/permissions
    # or fall back to authenticated access if public reads are denied.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError("Release protection API did not return success")
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Release protection response exceeded its limit")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("Invalid release protection response")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_environment(read=read_public_json) -> None:
    environment = read(BASE)
    require(environment.get("name") == "mcp-pypi", "Expected the existing mcp-pypi environment")
    rules = environment.get("protection_rules")
    require(isinstance(rules, list), "Missing environment protection rules")
    reviewers = [rule for rule in rules if rule.get("type") == "required_reviewers"]
    require(len(reviewers) == 1, "A required-reviewer protection rule must exist")
    rule = reviewers[0]
    require(rule.get("prevent_self_review") is True, "Release self-review must be disabled")
    identities = rule.get("reviewers")
    require(
        isinstance(identities, list) and bool(identities), "Required reviewers must be configured"
    )
    require(
        all(
            item.get("type") in {"User", "Team"}
            and isinstance(item.get("reviewer", {}).get("id"), int)
            and item["reviewer"]["id"] > 0
            for item in identities
        ),
        "Invalid required-reviewer identity",
    )
    require(
        environment.get("deployment_branch_policy")
        == {"protected_branches": False, "custom_branch_policies": True},
        "Explicit tag-only deployment policies must be enabled",
    )
    # The contract intentionally permits exactly one narrow tag rule. Any broader
    # rule, branch rule, absent type, extra page or ambiguous count fails closed.
    policies = read(BASE + "/deployment-branch-policies?per_page=100&page=1")
    entries = policies.get("branch_policies")
    require(policies.get("total_count") == 1, "Expected exactly one release tag policy")
    require(
        isinstance(entries, list) and len(entries) == 1, "Incomplete deployment policy response"
    )
    require(
        entries[0].get("name") == "mcp-v*" and entries[0].get("type") == "tag",
        "Only the mcp-v* tag deployment policy is permitted",
    )


if __name__ == "__main__":
    verify_environment()
    print("Verified existing release environment, independent reviewer and tag-only policy.")
