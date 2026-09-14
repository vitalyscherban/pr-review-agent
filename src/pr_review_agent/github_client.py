"""Thin GitHub REST API client for fetching PR diffs and posting review comments."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub API returns an error response."""


@dataclass
class InlineComment:
    """A single inline review comment anchored to a file/line in the PR diff."""

    path: str
    line: int
    body: str


class GitHubClient:
    """Wraps the GitHub REST API calls needed by the PR review agent."""

    def __init__(self, token: str, repository: str, session: Optional[requests.Session] = None, base_url: str = API_BASE):
        self.token = token
        self.repository = repository
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, url, headers=self._headers(kwargs.pop("accept", "application/vnd.github+json")), timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise GitHubAPIError(f"Network error calling GitHub API ({method} {url}): {exc}") from exc

        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise GitHubAPIError(f"GitHub API rate limit exceeded: {response.text}")
        if response.status_code >= 400:
            raise GitHubAPIError(f"GitHub API error {response.status_code} for {method} {url}: {response.text}")
        return response

    def get_pr_diff(self, pr_number: int) -> str:
        """Fetch the raw unified diff for a pull request."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pr_number}"
        response = self._request("GET", url, accept="application/vnd.github.v3.diff")
        return response.text

    def get_pr(self, pr_number: int) -> dict:
        """Fetch PR metadata (head sha, base, title, etc.)."""
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pr_number}"
        return self._request("GET", url).json()

    def post_issue_comment(self, pr_number: int, body: str) -> dict:
        """Post a top-level (issue) comment on the PR."""
        url = f"{self.base_url}/repos/{self.repository}/issues/{pr_number}/comments"
        return self._request("POST", url, json={"body": body}).json()

    def post_review(self, pr_number: int, commit_sha: str, body: str, event: str, comments: Optional[List[InlineComment]] = None) -> dict:
        """Post a full PR review, optionally with inline comments.

        `event` must be one of APPROVE, REQUEST_CHANGES, COMMENT.
        """
        url = f"{self.base_url}/repos/{self.repository}/pulls/{pr_number}/reviews"
        payload = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }
        if comments:
            payload["comments"] = [
                {"path": c.path, "line": c.line, "body": c.body} for c in comments
            ]
        return self._request("POST", url, json=payload).json()
