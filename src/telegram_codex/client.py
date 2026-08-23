from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from .config import Settings

logger = logging.getLogger(__name__)


class TelegramNotAuthorized(RuntimeError):
    pass


class WritesDisabled(PermissionError):
    pass


class ChatNotAllowed(PermissionError):
    pass


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _session_for(settings: Settings):
    if settings.session_string:
        return StringSession(settings.session_string)
    return str(settings.session_path)


class TelegramGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = TelegramClient(
            _session_for(settings), settings.api_id, settings.api_hash
        )

    async def ensure_ready(self) -> TelegramClient:
        if not self.client.is_connected():
            await self.client.connect()
        if not await self.client.is_user_authorized():
            raise TelegramNotAuthorized(
                "Telegram session is not authorized. Run `telegram-codex-auth` for a file "
                "session or `telegram-codex-auth-string` to generate a cloud session secret."
            )
        return self.client

    def _require_writes(self, chat_id: int) -> None:
        if not self.settings.allow_writes:
            raise WritesDisabled(
                "Write actions are disabled. Set TELEGRAM_ALLOW_WRITES=true only after "
                "configuring Codex/app approvals for send/edit actions."
            )
        allowed = self.settings.write_chat_allowlist
        if allowed is not None and int(chat_id) not in allowed:
            raise ChatNotAllowed(
                f"chat_id {chat_id} is not in TELEGRAM_WRITE_CHAT_ALLOWLIST; "
                "add it explicitly before writing to this chat."
            )

    def _audit(
        self,
        event: str,
        chat_id: int,
        *,
        status: str,
        message_id: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """Append metadata-only write audit records.

        Message text, previews, Telegram payloads, and raw exception strings are
        intentionally excluded. Audit answers who/what/where/when/result, not
        message content.
        """
        path = self.settings.audit_log_path
        if path is None:
            return
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "status": status,
            "chat_id": int(chat_id),
        }
        if message_id is not None:
            record["message_id"] = int(message_id)
        if error_type is not None:
            record["error_type"] = error_type
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Failed to append to audit log %s", path, exc_info=True)

    def read_audit_tail(self, limit: int = 20) -> list[dict[str, Any]]:
        path = self.settings.audit_log_path
        if path is None or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines[-max(limit, 0):]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    async def whoami(self) -> dict[str, Any]:
        if not self.client.is_connected():
            await self.client.connect()
        authorized = bool(await self.client.is_user_authorized())
        info: dict[str, Any] = {
            "authorized": authorized,
            "session_mode": self.settings.session_mode,
            "session_path": (
                str(self.settings.session_path)
                if self.settings.session_mode == "file"
                else None
            ),
            "allow_writes": self.settings.allow_writes,
            "write_chat_allowlist": (
                sorted(self.settings.write_chat_allowlist)
                if self.settings.write_chat_allowlist is not None
                else "all"
            ),
            "audit_log_path": (
                str(self.settings.audit_log_path)
                if self.settings.audit_log_path is not None
                else None
            ),
        }
        if not authorized:
            info["hint"] = (
                "Authorize a file session with `telegram-codex-auth` or generate a cloud "
                "StringSession with `telegram-codex-auth-string`."
            )
            return info
        me = await self.client.get_me()
        info["user_id"] = int(me.id)
        info["username"] = getattr(me, "username", None)
        info["first_name"] = getattr(me, "first_name", None)
        info["phone"] = getattr(me, "phone", None)
        return info

    async def list_chats(self, limit: int = 20, unread_only: bool = False) -> list[dict[str, Any]]:
        try:
            return await self._list_chats(limit=limit, unread_only=unread_only)
        except FloodWaitError as exc:
            raise RuntimeError(
                f"Telegram flood limit reached. Retry after {exc.seconds} seconds."
            ) from exc

    async def _list_chats(self, limit: int, unread_only: bool) -> list[dict[str, Any]]:
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
        try:
            self._require_writes(chat_id)
            client = await self.ensure_ready()
            message = await client.send_message(chat_id, text)
        except (WritesDisabled, ChatNotAllowed, TelegramNotAuthorized, FloodWaitError) as exc:
            self._audit(
                "send",
                chat_id,
                status="denied",
                error_type=type(exc).__name__,
            )
            raise
        payload = self._message_payload(message)
        self._audit(
            "send",
            chat_id,
            status="ok",
            message_id=payload["message_id"],
        )
        return payload

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> dict[str, Any]:
        try:
            self._require_writes(chat_id)
            client = await self.ensure_ready()
            original = await client.get_messages(chat_id, ids=message_id)
            if original is None:
                raise ValueError(f"Message {message_id} was not found in chat {chat_id}")
            if not getattr(original, "out", False):
                raise PermissionError("Only your own outgoing Telegram messages can be edited")
            edited = await client.edit_message(chat_id, message_id, text)
        except (WritesDisabled, ChatNotAllowed, TelegramNotAuthorized, FloodWaitError) as exc:
            self._audit(
                "edit",
                chat_id,
                status="denied",
                message_id=message_id,
                error_type=type(exc).__name__,
            )
            raise
        payload = self._message_payload(edited)
        self._audit(
            "edit",
            chat_id,
            status="ok",
            message_id=payload["message_id"],
        )
        return payload

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
