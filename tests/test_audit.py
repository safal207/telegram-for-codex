from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from telegram_codex import client as client_module
from telegram_codex.client import ConfirmationRequired, TelegramGateway
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
            write_chat_allowlist=(frozenset({123}) if allow_writes else None),
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


class FakeEditClient:
    async def get_messages(self, chat_id: int, ids: int):
        return SimpleNamespace(out=True)

    async def edit_message(self, chat_id: int, message_id: int, text: str):
        return SimpleNamespace(
            id=message_id,
            chat_id=chat_id,
            sender_id=42,
            raw_text=text,
            date=None,
            out=True,
        )


def test_send_success_is_audited_without_message_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeSendClient())

    secret_text = "message body must never enter audit"
    asyncio.run(gateway.send_message(chat_id=123, text=secret_text, confirm=True))

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


def test_edit_success_is_audited_without_message_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeEditClient())

    asyncio.run(
        gateway.edit_message(
            chat_id=123, message_id=77, text="edited secret", confirm=True
        )
    )

    record = json.loads(audit_path.read_text("utf-8"))
    assert record == {
        "timestamp": record["timestamp"],
        "event": "edit",
        "status": "ok",
        "chat_id": 123,
        "message_id": 77,
    }
    assert "edited secret" not in audit_path.read_text("utf-8")


def test_denied_edit_is_audited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)

    class IncomingMessageClient:
        async def get_messages(self, chat_id: int, ids: int):
            return SimpleNamespace(out=False)

    _patch_ready(gateway, monkeypatch, IncomingMessageClient())

    with pytest.raises(PermissionError, match="Only your own outgoing"):
        asyncio.run(
            gateway.edit_message(
                chat_id=123, message_id=77, text="edited secret", confirm=True
            )
        )

    record = json.loads(audit_path.read_text("utf-8"))
    assert record["event"] == "edit"
    assert record["status"] == "denied"
    assert record["message_id"] == 77
    assert record["error_type"] == "PermissionError"
    assert "edited secret" not in audit_path.read_text("utf-8")


def test_denied_send_is_audited_without_raw_error_or_message_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, allow_writes=False, audit_log_path=audit_path)

    from telegram_codex.client import WritesDisabled

    with pytest.raises(WritesDisabled):
        asyncio.run(
            gateway.send_message(
                chat_id=123, text="denied secret body", confirm=True
            )
        )

    records = [json.loads(line) for line in audit_path.read_text("utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["event"] == "send"
    assert records[0]["status"] == "denied"
    assert records[0]["error_type"] == "WritesDisabled"
    assert "error" not in records[0]
    assert "denied secret body" not in audit_path.read_text("utf-8")


def test_missing_write_confirmation_is_denied_and_audited(
    tmp_path: Path,
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)

    with pytest.raises(ConfirmationRequired, match="confirm=true"):
        asyncio.run(
            gateway.send_message(
                chat_id=123, text="must not be sent", confirm=False
            )
        )

    record = json.loads(audit_path.read_text("utf-8"))
    assert record["event"] == "send"
    assert record["status"] == "denied"
    assert record["error_type"] == "ConfirmationRequired"
    assert "must not be sent" not in audit_path.read_text("utf-8")


def test_unexpected_send_error_is_audited_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)

    class BrokenSendClient:
        async def send_message(self, chat_id: int, text: str):
            raise RuntimeError("upstream secret must not be logged")

    _patch_ready(gateway, monkeypatch, BrokenSendClient())

    with pytest.raises(RuntimeError, match="upstream secret"):
        asyncio.run(
            gateway.send_message(chat_id=123, text="message secret", confirm=True)
        )

    records = [json.loads(line) for line in audit_path.read_text("utf-8").splitlines()]
    assert records[0]["event"] == "send"
    assert records[0]["status"] == "error"
    assert records[0]["error_type"] == "RuntimeError"
    audit_text = audit_path.read_text("utf-8")
    assert "upstream secret" not in audit_text
    assert "message secret" not in audit_text


def test_unexpected_edit_error_is_audited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)

    class BrokenEditClient:
        async def get_messages(self, chat_id: int, ids: int):
            raise RuntimeError("telegram unavailable")

    _patch_ready(gateway, monkeypatch, BrokenEditClient())

    with pytest.raises(RuntimeError, match="telegram unavailable"):
        asyncio.run(
            gateway.edit_message(
                chat_id=123, message_id=77, text="edited secret", confirm=True
            )
        )

    record = json.loads(audit_path.read_text("utf-8"))
    assert record["event"] == "edit"
    assert record["status"] == "error"
    assert record["message_id"] == 77
    assert record["error_type"] == "RuntimeError"
    assert "edited secret" not in audit_path.read_text("utf-8")


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


