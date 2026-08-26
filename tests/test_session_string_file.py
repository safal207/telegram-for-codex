from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from telegram_codex import client as client_module
from telegram_codex.client import TelegramGateway
from telegram_codex.config import ConfigurationError, Settings


def _base(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")
    monkeypatch.delenv("TELEGRAM_SESSION_STRING", raising=False)


def test_settings_loads_session_string_from_private_file(tmp_path, monkeypatch) -> None:
    _base(monkeypatch)
    path = tmp_path / "session.string"
    path.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(path))

    settings = Settings.from_env()

    assert settings.session_string == "from-file"
    assert settings.session_mode == "string"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_settings_hardens_session_string_file_and_directory(tmp_path, monkeypatch) -> None:
    _base(monkeypatch)
    path = tmp_path / "private-session-string" / "session.string"
    path.parent.mkdir(mode=0o700)
    os.chmod(path.parent, 0o700)
    path.write_text("from-file\n", encoding="utf-8")
    os.chmod(path, 0o666)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(path))

    settings = Settings.from_env()

    assert settings.session_string == "from-file"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics are unavailable on Windows")
def test_settings_rejects_symlink_session_string_file(tmp_path, monkeypatch) -> None:
    _base(monkeypatch)
    directory = tmp_path / "private-session-string"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    target = directory / "real-session.string"
    target.write_text("bearer-session", encoding="utf-8")
    os.chmod(target, 0o600)
    link = directory / "session.string"
    link.symlink_to(target)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(link))

    with pytest.raises(ConfigurationError, match="regular non-symlink file"):
        Settings.from_env()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_settings_rejects_permissive_session_file_when_chmod_fails(
    tmp_path, monkeypatch
) -> None:
    _base(monkeypatch)
    directory = tmp_path / "private-session-string"
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    path = directory / "session.string"
    path.write_text("bearer-session", encoding="utf-8")
    os.chmod(path, 0o644)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(path))

    def unavailable_permissions(*args, **kwargs) -> None:
        raise OSError("chmod unsupported")

    monkeypatch.setattr("telegram_codex.config.os.fchmod", unavailable_permissions)

    with pytest.raises(ConfigurationError, match="Unable to secure private file"):
        Settings.from_env()


def test_direct_secret_takes_precedence_over_session_file(tmp_path, monkeypatch) -> None:
    _base(monkeypatch)
    path = tmp_path / "session.string"
    path.write_text("from-file", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(path))
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "from-env")

    settings = Settings.from_env()

    assert settings.session_string == "from-env"


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links are unavailable")
def test_settings_rejects_session_file_with_unconfigured_hardlink(
    tmp_path, monkeypatch
) -> None:
    _base(monkeypatch)
    directory = tmp_path / "private-session-string"
    directory.mkdir(mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    path = directory / "session.string"
    path.write_text("bearer-session", encoding="utf-8")
    os.link(path, directory / "unconfigured-backup")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(path))

    with pytest.raises(ConfigurationError, match="must not have hard links"):
        Settings.from_env()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_gateway_hardens_session_file_created_by_telethon(tmp_path, monkeypatch) -> None:
    session_path = tmp_path / "private" / "codex"
    session_file = Path(f"{session_path}.session")

    class FakeTelegramClient:
        def __init__(self, session, api_id, api_hash) -> None:
            session_file.write_text("sqlite-placeholder", encoding="utf-8")
            os.chmod(session_file, 0o666)

    monkeypatch.setattr(client_module, "TelegramClient", FakeTelegramClient)

    TelegramGateway(
        Settings(
            api_id=1,
            api_hash="hash",
            phone=None,
            session_path=session_path,
        )
    )

    assert stat.S_IMODE(session_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(session_file.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_gateway_hardens_session_file_when_client_construction_fails(
    tmp_path, monkeypatch
) -> None:
    session_path = tmp_path / "private-failed" / "codex"
    session_file = Path(f"{session_path}.session")

    class BrokenTelegramClient:
        def __init__(self, session, api_id, api_hash) -> None:
            session_file.write_text("partial-sqlite", encoding="utf-8")
            os.chmod(session_file, 0o666)
            raise RuntimeError("client construction failed")

    monkeypatch.setattr(client_module, "TelegramClient", BrokenTelegramClient)

    with pytest.raises(RuntimeError, match="client construction failed"):
        TelegramGateway(
            Settings(
                api_id=1,
                api_hash="hash",
                phone=None,
                session_path=session_path,
            )
        )

    assert stat.S_IMODE(session_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(session_file.stat().st_mode) == 0o600
