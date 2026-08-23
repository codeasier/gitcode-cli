from __future__ import annotations

from .base import AdapterActionResult
from .issues import IssueAdapter
from .pulls import PullRequestAdapter
from .repos import RepoAdapter

__all__ = ["AdapterActionResult", "IssueAdapter", "PullRequestAdapter", "RepoAdapter"]