def test_read_audit_tail_is_bounded_and_reads_from_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    lines = [
        json.dumps({"event": "send", "status": "ok", "chat_id": value})
        for value in range(5)
    ]
    audit_path.write_bytes(
        b"x" * (2 * 1024 * 1024) + b"\n" + "\n".join(lines).encode("utf-8") + b"\n"
    )
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    original_fdopen = os.fdopen
    bytes_read = 0

    class TrackingReader:
        def __init__(self, handle) -> None:
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.handle.close()

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def read(self, size: int = -1):
            nonlocal bytes_read
            assert 0 <= size <= 8192
            data = self.handle.read(size)
            bytes_read += len(data)
            return data

    def tracked_fdopen(descriptor: int, *args, **kwargs):
        handle = original_fdopen(descriptor, *args, **kwargs)
        if args and args[0] == "rb":
            return TrackingReader(handle)
        return handle

    monkeypatch.setattr(client_module.os, "fdopen", tracked_fdopen)

    records = gateway.read_audit_tail(limit=3)

    assert [record["chat_id"] for record in records] == [2, 3, 4]
    assert 0 < bytes_read <= 8192


def test_read_audit_tail_empty_when_audit_disabled_or_missing(tmp_path: Path) -> None:
    disabled = _gateway(tmp_path, audit_log_path=None)
    missing = _gateway(tmp_path, audit_log_path=tmp_path / "nope.jsonl")

    assert disabled.read_audit_tail() == []
    assert missing.read_audit_tail() == []


def test_audit_rotation_keeps_only_bounded_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "audit.jsonl"
    main_payload = b"m" * 480
    audit_path.write_bytes(main_payload)
    audit_path.with_name("audit.jsonl.1").write_bytes(b"older-one")
    audit_path.with_name("audit.jsonl.2").write_bytes(b"oldest-two")
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeSendClient())
    monkeypatch.setattr(client_module, "_AUDIT_MAX_BYTES", 512)
    monkeypatch.setattr(client_module, "_AUDIT_BACKUP_COUNT", 2)

    asyncio.run(gateway.send_message(chat_id=123, text="rotate", confirm=True))

    current = json.loads(audit_path.read_text("utf-8"))
    assert current["event"] == "send"
    assert current["status"] == "ok"
    assert audit_path.stat().st_size <= 512
    assert audit_path.with_name("audit.jsonl.1").read_bytes() == main_payload
    assert audit_path.with_name("audit.jsonl.2").read_bytes() == b"older-one"
    assert not audit_path.with_name("audit.jsonl.3").exists()
    if os.name != "nt":
        for path in (
            audit_path,
            audit_path.with_name("audit.jsonl.1"),
            audit_path.with_name("audit.jsonl.2"),
        ):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_audit_directory_and_file_are_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_path = tmp_path / "private-audit" / "audit.jsonl"
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeSendClient())

    asyncio.run(gateway.send_message(chat_id=123, text="hello", confirm=True))

    assert stat.S_IMODE(audit_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(audit_path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics are unavailable on Windows")
def test_audit_refuses_symlink_without_overwriting_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit_directory = tmp_path / "private-audit"
    audit_directory.mkdir(mode=0o700)
    os.chmod(audit_directory, 0o700)
    target = audit_directory / "target.txt"
    target.write_text("do-not-touch", encoding="utf-8")
    os.chmod(target, 0o600)
    audit_path = audit_directory / "audit.jsonl"
    audit_path.symlink_to(target)
    gateway = _gateway(tmp_path, audit_log_path=audit_path)
    _patch_ready(gateway, monkeypatch, FakeSendClient())

    result = asyncio.run(
        gateway.send_message(chat_id=123, text="hello", confirm=True)
    )

    assert result["message_id"] == 5
    assert target.read_text(encoding="utf-8") == "do-not-touch"
    assert audit_path.is_symlink()


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
