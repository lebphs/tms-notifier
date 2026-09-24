"""Entry point for the TMS Notifier Webex bot."""
from __future__ import annotations

import logging
import sys
import time
from typing import Any

from config import Config
from bot.filter_watcher import FilterWatcher
from bot.jira_client import JiraAuthError, JiraClient
from bot.parser import build_help_message, parse_command
from bot.webex_client import WebexClient, WebexPermissionError, WebexServerError
from webexteamssdk.exceptions import ApiError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Bot:
    """Polling Webex bot that replies to Jira ticket commands and watches filters."""

    def __init__(self, config: Config):
        config.validate()
        self.config = config

        token = config.WEBEX_BOT_TOKEN or ""
        logger.info("Loaded WEBEX_BOT_TOKEN: length=%s, prefix=%s", len(token), token[:12])
        if not token:
            raise ValueError("WEBEX_BOT_TOKEN is empty. Check your .env file.")

        self.webex = WebexClient(config.WEBEX_BOT_TOKEN, config.WEBEX_ROOM_ID)
        logger.info(
            "Jira config: token_length=%s, url=%s",
            len(config.JIRA_API_TOKEN or ""),
            config.JIRA_URL,
        )
        self.jira = JiraClient(
            config.JIRA_URL,
            config.JIRA_API_TOKEN,
        )

        try:
            me = self.webex.api.people.me()
            logger.info("Webex token is valid. Bot identity: %s (%s)", me.displayName, me.emails)
        except ApiError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 401:
                raise ValueError(
                    "Webex token was rejected (401 Unauthorized). "
                    "If the same token works with curl, check that .env is saved as UTF-8 "
                    "without BOM, has no quotes/spaces around the token, and that the bot is "
                    "started from the project directory."
                ) from exc
            raise

        self.bot_person_id = me.id
        # Store IDs of messages already processed to avoid duplicates.
        self.processed_message_ids: set[str] = set()
        # Seed the set with recent messages so the bot does not replay old history.
        for message in self.webex.get_messages():
            message_id = message.get("id")
            if message_id:
                self.processed_message_ids.add(message_id)

        self.filter_watcher: FilterWatcher | None = None
        self._last_filter_check = 0.0
        self._init_filter_watcher()

    def _init_filter_watcher(self) -> None:
        self.filter_watcher = FilterWatcher(self.jira, self.webex)

        # Load initial filters from the environment, if any.
        initial_filter_ids = [
            fid.strip()
            for fid in (self.config.JIRA_FILTER_IDS or "").split(",")
            if fid.strip()
        ]
        for filter_id in initial_filter_ids:
            logger.info("Registering initial filter from environment: %s", filter_id)
            success, message = self.filter_watcher.add_filter(filter_id)
            if not success:
                logger.warning("Could not register filter %s: %s", filter_id, message)

    def _process_filter_command(self, command: dict[str, Any]) -> str:
        if self.filter_watcher is None:
            return "Filter watching is not available."

        filter_id = command.get("filter_id")
        if command["command"] == "add_filter":
            if not filter_id:
                return "Please provide a filter ID, e.g. `/add_filter 12345`."
            success, message = self.filter_watcher.add_filter(filter_id)
            return message

        if command["command"] == "remove_filter":
            if not filter_id:
                return "Please provide a filter ID, e.g. `/remove_filter 12345`."
            success, message = self.filter_watcher.remove_filter(filter_id)
            return message

        if command["command"] == "list_filters":
            filters = self.filter_watcher.list_filters()
            if not filters:
                return "No filters are being watched."
            lines = ["**Watched filters:**"]
            for filter_id, info in filters.items():
                last_check = info.get("last_checked_at") or "never"
                lines.append(
                    f"- **{filter_id}**: `{info['jql']}` "
                    f"({info['issue_count']} tickets, last check: {last_check})"
                )
            return "\n".join(lines)

        return "Unknown filter command."

    def _process_message(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        if not message_id or message_id in self.processed_message_ids:
            return

        if WebexClient.is_from_bot(message, self.bot_person_id):
            self.processed_message_ids.add(message_id)
            return

        text = message.get("text", "")
        command = parse_command(text)

        if command["command"] == "help":
            self.webex.send_message(build_help_message())
        elif command["command"] in ("add_filter", "remove_filter", "list_filters"):
            reply = self._process_filter_command(command)
            self.webex.send_message(reply)

        elif command["command"] == "jira":
            issue_key = command["issue_key"]
            logger.info("Processing Jira command for %s", issue_key)
            try:
                reply = self.jira.build_reply(issue_key)
            except JiraAuthError as exc:
                logger.error("Jira auth error for %s: %s", issue_key, exc)
                reply = (
                    "Jira authentication failed. Please check the bot's "
                    "JIRA_USERNAME, JIRA_API_TOKEN and JIRA_URL configuration."
                )
            except Exception as exc:
                logger.exception("Failed to fetch Jira issue %s", issue_key)
                reply = (
                    f"Sorry, I couldn't retrieve **{issue_key}**. "
                    f"Error: {exc}"
                )
            self.webex.send_message(reply)
        else:
            # Do not reply to unrelated messages to avoid spam.
            pass

        self.processed_message_ids.add(message_id)

    def _prune_processed_ids(self, messages: list[dict[str, Any]]) -> None:
        """Keep only IDs that are still in the recent message window."""
        recent_ids = {msg.get("id") for msg in messages}
        self.processed_message_ids.intersection_update(recent_ids)

    def _should_check_filters(self) -> bool:
        return (
            self.filter_watcher is not None
            and self.config.FILTER_POLL_INTERVAL_SECONDS > 0
            and time.time() - self._last_filter_check
            >= self.config.FILTER_POLL_INTERVAL_SECONDS
        )

    def run(self) -> None:
        logger.info(
            "Starting TMS Notifier bot. Polling interval: %s seconds",
            self.config.POLL_INTERVAL_SECONDS,
        )
        logger.info(
            "Filter check interval: %s seconds",
            self.config.FILTER_POLL_INTERVAL_SECONDS,
        )
        logger.info("Monitoring Webex room: %s", self.config.WEBEX_ROOM_ID)
        logger.info("Jira URL: %s", self.config.JIRA_URL)

        while True:
            try:
                messages = self.webex.get_messages()
                if messages:
                    # API returns newest first; process oldest first.
                    for message in reversed(messages):
                        self._process_message(message)
                    self._prune_processed_ids(messages)
            except WebexPermissionError as exc:
                logger.error("Webex permission error: %s", exc)
                logger.error("Stopping bot. Please fix Webex membership/scopes.")
                break
            except WebexServerError as exc:
                logger.warning("Webex server error: %s", exc)
            except Exception:
                logger.exception("Error during message polling cycle")

            if self._should_check_filters():
                try:
                    self.filter_watcher.check_filters()
                    self._last_filter_check = time.time()
                except Exception:
                    logger.exception("Error during filter check cycle")

            time.sleep(self.config.POLL_INTERVAL_SECONDS)


def main() -> int:
    try:
        bot = Bot(Config())
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Stopping bot")
    return 0


if __name__ == "__main__":
    sys.exit(main())

