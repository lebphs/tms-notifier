"""Application configuration loaded from environment variables."""
import logging
import os

from dotenv import find_dotenv, load_dotenv

logger = logging.getLogger(__name__)

# Look for .env starting from this file's directory and walking up.
_DOTENV_PATH = find_dotenv(usecwd=False)
if _DOTENV_PATH:
    logger.info("Loading environment variables from %s", _DOTENV_PATH)
    load_dotenv(_DOTENV_PATH, override=False)
else:
    logger.warning(
        ".env file not found. Relying on environment variables already set."
    )


class Config:
    WEBEX_BOT_TOKEN = os.environ.get("WEBEX_BOT_TOKEN")
    WEBEX_ROOM_ID = os.environ.get("WEBEX_ROOM_ID")

    JIRA_URL = os.environ.get("JIRA_URL", "https://tms.netcracker.com").rstrip("/")
    JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

    POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "10"))

    # Optional filter monitoring configuration.
    JIRA_FILTER_IDS = os.environ.get("JIRA_FILTER_IDS", "").strip()
    FILTER_POLL_INTERVAL_SECONDS = int(
        os.environ.get("FILTER_POLL_INTERVAL_SECONDS", "60")
    )

    @classmethod
    def validate(cls):
        missing = []
        for name in (
            "WEBEX_BOT_TOKEN",
            "WEBEX_ROOM_ID",
            "JIRA_API_TOKEN",
        ):
            if not getattr(cls, name):
                missing.append(name)
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
