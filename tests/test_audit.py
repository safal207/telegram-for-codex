from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_codex.client import TelegramGateway
from telegram_codex.config import Settings


def _gateway(
    tmp_path: Path,
    *,
    allow_writes: bool = True,
    audit_log_path: Path | None = None,
) -> TelegramGateway:
    return TelegramGateway(
        Settings(
            api_id=1,
            api_hash="test-hash",
            phone=None,
            session_path=tmp_path / "telegram-test",
            allow_writes=allow_writes,
            audit_log_path=audit_log_path,
        )
    )


def _patch_ready(
    gateway: TelegramGateway,
    monkeypatch: pytest.MonkeyPatch,
    fake_client: object,
) -> None:
    async def fake_ensure_ready():
        return fake_client

    monkeypatch.setattr(gateway, "ensure_ready", fake_ensure_ready)


def _sent_message() -> SimpleNamespace:
    return SimpleNamespace(
        id=5,
        chat_id=123,
        sender_id=42,
        raw_text="hello",
        date=None,
        out=True,
    )


class FakeSendClient:
    async def send_message(self, chat_id: int, text: str):
        return _sent_message()


def test_send_success_is_audited_without_message_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeSendClient())

    secret_text = "message body must never enter audit"
    asyncio.run(gateway.send_message(chat_id=123, text=secret_text))

    records = [json.loads(line) for line in audit_path.read_text("utf-8").splitlines()]
    assert len(records) == 1
    assert records[0] == {
        "timestamp": records[0]["timestamp"],
        "event": "send",
        "status": "ok",
        "chat_id": 123,
        "message_id": 5,
    }
    assert secret_text not in audit_path.read_text("utf-8")
    assert "text" not in records[0]
    assert "text_preview" not in records[0]


def test_denied_send_is_audited_without_raw_error_or_message_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, allow_writes=False, audit_log_path=audit_path)

    from telegram_codex.client import WritesDisabled

    with pytest.raises(WritesDisabled):
        asyncio.run(gateway.send_message(chat_id=123, text="denied secret body"))

    records = [json.loads(line) for line in audit_path.read_text("utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["event"] == "send"
    assert records[0]["status"] == "denied"
    assert records[0]["error_type"] == "WritesDisabled"
    assert "error" not in records[0]
    assert "denied secret body" not in audit_path.read_text("utf-8")


def test_reads_are_never_audited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audit_path = tmp_path / "audit.jsonl"

    class FakeReadClient:
        async def get_messages(self, chat_id: int, limit: int):
            return []

    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeReadClient())

    asyncio.run(gateway.get_messages(chat_id=123, limit=10))

    assert not audit_path.exists()


def test_read_audit_tail_parses_and_skips_broken_lines(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    good = '{"timestamp": "t", "event": "send", "status": "ok", "chat_id": 1}'
    audit_path.write_text("not-json\n" + good + "\n", encoding="utf-8")
    gateway = _gateway(tmp_path, audit_log_path=audit_path)

    records = gateway.read_audit_tail(limit=10)

    assert records == [{"timestamp": "t", "event": "send", "status": "ok", "chat_id": 1}]


def test_read_audit_tail_empty_when_audit_disabled_or_missing(tmp_path: Path) -> None:
    disabled = _gateway(tmp_path, audit_log_path=None)
    missing = _gateway(tmp_path, audit_log_path=tmp_path / "nope.jsonl")

    assert disabled.read_audit_tail() == []
    assert missing.read_audit_tail() == []


def test_whoami_reports_unauthorized_session(tmp_path: Path) -> None:
    class FakeUnauthorizedClient:
        def is_connected(self) -> bool:
            return True

        async def is_user_authorized(self) -> bool:
            return False

    gateway = _gateway(tmp_path)
    gateway.client = FakeUnauthorizedClient()

    info = asyncio.run(gateway.whoami())

    assert info["authorized"] is False
    assert "telegram-codex-auth" in info["hint"]
    assert info["allow_writes"] is True


def test_whoami_reports_authorized_user(tmp_path: Path) -> None:
    class FakeAuthorizedClient:
        def is_connected(self) -> bool:
            return True

        async def is_user_authorized(self) -> bool:
            return True

        async def get_me(self):
            return SimpleNamespace(id=42, username="tester", first_name="Test", phone="+79990000000")

    gateway = TelegramGateway(
        Settings(
            api_id=1,
            api_hash="test-hash",
            phone=None,
            session_path=tmp_path / "telegram-test",
            allow_writes=True,
            write_chat_allowlist=frozenset({1}),
        )
    )
    gateway.client = FakeAuthorizedClient()

    info = asyncio.run(gateway.whoami())

    assert info["authorized"] is True
    assert info["user_id"] == 42
    assert info["username"] == "tester"
    assert info["write_chat_allowlist"] == [1]
