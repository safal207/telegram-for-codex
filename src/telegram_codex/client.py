from __future__ import annotations

from datetime import datetime
from typing import Any

from telethon import TelegramClient

from .config import Settings


class TelegramNotAuthorized(RuntimeError):
    pass


class WritesDisabled(PermissionError):
    pass


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class TelegramGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = TelegramClient(
            str(settings.session_path), settings.api_id, settings.api_hash
        )

    async def ensure_ready(self) -> TelegramClient:
        if not self.client.is_connected():
            await self.client.connect()
        if not await self.client.is_user_authorized():
            raise TelegramNotAuthorized(
                "Telegram session is not authorized. Run `telegram-codex-auth` first."
            )
        return self.client

    def _require_writes(self) -> None:
        if not self.settings.allow_writes:
            raise WritesDisabled(
                "Write actions are disabled. Set TELEGRAM_ALLOW_WRITES=true only after "
                "configuring Codex/app approvals for send/edit actions."
            )

    async def list_chats(self, limit: int = 20, unread_only: bool = False) -> list[dict[str, Any]]:
        client = await self.ensure_ready()
        result: list[dict[str, Any]] = []
        async for dialog in client.iter_dialogs(limit=max(limit * 3, limit)):
            unread_count = int(dialog.unread_count or 0)
            if unread_only and unread_count == 0:
                continue
            entity = dialog.entity
            result.append(
                {
                    "chat_id": int(dialog.id),
                    "title": dialog.name,
                    "unread_count": unread_count,
                    "is_user": bool(dialog.is_user),
                    "is_group": bool(dialog.is_group),
                    "is_channel": bool(dialog.is_channel),
                    "username": getattr(entity, "username", None),
                }
            )
            if len(result) >= limit:
                break
        return result

    async def get_messages(self, chat_id: int, limit: int = 20) -> list[dict[str, Any]]:
        client = await self.ensure_ready()
        messages = await client.get_messages(chat_id, limit=limit)
        return [self._message_payload(message) for message in messages]

    async def search_messages(
        self, query: str, chat_id: int | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        client = await self.ensure_ready()
        entity = chat_id if chat_id is not None else None
        result: list[dict[str, Any]] = []
        async for message in client.iter_messages(entity, search=query, limit=limit):
            result.append(self._message_payload(message))
        return result

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        self._require_writes()
        client = await self.ensure_ready()
        message = await client.send_message(chat_id, text)
        return self._message_payload(message)

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> dict[str, Any]:
        self._require_writes()
        client = await self.ensure_ready()
        original = await client.get_messages(chat_id, ids=message_id)
        if original is None:
            raise ValueError(f"Message {message_id} was not found in chat {chat_id}")
        if not getattr(original, "out", False):
            raise PermissionError("Only your own outgoing Telegram messages can be edited")
        edited = await client.edit_message(chat_id, message_id, text)
        return self._message_payload(edited)

    @staticmethod
    def _message_payload(message: Any) -> dict[str, Any]:
        return {
            "message_id": int(message.id),
            "chat_id": int(message.chat_id) if message.chat_id is not None else None,
            "sender_id": int(message.sender_id) if message.sender_id is not None else None,
            "text": message.raw_text or "",
            "date": _iso(message.date),
            "outgoing": bool(getattr(message, "out", False)),
        }
