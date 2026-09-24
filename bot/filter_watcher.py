"""Watch Jira filters and emit Webex notifications on changes."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from bot.jira_client import JiraClient
from bot.webex_client import WebexClient

logger = logging.getLogger(__name__)

STATE_FILE_NAME = "filters_state.json"


class FilterWatcher:
    """Polls Jira filters and notifies a Webex room about new/updated tickets."""

    def __init__(
        self,
        jira: JiraClient,
        webex: WebexClient,
        state_path: str | None = None,
    ):
        self.jira = jira
        self.webex = webex
        self.state_path = state_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            STATE_FILE_NAME,
        )
        self._state: dict[str, Any] = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                logger.warning("Corrupt state file; starting fresh.")
                return {}
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read state file %s: %s", self.state_path, exc)
            return {}

    def _save_state(self) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Could not write state file %s: %s", self.state_path, exc)

    def list_filters(self) -> dict[str, dict[str, Any]]:
        """Return the currently watched filters with metadata."""
        return {
            filter_id: {
                "jql": info.get("jql", "_unknown_"),
                "last_checked_at": info.get("last_checked_at"),
                "issue_count": len(info.get("issues", {})),
            }
            for filter_id, info in self._state.items()
        }

    def add_filter(self, filter_id: str) -> tuple[bool, str]:
        """Validate and start watching a Jira filter.

        Returns (success, message).
        """
        if filter_id in self._state:
            return False, f"Filter **{filter_id}** is already being watched."

        try:
            jfilter = self.jira.get_filter(filter_id)
        except Exception as exc:
            logger.exception("Failed to fetch filter %s", filter_id)
            return False, f"Could not fetch filter **{filter_id}**: {exc}"

        if jfilter is None:
            return False, f"Filter **{filter_id}** not found in Jira."

        jql = jfilter.get("jql", "")
        if not jql:
            return False, f"Filter **{filter_id}** has no JQL query."

        self._state[filter_id] = {
            "jql": jql,
            "name": jfilter.get("name", f"Filter {filter_id}"),
            "last_checked_at": None,
            "issues": {},
        }
        self._save_state()

        # Run an immediate check so the user sees current issues as baseline.
        self.check_filters(filter_ids=[filter_id])
        return True, (
            f"Now watching filter **{filter_id}**: `{jql}`. "
            "I will notify this room when new tickets appear or statuses change."
        )

    def remove_filter(self, filter_id: str) -> tuple[bool, str]:
        """Stop watching a filter."""
        if filter_id not in self._state:
            return False, f"Filter **{filter_id}** is not being watched."
        del self._state[filter_id]
        self._save_state()
        return True, f"Stopped watching filter **{filter_id}**."

    def _build_notification(
        self,
        filter_id: str,
        filter_info: dict[str, Any],
        new_issues: list[dict[str, str]],
        changed_issues: list[tuple[dict[str, str], str]],
    ) -> str:
        filter_name = filter_info.get("name", f"Filter {filter_id}")
        lines = [f"**Filter update: {filter_name}**"]

        if new_issues:
            lines.append("\n**New tickets:**")
            for issue in new_issues:
                link = f"{self.jira.base_url}/browse/{issue['key']}"
                lines.append(
                    f"- **{issue['key']}** ({issue['status']}): {issue['summary']} "
                    f"[Open]({link})"
                )

        if changed_issues:
            lines.append("\n**Status changed:**")
            for issue, old_status in changed_issues:
                link = f"{self.jira.base_url}/browse/{issue['key']}"
                lines.append(
                    f"- **{issue['key']}**: `{old_status}` → `{issue['status']}` "
                    f"({issue['summary']}) [Open]({link})"
                )

        return "\n".join(lines)

    def check_filters(self, filter_ids: list[str] | None = None) -> None:
        """Poll configured filters and send notifications for changes."""
        if filter_ids is None:
            filter_ids = list(self._state.keys())

        for filter_id in filter_ids:
            filter_info = self._state.get(filter_id)
            if not filter_info:
                logger.warning("Filter %s is not watched; skipping", filter_id)
                continue

            jql = filter_info.get("jql", "")
            if not jql:
                logger.warning("Filter %s has no JQL; skipping", filter_id)
                continue

            try:
                issues = self.jira.search_issues(jql, fields="summary,status")
            except Exception as exc:
                logger.exception("Failed to search filter %s: %s", filter_id, exc)
                continue

            current_snapshots = {
                issue["key"]: self.jira.format_issue_snapshot(issue)
                for issue in issues
            }
            previous_snapshots = filter_info.get("issues", {})

            new_issues: list[dict[str, str]] = []
            changed_issues: list[tuple[dict[str, str], str]] = []

            for key, snapshot in current_snapshots.items():
                prev = previous_snapshots.get(key)
                if not prev:
                    new_issues.append(snapshot)
                elif prev.get("status") != snapshot["status"]:
                    changed_issues.append((snapshot, prev.get("status", "Unknown")))

            # Only notify if we already had a previous check; otherwise this
            # initial run establishes the baseline silently (except for the
            # immediate check after /add_filter, which we want to be quiet too).
            if filter_info.get("last_checked_at") and (new_issues or changed_issues):
                message = self._build_notification(
                    filter_id, filter_info, new_issues, changed_issues
                )
                try:
                    self.webex.send_message(message)
                except Exception as exc:
                    logger.exception("Failed to send filter notification: %s", exc)

            filter_info["issues"] = current_snapshots
            filter_info["last_checked_at"] = datetime.now(timezone.utc).isoformat()
            self._save_state()
