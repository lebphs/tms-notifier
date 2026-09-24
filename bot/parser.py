"""Parse incoming Webex messages for bot commands."""
import re

ISSUE_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9]*-\d+")
FILTER_ID_PATTERN = re.compile(r"\d+")


def extract_issue_key(text: str) -> str | None:
    """Return the first Jira issue key found in the text, or None."""
    match = ISSUE_KEY_PATTERN.search(text)
    return match.group(0) if match else None


def extract_filter_id(text: str) -> str | None:
    """Return the first numeric filter ID found in the text, or None."""
    match = FILTER_ID_PATTERN.search(text)
    return match.group(0) if match else None


def parse_command(text: str) -> dict:
    """Parse a message text into a command and optional issue key.

    Supported commands:
      - /jira PROJ-123  -> {"command": "jira", "issue_key": "PROJ-123"}
      - PROJ-123        -> {"command": "jira", "issue_key": "PROJ-123"}
      - /add_filter ID  -> {"command": "add_filter", "filter_id": "ID"}
      - /remove_filter ID -> {"command": "remove_filter", "filter_id": "ID"}
      - /list_filters   -> {"command": "list_filters"}
      - help            -> {"command": "help"}
      - /help           -> {"command": "help"}
      - anything else   -> {"command": "unknown"}
    """
    text = (text or "").strip()
    if not text:
        return {"command": "unknown", "issue_key": None, "filter_id": None}

    lower = text.lower()
    if lower in ("help", "/help"):
        return {"command": "help", "issue_key": None, "filter_id": None}

    if lower.startswith("/add_filter") or lower.startswith("add_filter"):
        filter_id = extract_filter_id(text)
        return {
            "command": "add_filter",
            "issue_key": None,
            "filter_id": filter_id,
        }

    if lower.startswith("/remove_filter") or lower.startswith("remove_filter"):
        filter_id = extract_filter_id(text)
        return {
            "command": "remove_filter",
            "issue_key": None,
            "filter_id": filter_id,
        }

    if lower in ("/list_filters", "list_filters"):
        return {"command": "list_filters", "issue_key": None, "filter_id": None}

    issue_key = extract_issue_key(text)
    if issue_key:
        return {"command": "jira", "issue_key": issue_key, "filter_id": None}

    return {"command": "unknown", "issue_key": None, "filter_id": None}


def build_help_message() -> str:
    return (
        "**TMS Notifier Bot**\n\n"
        "Commands:\n"
        "- `/jira PROJ-123` — show Jira issue summary, status, assignee, description and last 3 comments\n"
        "- `PROJ-123` — same without slash command\n"
        "- `/add_filter 12345` — watch a Jira filter for new/updated tickets\n"
        "- `/remove_filter 12345` — stop watching a filter\n"
        "- `/list_filters` — show watched filters\n"
        "- `help` — show this message"
    )
