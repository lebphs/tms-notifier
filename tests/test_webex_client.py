"""Tests for the Webex client."""
from unittest.mock import MagicMock

import pytest
from webexteamssdk.exceptions import ApiError

from bot.webex_client import WebexClient, WebexPermissionError


def test_translate_api_error_403():
    import requests

    response = requests.Response()
    response.status_code = 403
    response.url = "https://webexapis.com/v1/messages"
    exc = ApiError(response)

    translated = WebexClient._translate_api_error(exc, "read messages")

    assert isinstance(translated, WebexPermissionError)
    assert "read messages" in str(translated)
    assert "Ensure the bot is a member" in str(translated)


def test_is_from_bot_true():
    assert WebexClient.is_from_bot({"personId": "bot-id"}, "bot-id") is True


def test_is_from_bot_false():
    assert WebexClient.is_from_bot({"personId": "user-id"}, "bot-id") is False


def test_message_to_dict_from_object():
    class FakeMessage:
        def to_dict(self):
            return {"id": "msg-1", "text": "hello"}

    assert WebexClient._message_to_dict(FakeMessage()) == {
        "id": "msg-1",
        "text": "hello",
    }


def test_send_message_logs_id():
    client = WebexClient.__new__(WebexClient)
    client.api = MagicMock()
    client.room_id = "room-1"
    created = MagicMock()
    created.id = "msg-42"
    created.to_dict.return_value = {"id": "msg-42", "text": "hello"}
    client.api.messages.create.return_value = created

    result = client.send_message("hello")

    client.api.messages.create.assert_called_once_with(
        roomId="room-1", markdown="hello"
    )
    assert result["id"] == "msg-42"
