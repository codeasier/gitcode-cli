from __future__ import annotations

from .base import AdapterActionResult
from .issues import IssueAdapter
from .pulls import PullRequestAdapter

__all__ = ["AdapterActionResult", "IssueAdapter", "PullRequestAdapter"]
