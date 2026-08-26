from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from .config import (
    ConfigurationError,
    Settings,
    _ensure_private_directory,
    _harden_private_file,
    prepare_file_session_storage,
)

logger = logging.getLogger(__name__)

_MAX_READ_LIMIT = 100
_MAX_TELEGRAM_TEXT_LENGTH = 4096
_MAX_SEARCH_QUERY_LENGTH = 4096
_AUDIT_TAIL_BLOCK_BYTES = 8192
_AUDIT_TAIL_MAX_BYTES = 1024 * 1024
_AUDIT_MAX_BYTES = 10 * 1024 * 1024
_AUDIT_BACKUP_COUNT = 2


class TelegramNotAuthorized(RuntimeError):
    pass


class WritesDisabled(PermissionError):
    pass


class ChatNotAllowed(PermissionError):
    pass


class ConfirmationRequired(ValueError):
    pass


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _session_for(settings: Settings):
    if settings.session_string:
        return StringSession(settings.session_string)
    return str(settings.session_path)


def _clamp_read_limit(limit: int) -> int:
    return max(1, min(int(limit), _MAX_READ_LIMIT))


def _validate_message_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Telegram message text must be a non-empty string.")
    if len(text) > _MAX_TELEGRAM_TEXT_LENGTH:
        raise ValueError(
            f"Telegram message text must be at most {_MAX_TELEGRAM_TEXT_LENGTH} characters."
        )


def _validate_search_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Telegram search query must be a non-empty string.")
    if len(query) > _MAX_SEARCH_QUERY_LENGTH:
        raise ValueError(
            f"Telegram search query must be at most {_MAX_SEARCH_QUERY_LENGTH} characters."
        )


def require_write_confirmation(confirm: bool) -> None:
    if not confirm:
        raise ConfirmationRequired(
            "Pass confirm=true only after the user approves this write action."
        )


def _write_error_status(exc: Exception) -> str:
    if isinstance(exc, (PermissionError, TelegramNotAuthorized, ValueError)):
        return "denied"
    return "error"


class TelegramGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._harden_session_storage()
        try:
            self.client = TelegramClient(
                _session_for(settings), settings.api_id, settings.api_hash
            )
        finally:
            self._harden_session_storage()

    def _harden_session_storage(self) -> None:
        if self.settings.session_mode == "file":
            prepare_file_session_storage(self.settings.session_path)

    async def _connect_if_needed(self) -> None:
        if self.client.is_connected():
            self._harden_session_storage()
            return
        try:
            await self.client.connect()
        finally:
            # SQLiteSession may be created even when the connection attempt fails.
            self._harden_session_storage()

    async def ensure_ready(self) -> TelegramClient:
        await self._connect_if_needed()
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
        if not allowed:
            raise ChatNotAllowed(
                "Write actions require a non-empty TELEGRAM_WRITE_CHAT_ALLOWLIST; "
                "writes fail closed until chat IDs are configured explicitly."
            )
        if int(chat_id) not in allowed:
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
            _ensure_private_directory(path.parent)
            _harden_private_file(path)
            encoded = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
            self._rotate_audit_if_needed(path, len(encoded))
            flags = (
                os.O_APPEND
                | os.O_CREAT
                | os.O_WRONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(path, flags, 0o600)
            try:
                remaining = memoryview(encoded)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise OSError("partial audit record write")
                    remaining = remaining[written:]
            finally:
                os.close(descriptor)
            _harden_private_file(path)
        except (ConfigurationError, OSError):
            logger.warning("Failed to append to audit log %s", path, exc_info=True)

    @staticmethod
    def _audit_backup_path(path: Path, index: int) -> Path:
        return path.with_name(f"{path.name}.{index}")

    def _rotate_audit_if_needed(self, path: Path, incoming_bytes: int) -> None:
        if incoming_bytes > _AUDIT_MAX_BYTES:
            raise OSError("audit record exceeds maximum file size")
        if not os.path.lexists(path):
            return
        _harden_private_file(path)
        if path.stat().st_size + incoming_bytes <= _AUDIT_MAX_BYTES:
            return

        oldest = self._audit_backup_path(path, _AUDIT_BACKUP_COUNT)
        if os.path.lexists(oldest):
            _harden_private_file(oldest)
            oldest.unlink()
        for index in range(_AUDIT_BACKUP_COUNT - 1, 0, -1):
            source = self._audit_backup_path(path, index)
            if not os.path.lexists(source):
                continue
            _harden_private_file(source)
            target = self._audit_backup_path(path, index + 1)
            os.replace(source, target)
            _harden_private_file(target)
        first = self._audit_backup_path(path, 1)
        os.replace(path, first)
        _harden_private_file(first)

    def read_audit_tail(self, limit: int = 20) -> list[dict[str, Any]]:
        path = self.settings.audit_log_path
        if path is None or not os.path.lexists(path):
            return []
        limit = _clamp_read_limit(limit)
        blocks: list[bytes] = []
        newline_count = 0
        bytes_read = 0
        descriptor = -1
        try:
            _harden_private_file(path)
            flags = (
                os.O_RDONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(path, flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ConfigurationError(
                    f"Audit path must be a regular file: {path}"
                )
            if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077:
                raise ConfigurationError(
                    f"Audit file {path} must have POSIX mode 0600 or stricter"
                )
            handle = os.fdopen(descriptor, "rb")
            descriptor = -1
            with handle:
                handle.seek(0, os.SEEK_END)
                position = handle.tell()
                while (
                    position > 0
                    and newline_count <= limit
                    and bytes_read < _AUDIT_TAIL_MAX_BYTES
                ):
                    block_size = min(
                        _AUDIT_TAIL_BLOCK_BYTES,
                        position,
                        _AUDIT_TAIL_MAX_BYTES - bytes_read,
                    )
                    position -= block_size
                    handle.seek(position)
                    block = handle.read(block_size)
                    blocks.append(block)
                    newline_count += block.count(b"\n")
                    bytes_read += len(block)
        except (ConfigurationError, OSError):
            logger.warning("Failed to read audit log %s", path, exc_info=True)
            return []
        finally:
            if descriptor >= 0:
                os.close(descriptor)

        lines = b"".join(reversed(blocks)).splitlines()
        if position > 0 and lines:
            # The first line is potentially truncated because this is a bounded tail read.
            lines = lines[1:]
        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(record, dict):
                records.append(record)
        return records

    async def whoami(self) -> dict[str, Any]:
        await self._connect_if_needed()
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
                else []
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
        limit = _clamp_read_limit(limit)
        try:
            return await self._list_chats(limit=limit, unread_only=unread_only)
        except FloodWaitError as exc:
            raise RuntimeError(
                f"Telegram flood limit reached. Retry after {exc.seconds} seconds."
            ) from exc

    async def _list_chats(self, limit: int, unread_only: bool) -> list[dict[str, Any]]:
        client = await self.ensure_ready()
        result: list[dict[str, Any]] = []
        scan_limit = min(limit * 3, 300) if unread_only else limit
        async for dialog in client.iter_dialogs(limit=scan_limit):
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
        messages = await client.get_messages(chat_id, limit=_clamp_read_limit(limit))
        return [self._message_payload(message) for message in messages]

    async def search_messages(
        self, query: str, chat_id: int | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        _validate_search_query(query)
        client = await self.ensure_ready()
        entity = chat_id if chat_id is not None else None
        result: list[dict[str, Any]] = []
        async for message in client.iter_messages(
            entity, search=query, limit=_clamp_read_limit(limit)
        ):
            result.append(self._message_payload(message))
        return result

    async def send_message(
        self, chat_id: int, text: str, *, confirm: bool
    ) -> dict[str, Any]:
        try:
            require_write_confirmation(confirm)
            _validate_message_text(text)
            self._require_writes(chat_id)
            client = await self.ensure_ready()
            message = await client.send_message(chat_id, text)
            payload = self._message_payload(message)
        except Exception as exc:
            self._audit(
                "send",
                chat_id,
                status=_write_error_status(exc),
                error_type=type(exc).__name__,
            )
            raise
        self._audit(
            "send",
            chat_id,
            status="ok",
            message_id=payload["message_id"],
        )
        return payload

    async def edit_message(
        self, chat_id: int, message_id: int, text: str, *, confirm: bool
    ) -> dict[str, Any]:
        try:
            require_write_confirmation(confirm)
            _validate_message_text(text)
            self._require_writes(chat_id)
            client = await self.ensure_ready()
            original = await client.get_messages(chat_id, ids=message_id)
            if original is None:
                raise ValueError(f"Message {message_id} was not found in chat {chat_id}")
            if not getattr(original, "out", False):
                raise PermissionError("Only your own outgoing Telegram messages can be edited")
            edited = await client.edit_message(chat_id, message_id, text)
            payload = self._message_payload(edited)
        except Exception as exc:
            self._audit(
                "edit",
                chat_id,
                status=_write_error_status(exc),
                message_id=message_id,
                error_type=type(exc).__name__,
            )
            raise
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
