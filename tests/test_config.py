import os
import stat
from pathlib import Path

import pytest

from telegram_codex.config import ConfigurationError, Settings, _as_bool, _parse_allowlist


def test_as_bool_defaults_false() -> None:
    assert _as_bool(None) is False


def test_as_bool_true_values() -> None:
    for value in ("1", "true", "TRUE", "yes", "on"):
        assert _as_bool(value) is True


def test_as_bool_false_values() -> None:
    for value in ("0", "false", "no", "off", "anything"):
        assert _as_bool(value) is False


def test_parse_allowlist_empty_means_not_configured() -> None:
    assert _parse_allowlist(None) is None
    assert _parse_allowlist("") is None
    assert _parse_allowlist("  ") is None


def test_parse_allowlist_parses_ids() -> None:
    assert _parse_allowlist("777000, 42,") == frozenset({777000, 42})


def test_parse_allowlist_rejects_non_integers() -> None:
    with pytest.raises(ConfigurationError, match="comma-separated integers"):
        _parse_allowlist("777000,abc")


def _set_base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.delenv("TELEGRAM_SESSION_STRING", raising=False)
    monkeypatch.delenv("TELEGRAM_SESSION_STRING_FILE", raising=False)
    monkeypatch.delenv("TELEGRAM_SESSION_PATH", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("TELEGRAM_WRITE_CHAT_ALLOWLIST", raising=False)
    monkeypatch.delenv("TELEGRAM_AUDIT_LOG_PATH", raising=False)


def test_from_env_defaults_writes_off_and_audit_on(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)

    settings = Settings.from_env()

    assert settings.session_mode == "file"
    assert settings.session_string is None
    assert settings.allow_writes is False
    assert settings.write_chat_allowlist is None
    assert settings.audit_log_path == Path(".telegram/audit.jsonl")
    assert (tmp_path / ".telegram" / "audit.jsonl").parent.exists()


def test_from_env_parses_allowlist_and_audit_off(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_WRITE_CHAT_ALLOWLIST", "777000,42")
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")

    settings = Settings.from_env()

    assert settings.write_chat_allowlist == frozenset({777000, 42})
    assert settings.audit_log_path is None


@pytest.mark.parametrize("allowlist", [None, "", "   ", ",,"])
def test_from_env_rejects_writes_without_non_empty_allowlist(
    allowlist: str | None, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOW_WRITES", "true")
    if allowlist is not None:
        monkeypatch.setenv("TELEGRAM_WRITE_CHAT_ALLOWLIST", allowlist)

    with pytest.raises(ConfigurationError, match="requires a non-empty"):
        Settings.from_env()


def test_from_env_accepts_writes_with_integer_allowlist(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOW_WRITES", "true")
    monkeypatch.setenv("TELEGRAM_WRITE_CHAT_ALLOWLIST", "123,-456")

    settings = Settings.from_env()

    assert settings.allow_writes is True
    assert settings.write_chat_allowlist == frozenset({123, -456})


@pytest.mark.parametrize("collision", ["active-audit", "audit-backup"])
def test_from_env_rejects_credential_and_audit_path_collisions(
    collision: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    audit_path = tmp_path / "private" / "audit.jsonl"
    session_string_path = (
        audit_path
        if collision == "active-audit"
        else audit_path.with_name("audit.jsonl.1")
    )
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_string_path))

    with pytest.raises(ConfigurationError, match="paths must be distinct"):
        Settings.from_env()

    assert not audit_path.parent.exists()


def test_from_env_rejects_collision_before_reading_session_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    shared_path = tmp_path / "private" / "audit.jsonl"
    shared_path.parent.mkdir()
    shared_path.write_text("must-not-be-read", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", str(shared_path))
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(shared_path))

    def unexpected_read(*args, **kwargs) -> str:
        raise AssertionError("credential file was read before collision validation")

    monkeypatch.setattr(
        "telegram_codex.config._read_private_text_file", unexpected_read
    )

    with pytest.raises(ConfigurationError, match="paths must be distinct"):
        Settings.from_env()


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links are unavailable")
def test_from_env_rejects_hardlinked_credential_and_audit_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    private_directory = tmp_path / "private"
    private_directory.mkdir()
    session_string_path = private_directory / "session.string"
    session_string_path.write_text("credential", encoding="utf-8")
    audit_path = private_directory / "audit.jsonl"
    os.link(session_string_path, audit_path)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_string_path))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", str(audit_path))

    with pytest.raises(ConfigurationError, match="hard-link aliases"):
        Settings.from_env()


def test_from_env_loads_default_connect_session_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    private_directory = tmp_path / ".telegram"
    private_directory.mkdir(mode=0o700)
    if os.name != "nt":
        os.chmod(private_directory, 0o700)
    path = private_directory / "remote.session.string"
    path.write_text("from-default-connect-file\n", encoding="utf-8")

    settings = Settings.from_env()

    assert settings.session_string == "from-default-connect-file"
    assert settings.session_mode == "string"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_from_env_rejects_preexisting_non_private_session_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")
    session_path = tmp_path / "private-session" / "codex"
    session_path.parent.mkdir(mode=0o777)
    os.chmod(session_path.parent, 0o755)
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(session_path))

    with pytest.raises(ConfigurationError, match="mode 0700"):
        Settings.from_env()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are not available on Windows")
