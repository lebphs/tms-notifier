"""Jira REST API client for fetching issue details and comments."""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)


class JiraAuthError(PermissionError):
    """Raised when Jira rejects the provided credentials."""


class JiraClient:
    """Minimal Jira REST client using Bearer token authentication."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        })

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/rest/api/2{path}"
        response = self.session.get(url, params=params, timeout=30)
        if response.status_code == 401:
            raise JiraAuthError(
                "Jira authentication failed. Check JIRA_USERNAME, "
                "JIRA_API_TOKEN and JIRA_URL in .env."
            )
        if response.status_code == 403:
            raise JiraAuthError(
                "Jira credentials are valid but user lacks permission to "
                f"access this resource: {url}"
            )
        response.raise_for_status()
        return response.json()

    def get_issue(self, issue_key: str) -> dict[str, Any] | None:
        """Fetch issue fields. Returns None if the issue is not found."""
        try:
            return self._get(
                f"/issue/{issue_key}",
                params={
                    "fields": "summary,description,status,assignee",
                },
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("Issue %s not found", issue_key)
                return None
            raise

    def get_last_comments(
        self, issue_key: str, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Return the most recent comments for an issue."""
        data = self._get(
            f"/issue/{issue_key}/comment",
            params={
                "orderBy": "-created",
                "maxResults": limit,
                "expand": "renderedBody",
            },
        )
        return data.get("comments", [])

    def get_filter(self, filter_id: str | int) -> dict[str, Any] | None:
        """Fetch a saved filter by ID. Returns None if not found."""
        try:
            return self._get(f"/filter/{filter_id}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("Filter %s not found", filter_id)
                return None
            raise

    def search_issues(
        self,
        jql: str,
        fields: str = "summary,status",
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Run a JQL search and return the issue list."""
        data = self._get(
            "/search",
            params={
                "jql": jql,
                "fields": fields,
                "maxResults": max_results,
            },
        )
        return data.get("issues", [])

    @staticmethod
    def _get_user_name(user: dict | None) -> str:
        if not user:
            return "Unassigned"
        return user.get("displayName") or user.get("name") or "Unknown"

    @staticmethod
    def _get_status_name(issue: dict[str, Any]) -> str:
        fields = issue.get("fields", {})
        status = fields.get("status")
        return status.get("name", "Unknown") if status else "Unknown"

    @staticmethod
    def _get_summary(issue: dict[str, Any]) -> str:
        fields = issue.get("fields", {})
        return fields.get("summary") or "_No summary_"

    @staticmethod
    def _format_description(description: Any) -> str:
        if not description:
            return "_No description_"
        if isinstance(description, str):
            return description or "_No description_"
        # Atlassian Document Format (ADF) on newer Jira; fallback to raw JSON
        return str(description)

    @staticmethod
    def _format_comment_body(comment: dict[str, Any]) -> str:
        body = comment.get("renderedBody") or comment.get("body")
        if not body:
            return "_Empty comment_"
        if isinstance(body, str):
            # Strip HTML tags if renderedBody returns HTML.
            body = re.sub(r"<[^>]+>", "", body)
            return body.strip() or "_Empty comment_"
        return str(body)

    def build_reply(self, issue_key: str) -> str:
        """Fetch issue data and format a markdown reply."""
        issue = self.get_issue(issue_key)
        if issue is None:
            return f"Issue **{issue_key}** not found in Jira."

        fields = issue.get("fields", {})
        summary = fields.get("summary", "_No summary_")
        status = self._get_status_name(issue)
        assignee = self._get_user_name(fields.get("assignee"))
        description = self._format_description(fields.get("description"))
        link = f"{self.base_url}/browse/{issue_key}"

        last_comments = self.get_last_comments(issue_key, limit=3)
        if last_comments:
            lines = ["**Last 3 comments**"]
            for idx, comment in enumerate(last_comments, start=1):
                author = self._get_user_name(comment.get("author"))
                created = comment.get("created", "unknown date")
                body = self._format_comment_body(comment)
                lines.append(f"{idx}. by {author}, {created}:\n{body}")
            comment_section = "\n\n".join(lines)
        else:
            comment_section = "**Last 3 comments**: _No comments yet_"

        return (
            f"**{issue_key}**: {summary}\n\n"
            f"**Status**: {status}\n"
            f"**Assignee**: {assignee}\n\n"
            f"**Description**:\n{description}\n\n"
            f"{comment_section}\n\n"
            f"[Open in Jira]({link})"
        )

    def format_issue_snapshot(self, issue: dict[str, Any]) -> dict[str, str]:
        """Return a lightweight snapshot of an issue for change tracking."""
        return {
            "key": issue.get("key", ""),
            "status": self._get_status_name(issue),
            "summary": self._get_summary(issue),
        }
