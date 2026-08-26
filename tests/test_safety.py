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
        asyncio.run(
            gateway.send_message(chat_id=123, text="should not send", confirm=True)
        )


def test_edit_rejects_incoming_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _gateway(
        tmp_path, allow_writes=True, write_chat_allowlist=frozenset({123})
    )

    class FakeClient:
        async def get_messages(self, chat_id: int, ids: int):
            return SimpleNamespace(out=False)

    fake_client = FakeClient()

    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)

    with pytest.raises(PermissionError, match="Only your own outgoing"):
        asyncio.run(
            gateway.edit_message(
                chat_id=123, message_id=456, text="must not edit", confirm=True
            )
        )


def test_edit_rejects_missing_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _gateway(
        tmp_path, allow_writes=True, write_chat_allowlist=frozenset({123})
    )

    class FakeClient:
        async def get_messages(self, chat_id: int, ids: int):
            return None

    fake_client = FakeClient()

    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)

    with pytest.raises(ValueError, match="was not found"):
        asyncio.run(
            gateway.edit_message(
                chat_id=123, message_id=999, text="missing", confirm=True
            )
        )


def test_send_blocked_when_chat_not_in_allowlist(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=True, write_chat_allowlist=frozenset({111}))

    with pytest.raises(ChatNotAllowed, match="not in TELEGRAM_WRITE_CHAT_ALLOWLIST"):
        asyncio.run(
            gateway.send_message(chat_id=222, text="should not send", confirm=True)
        )


def test_edit_blocked_when_chat_not_in_allowlist(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=True, write_chat_allowlist=frozenset({111}))

    with pytest.raises(ChatNotAllowed, match="not in TELEGRAM_WRITE_CHAT_ALLOWLIST"):
        asyncio.run(
            gateway.edit_message(
                chat_id=222, message_id=1, text="should not edit", confirm=True
            )
        )


@pytest.mark.parametrize("allowlist", [None, frozenset()])
def test_writes_fail_closed_when_allowlist_is_missing_or_empty(
    allowlist: frozenset[int] | None, tmp_path: Path
) -> None:
    gateway = _gateway(
        tmp_path, allow_writes=True, write_chat_allowlist=allowlist
    )

    with pytest.raises(ChatNotAllowed, match="require a non-empty"):
        asyncio.run(
            gateway.send_message(chat_id=123, text="should not send", confirm=True)
        )


@pytest.mark.parametrize("text", ["", "   \t\n", "x" * 4097])
def test_send_rejects_empty_or_oversized_text(tmp_path: Path, text: str) -> None:
    gateway = _gateway(
        tmp_path, allow_writes=True, write_chat_allowlist=frozenset({123})
    )

    with pytest.raises(ValueError, match="Telegram message text"):
        asyncio.run(gateway.send_message(chat_id=123, text=text, confirm=True))


def test_send_accepts_telegram_text_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(
        tmp_path, allow_writes=True, write_chat_allowlist=frozenset({123})
    )

    class FakeClient:
        async def send_message(self, chat_id: int, text: str):
            return SimpleNamespace(
                id=1,
                chat_id=chat_id,
                sender_id=42,
                raw_text=text,
                date=None,
                out=True,
            )

    async def fake_ensure_ready():
        return FakeClient()

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)

    result = asyncio.run(
        gateway.send_message(chat_id=123, text="x" * 4096, confirm=True)
    )

    assert len(result["text"]) == 4096


def test_unread_chat_scan_is_bounded_but_can_scan_past_result_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, allow_writes=False)

    class FakeClient:
        seen_limit: int | None = None

        async def iter_dialogs(self, limit: int):
            self.seen_limit = limit
            for index in range(limit):
                yield SimpleNamespace(
                    id=index,
                    name=f"Chat {index}",
                    unread_count=(1 if index in {3, 5} else 0),
                    entity=SimpleNamespace(username=None),
                    is_user=False,
                    is_group=True,
                    is_channel=False,
                )

    fake_client = FakeClient()

    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)

    result = asyncio.run(gateway.list_chats(limit=2, unread_only=True))

    assert fake_client.seen_limit == 6
    assert [chat["chat_id"] for chat in result] == [3, 5]


@pytest.mark.parametrize("query", ["", "   \t\n", "x" * 4097])
def test_search_rejects_empty_or_oversized_query(tmp_path: Path, query: str) -> None:
    gateway = _gateway(tmp_path, allow_writes=False)

    with pytest.raises(ValueError, match="Telegram search query"):
        asyncio.run(gateway.search_messages(query=query))


def test_search_accepts_query_boundary_and_clamps_read_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = _gateway(tmp_path, allow_writes=False)

    class FakeClient:
        calls: list[tuple[int | None, str, int]] = []

        async def iter_messages(
            self, entity: int | None, *, search: str, limit: int
        ):
            self.calls.append((entity, search, limit))
            if False:
                yield None

    fake_client = FakeClient()

    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)
    boundary_query = "x" * 4096

    assert asyncio.run(
        gateway.search_messages(
            query=boundary_query, chat_id=123, limit=1000
        )
    ) == []
    assert asyncio.run(gateway.search_messages(query="telegram", limit=0)) == []

    assert fake_client.calls == [
        (123, boundary_query, 100),
        (None, "telegram", 1),
    ]


def test_require_writes_passes_for_allowlisted_chat(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, allow_writes=True, write_chat_allowlist=frozenset({111}))

    gateway._require_writes(chat_id=111)
