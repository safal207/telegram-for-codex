from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import BusinessConnection, BusinessMessageEvent, EventKind


@dataclass(frozen=True, slots=True)
class DeletedBusinessMessages:
    connection_id: str
    chat_id: int
    message_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ParsedBusinessUpdate:
    connection: BusinessConnection | None = None
    message: BusinessMessageEvent | None = None
    deleted: DeletedBusinessMessages | None = None


def parse_business_update(update: dict[str, Any]) -> ParsedBusinessUpdate | None:
    """Normalize the Telegram Bot API business-related update types we use.

    Unknown/non-business updates return None so the webhook can safely coexist
    with ordinary bot traffic later.
    """

    connection = update.get("business_connection")
    if isinstance(connection, dict):
        return ParsedBusinessUpdate(connection=BusinessConnection.from_bot_api(connection))

    for field, kind in (
        ("business_message", EventKind.NEW),
        ("edited_business_message", EventKind.EDITED),
    ):
        message = update.get(field)
        if isinstance(message, dict):
            connection_id = str(message.get("business_connection_id") or "")
            if not connection_id:
                raise ValueError(f"{field} is missing business_connection_id")
            return ParsedBusinessUpdate(
                message=BusinessMessageEvent.from_message_payload(
                    connection_id=connection_id,
                    message=message,
                    kind=kind,
                )
            )

    deleted = update.get("deleted_business_messages")
    if isinstance(deleted, dict):
        connection_id = str(deleted.get("business_connection_id") or "")
        chat = deleted.get("chat") or {}
        if not connection_id or "id" not in chat:
            raise ValueError("deleted_business_messages is missing routing fields")
        return ParsedBusinessUpdate(
            deleted=DeletedBusinessMessages(
                connection_id=connection_id,
                chat_id=int(chat["id"]),
                message_ids=tuple(int(value) for value in deleted.get("message_ids", [])),
            )
        )

    return None