def test_from_env_hardens_existing_database_and_sidecars_inside_private_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")
    session_path = tmp_path / "private-session" / "codex"
    session_path.parent.mkdir(mode=0o700)
    os.chmod(session_path.parent, 0o700)
    session_file = Path(f"{session_path}.session")
    session_files = [
        session_file,
        Path(f"{session_file}-journal"),
        Path(f"{session_file}-shm"),
        Path(f"{session_file}-wal"),
    ]
    for path in session_files:
        path.write_text("sqlite-placeholder", encoding="utf-8")
        os.chmod(path, 0o666)
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(session_path))

    Settings.from_env()

    assert stat.S_IMODE(session_path.parent.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in session_files)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics are unavailable on Windows")
def test_from_env_rejects_symlink_session_sidecar(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")
    session_path = tmp_path / "private-session" / "codex"
    session_path.parent.mkdir(mode=0o700)
    os.chmod(session_path.parent, 0o700)
    target = session_path.parent / "outside"
    target.write_text("do-not-touch", encoding="utf-8")
    os.chmod(target, 0o600)
    Path(f"{session_path}.session-wal").symlink_to(target)
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(session_path))

    with pytest.raises(ConfigurationError, match="regular non-symlink file"):
        Settings.from_env()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics are unavailable on Windows")
def test_from_env_rejects_symlink_session_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")
    real_directory = tmp_path / "real-session"
    real_directory.mkdir(mode=0o700)
    os.chmod(real_directory, 0o700)
    linked_directory = tmp_path / "linked-session"
    linked_directory.symlink_to(real_directory, target_is_directory=True)
    monkeypatch.setenv(
        "TELEGRAM_SESSION_PATH", str(linked_directory / "codex")
    )

    with pytest.raises(ConfigurationError, match="real directory"):
        Settings.from_env()


def test_created_storage_does_not_use_unsupported_path_chmod(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)

    def unexpected_path_chmod(*args, **kwargs) -> None:
        raise AssertionError("created private directories must not require path chmod")

    monkeypatch.setattr("telegram_codex.config.os.chmod", unexpected_path_chmod)

    settings = Settings.from_env()

    assert settings.session_mode == "file"
    assert (tmp_path / ".telegram").is_dir()
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / ".telegram").stat().st_mode) == 0o700


def test_from_env_prefers_string_session_for_cloud(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "  secret-session  ")
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", "unused/session")
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")

    settings = Settings.from_env()

    assert settings.session_mode == "string"
    assert settings.session_string == "secret-session"
    assert settings.session_path == Path("unused/session")
    assert not (tmp_path / "unused").exists()
