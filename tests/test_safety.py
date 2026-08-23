from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_codex.client import (
    ChatNotAllowed,
    TelegramGateway,
    WritesDisabled,
)
from telegram_codex.config import Settings


def _gateway(
    tmp_path: Path,
    *,
    allow_writes: bool,
    write_chat_allowlist: frozenset[int] | None = None,
) -> TelegramGateway:
    return TelegramGateway(
        Settings(
            api_id=1,
            api_hash="test-hash",
            phone=None,
            session_path=tmp_path / "telegram-test",
            allow_writes=allow_writes,
            write_chat_allowlist=write_chat_allowlist,
        )
    )


def test_send_is_blocked_when_writes_are_disabled(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=False)

    with pytest.raises(WritesDisabled, match="Write actions are disabled"):
        asyncio.run(gateway.send_message(chat_id=123, text="should not send"))


def test_edit_rejects_incoming_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _gateway(tmp_path, allow_writes=True)

    class FakeClient:
        async def get_messages(self, chat_id: int, ids: int):
            return SimpleNamespace(out=False)

    fake_client = FakeClient()

    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)

    with pytest.raises(PermissionError, match="Only your own outgoing"):
        asyncio.run(
            gateway.edit_message(chat_id=123, message_id=456, text="must not edit")
        )


def test_edit_rejects_missing_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _gateway(tmp_path, allow_writes=True)

    class FakeClient:
        async def get_messages(self, chat_id: int, ids: int):
            return None

    fake_client = FakeClient()

    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)

    with pytest.raises(ValueError, match="was not found"):
        asyncio.run(gateway.edit_message(chat_id=123, message_id=999, text="missing"))


def test_send_blocked_when_chat_not_in_allowlist(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=True, write_chat_allowlist=frozenset({111}))

    with pytest.raises(ChatNotAllowed, match="not in TELEGRAM_WRITE_CHAT_ALLOWLIST"):
        asyncio.run(gateway.send_message(chat_id=222, text="should not send"))


def test_edit_blocked_when_chat_not_in_allowlist(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=True, write_chat_allowlist=frozenset({111}))

    with pytest.raises(ChatNotAllowed, match="not in TELEGRAM_WRITE_CHAT_ALLOWLIST"):
        asyncio.run(
            gateway.edit_message(chat_id=222, message_id=1, text="should not edit")
        )


def test_require_writes_passes_for_allowlisted_chat(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=True, write_chat_allowlist=frozenset({111}))

    gateway._require_writes(chat_id=111)
