# TMS Notifier Webex Bot

A simple Webex bot that fetches Jira ticket details by issue key, replies in a Webex room, and monitors Jira filters for new or updated tickets.

## Features

- Polling-based message reading (no public URL required).
- Replies to commands like `/jira PROJ-123` or just `PROJ-123`.
- Watches Jira saved filters and notifies the room when:
  - a new ticket appears in the filter,
  - a tracked ticket changes status.
- Manage watched filters from chat with `/add_filter`, `/remove_filter`, `/list_filters`.
- Returns:
  - issue summary,
  - status,
  - assignee,
  - description,
  - last 3 comments,
  - direct link to Jira.

## Prerequisites

- Python 3.10+
- Webex bot token
- Webex room ID
- Jira API token

## Installation

1. Clone or open the project folder.
2. Create a virtual environment (recommended):

```bash
python -m venv venv
venv\Scripts\activate  # Windows
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
copy .env.example .env
```

| Variable | Description |
| --- | --- |
| `WEBEX_BOT_TOKEN` | Bot access token from Webex developer portal |
| `WEBEX_ROOM_ID` | ID of the Webex room to monitor |
| `JIRA_URL` | Jira base URL, e.g. `https://tms.company.com` |
| `JIRA_API_TOKEN` | Jira personal access token (sent as `Authorization: Bearer`) |
| `POLL_INTERVAL_SECONDS` | How often to check for new messages (default: 10) |
| `JIRA_FILTER_IDS` | Optional comma-separated saved filter IDs to watch (default: empty) |
| `FILTER_POLL_INTERVAL_SECONDS` | How often to check watched filters (default: 60) |

## Running the bot

```bash
python bot.py
```

The bot will poll the configured Webex room and reply to Jira commands.

Press `Ctrl+C` to stop.

## Commands

- `/jira PROJ-123` — fetch and display Jira issue details.
- `PROJ-123` — same as above.
- `/add_filter 12345` — start watching a Jira saved filter (by numeric ID).
- `/remove_filter 12345` — stop watching a filter.
- `/list_filters` — show watched filters and their last check status.
- `help` or `/help` — show usage help.

### Filter notifications

When a watched filter is checked:

1. The bot runs the filter's JQL and compares results with the previous snapshot.
2. If a new ticket appears or a tracked ticket's status changes, the bot posts a single message to the room with the changes.
3. The first check after adding a filter establishes the baseline silently, so you will not get a flood of old tickets.

Find a filter's ID in Jira from the filter URL (e.g. `https://tms.company.com/issues/?filter=12345`) or from the filter details page.

## Running tests

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest
```

## Project structure

```
tms-notifier/
├── bot.py                 # main entry point
├── config.py              # environment configuration
├── filters_state.json     # persisted state for watched filters (created at runtime)
├── requirements.txt
├── .env.example
├── README.md
├── bot/
│   ├── __init__.py
│   ├── parser.py          # command parsing
│   ├── jira_client.py     # Jira REST API client
│   ├── webex_client.py    # Webex SDK wrapper
│   └── filter_watcher.py  # filter monitoring and change detection
└── tests/
    ├── test_parser.py
    └── test_jira_client.py
```
