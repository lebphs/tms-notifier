"""Webex client wrapper for reading room messages and sending replies."""
from __future__ import annotations

import logging
from typing import Any

from webexteamssdk import WebexTeamsAPI
from webexteamssdk.exceptions import ApiError

logger = logging.getLogger(__name__)


class WebexPermissionError(PermissionError):
    """Raised when the bot cannot read/write the configured Webex room."""


class WebexServerError(RuntimeError):
    """Raised when Webex returns a 5xx transient server error."""


class WebexClient:
    """Thin wrapper around Cisco Webex Teams SDK."""

    def __init__(self, bot_token: str, room_id: str):
        self.api = WebexTeamsAPI(access_token=bot_token)
        self.room_id = room_id

    @staticmethod
    def _message_to_dict(message: Any) -> dict[str, Any]:
        """Convert a Webex SDK message object to a plain dictionary."""
        if hasattr(message, "to_dict"):
            return message.to_dict()
        return dict(message)

    @staticmethod
    def _translate_api_error(exc: ApiError, action: str) -> Exception:
        """Return a more readable exception for common Webex errors."""
        status = None
        try:
            status = exc.response.status_code
        except AttributeError:
            pass

        if status == 403:
            return WebexPermissionError(
                f"Cannot {action} in Webex room {exc.response.url}. "
                "Ensure the bot is a member of the room and the token has "
                "the required scopes (messages_read, messages_write, "
                "rooms_read, people_read)."
            )
        if status == 404:
            return ValueError(
                f"Webex room not found while {action}. Check WEBEX_ROOM_ID."
            )
        if status == 401:
            return PermissionError(
                f"Webex token is invalid or expired while {action}."
            )
        if status is not None and status >= 500:
            return WebexServerError(
                f"Webex returned {status} while {action}; this is usually "
                "transient and the bot will retry on the next poll."
            )
        return exc

    def get_messages(self, max_messages: int = 50) -> list[dict[str, Any]]:
        """Return recent messages from the configured room as plain dicts.

        Messages are returned newest-first by the Webex API.
        """
        try:
            messages = list(
                self.api.messages.list(roomId=self.room_id, max=max_messages)
            )
        except ApiError as exc:
            raise self._translate_api_error(exc, "read messages")
        return [self._message_to_dict(msg) for msg in messages]

    def send_message(self, text: str) -> dict[str, Any]:
        """Send a markdown message to the configured room."""
        try:
            message = self.api.messages.create(
                roomId=self.room_id, markdown=text
            )
        except ApiError as exc:
            raise self._translate_api_error(exc, "send message")
        logger.info("Sent message id=%s", getattr(message, "id", "unknown"))
        return self._message_to_dict(message)

    @staticmethod
    def is_from_bot(message: dict[str, Any], bot_person_id: str) -> bool:
        """Check whether the message was sent by the bot itself."""
        person_id = message.get("personId")
        return bool(person_id and person_id == bot_person_id)
