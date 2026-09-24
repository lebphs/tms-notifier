"""Tests for the command parser."""
import pytest

from bot.parser import build_help_message, extract_issue_key, parse_command


@pytest.mark.parametrize(
    "text,expected_key",
    [
        ("/jira PROJ-123", "PROJ-123"),
        ("PROJ-123", "PROJ-123"),
        ("  /jira   TEST-9999  ", "TEST-9999"),
        ("Can you check AB-1 please?", "AB-1"),
        ("No issue key here", None),
        ("", None),
    ],
)
def test_extract_issue_key(text, expected_key):
    assert extract_issue_key(text) == expected_key


@pytest.mark.parametrize(
    "text,expected_command,expected_key",
    [
        ("/jira PROJ-123", "jira", "PROJ-123"),
        ("PROJ-123", "jira", "PROJ-123"),
        ("help", "help", None),
        ("/help", "help", None),
        ("hello", "unknown", None),
        ("", "unknown", None),
    ],
)
def test_parse_command(text, expected_command, expected_key):
    result = parse_command(text)
    assert result["command"] == expected_command
    assert result["issue_key"] == expected_key


def test_build_help_message_contains_commands():
    help_text = build_help_message()
    assert "/jira" in help_text
    assert "help" in help_text
