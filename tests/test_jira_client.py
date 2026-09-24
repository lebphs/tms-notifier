"""Tests for the Jira client."""
import pytest
import responses

from bot.jira_client import JiraClient


@pytest.fixture
def client():
    return JiraClient(
        base_url="https://jira.example.com",
        token="token",
    )


def _mock_issue():
    issue_payload = {
        "key": "PROJ-123",
        "fields": {
            "summary": "Test summary",
            "description": "Test description",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "John Doe"},
        },
    }
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/issue/PROJ-123",
        json=issue_payload,
        status=200,
    )


def _mock_comments(count):
    comments = [
        {
            "author": {"displayName": f"Author {i}"},
            "created": f"2024-01-0{i}T00:00:00.000+0000",
            "body": f"Comment body {i}",
        }
        for i in range(1, count + 1)
    ]
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/issue/PROJ-123/comment",
        json={"comments": comments},
        status=200,
    )
    return comments


@responses.activate
def test_build_reply_success(client):
    _mock_issue()
    comments = _mock_comments(count=3)

    reply = client.build_reply("PROJ-123")

    assert "PROJ-123" in reply
    assert "Test summary" in reply
    assert "In Progress" in reply
    assert "John Doe" in reply
    assert "Test description" in reply
    assert "https://jira.example.com/browse/PROJ-123" in reply

    assert "**Last 3 comments**" in reply
    for i, comment in enumerate(comments, start=1):
        assert f"{i}. by {comment['author']['displayName']}" in reply
        assert comment["body"] in reply


@responses.activate
def test_build_reply_no_comments(client):
    _mock_issue()
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/issue/PROJ-123/comment",
        json={"comments": []},
        status=200,
    )

    reply = client.build_reply("PROJ-123")

    assert "**Last 3 comments**: _No comments yet_" in reply


@responses.activate
def test_build_reply_one_comment(client):
    _mock_issue()
    _mock_comments(count=1)

    reply = client.build_reply("PROJ-123")

    assert "**Last 3 comments**" in reply
    assert "1. by Author 1" in reply
    assert "Comment body 1" in reply
    assert "2. by" not in reply


@responses.activate
def test_build_reply_two_comments(client):
    _mock_issue()
    _mock_comments(count=2)

    reply = client.build_reply("PROJ-123")

    assert "1. by Author 1" in reply
    assert "2. by Author 2" in reply
    assert "3. by" not in reply


@responses.activate
def test_get_last_comments_limit(client):
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/issue/PROJ-123/comment",
        json={
            "comments": [
                {"author": {"displayName": "Author 1"}, "body": "Body 1"},
                {"author": {"displayName": "Author 2"}, "body": "Body 2"},
            ]
        },
        status=200,
    )

    comments = client.get_last_comments("PROJ-123", limit=2)

    assert len(comments) == 2
    assert comments[0]["author"]["displayName"] == "Author 1"


@responses.activate
def test_build_reply_issue_not_found(client):
    responses.add(
        responses.GET,
        "https://jira.example.com/rest/api/2/issue/UNKNOWN-1",
        json={"errorMessages": ["Issue does not exist"]},
        status=404,
    )

    reply = client.build_reply("UNKNOWN-1")
    assert "not found" in reply


def test_format_description_with_adf(client):
    adf = {"type": "doc", "content": [{"type": "paragraph"}]}
    result = client._format_description(adf)
    assert result == str(adf)


def test_format_description_empty(client):
    assert client._format_description(None) == "_No description_"
    assert client._format_description("") == "_No description_"
