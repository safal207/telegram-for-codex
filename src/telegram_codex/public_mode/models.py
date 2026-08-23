from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PublicAction(str, Enum):
    SEND = "send"
    EDIT = "edit"
    MARK_READ = "mark_read"
    DELETE_SENT = "delete_sent"
    DELETE_ANY = "delete_any"


class EventKind(str, Enum):
    NEW = "new"
    EDITED = "edited"
    DELETED = "deleted"


class RetentionMode(str, Enum):
    EPHEMERAL = "ephemeral"
    TTL = "ttl"


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    mode: RetentionMode = RetentionMode.EPHEMERAL
    ttl_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.mode is RetentionMode.TTL:
            if self.ttl_seconds is None or self.ttl_seconds <= 0:
                raise ValueError("TTL retention requires ttl_seconds > 0")
        elif self.ttl_seconds is not None:
            raise ValueError("Ephemeral retention must not set ttl_seconds")


@dataclass(frozen=True, slots=True)
class BusinessRights:
    can_reply: bool = False
    can_read_messages: bool = False
    can_delete_sent_messages: bool = False
    can_delete_all_messages: bool = False

    @classmethod
    def from_bot_api(cls, value: dict[str, Any] | None) -> "BusinessRights":
        value = value or {}
        return cls(
            can_reply=bool(value.get("can_reply", False)),
            can_read_messages=bool(value.get("can_read_messages", False)),
            can_delete_sent_messages=bool(value.get("can_delete_sent_messages", False)),
            can_delete_all_messages=bool(value.get("can_delete_all_messages", False)),
        )


@dataclass(frozen=True, slots=True)
class BusinessConnection:
    connection_id: str
    user_id: int
    user_chat_id: int
    connected_at: datetime
    rights: BusinessRights
    is_enabled: bool

    @classmethod
    def from_bot_api(cls, value: dict[str, Any]) -> "BusinessConnection":
        user = value.get("user") or {}
        return cls(
            connection_id=str(value["id"]),
            user_id=int(user["id"]),
            user_chat_id=int(value["user_chat_id"]),
            connected_at=datetime.fromtimestamp(int(value["date"]), tz=timezone.utc),
            rights=BusinessRights.from_bot_api(value.get("rights")),
            is_enabled=bool(value.get("is_enabled", False)),
        )


@dataclass(frozen=True, slots=True)
class BusinessMessageEvent:
    connection_id: str
    chat_id: int
    message_id: int
    kind: EventKind
    occurred_at: datetime
    text: str = ""
    outgoing: bool = False

    @classmethod
    def from_message_payload(
        cls,
        *,
        connection_id: str,
        message: dict[str, Any],
        kind: EventKind,
    ) -> "BusinessMessageEvent":
        chat = message.get("chat") or {}
        return cls(
            connection_id=connection_id,
            chat_id=int(chat["id"]),
            message_id=int(message["message_id"]),
            kind=kind,
            occurred_at=datetime.fromtimestamp(int(message["date"]), tz=timezone.utc),
            text=str(message.get("text") or message.get("caption") or ""),
            outgoing=bool(message.get("sender_business_bot")),
        )
