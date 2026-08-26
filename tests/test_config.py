import os
import stat
from pathlib import Path

import pytest

from telegram_codex.config import (
    ConfigurationError,
    Settings,
    _as_bool,
    _parse_allowlist,
    resolve_user_config_path,
)
from telegram_codex.onboarding import SetupCredentials, write_setup_config


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
    monkeypatch.setattr(
        "telegram_codex.config.resolve_user_config_path",
        lambda **kwargs: Path.cwd() / ".telegram-codex" / "config.env",
    )
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    monkeypatch.delenv("TELEGRAM_SESSION_STRING", raising=False)
    monkeypatch.delenv("TELEGRAM_SESSION_STRING_FILE", raising=False)
    monkeypatch.delenv("TELEGRAM_SESSION_PATH", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_WRITES", raising=False)
    monkeypatch.delenv("TELEGRAM_WRITE_CHAT_ALLOWLIST", raising=False)
    monkeypatch.delenv("TELEGRAM_AUDIT_LOG_PATH", raising=False)


def test_default_user_config_path_and_environment_override(tmp_path: Path) -> None:
    assert resolve_user_config_path(environ={}, home=tmp_path) == (
        tmp_path / ".telegram-codex" / "config.env"
    )
    override = tmp_path / "custom" / "telegram.env"
    assert resolve_user_config_path(
        environ={"TELEGRAM_CODEX_CONFIG_FILE": str(override)}, home=tmp_path
    ) == override


def test_user_config_override_must_be_absolute() -> None:
    with pytest.raises(ConfigurationError, match="must be an absolute path"):
        resolve_user_config_path(
            environ={"TELEGRAM_CODEX_CONFIG_FILE": "relative/config.env"}
        )


def test_from_env_loads_private_user_config_and_explicit_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(
        config_path,
        SetupCredentials(123456, "0123456789abcdef0123456789abcdef", "+15551234567"),
    )

    settings = Settings.from_env(
        environ={
            "TELEGRAM_CODEX_CONFIG_FILE": str(config_path),
            "TELEGRAM_API_ID": "654321",
        }
    )

    assert settings.api_id == 654321
    assert settings.api_hash == "0123456789abcdef0123456789abcdef"
    assert settings.phone == "+15551234567"
    assert settings.allow_writes is False


def test_from_env_uses_default_user_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "telegram_codex.config.Path.home", classmethod(lambda cls: tmp_path)
    )
    config_path = tmp_path / ".telegram-codex" / "config.env"
    write_setup_config(
        config_path,
        SetupCredentials(123456, "0123456789abcdef0123456789abcdef", "+15551234567"),
    )

    settings = Settings.from_env(environ={})

    assert settings.api_id == 123456
    assert settings.phone == "+15551234567"
    assert settings.session_path == config_path.parent / "data" / "codex"


def test_project_dotenv_remains_compatible_as_legacy_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    dotenv_path = tmp_path / ".env"
    session_path = tmp_path / "private" / "codex"
    audit_path = tmp_path / "private" / "audit.jsonl"
    dotenv_path.write_text(
        "\n".join(
            (
                "TELEGRAM_API_ID=777000",
                "TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef",
                "TELEGRAM_PHONE=+15551234567",
                f"TELEGRAM_SESSION_PATH={session_path}",
                f"TELEGRAM_AUDIT_LOG_PATH={audit_path}",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("telegram_codex.config.find_dotenv", lambda: str(dotenv_path))

    settings = Settings.from_env(environ={})

    assert settings.api_id == 777000
    assert settings.api_hash == "0123456789abcdef0123456789abcdef"


def test_private_user_config_is_not_overridden_by_workspace_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(
        config_path,
        SetupCredentials(123456, "0123456789abcdef0123456789abcdef", "+15551234567"),
    )
    (tmp_path / ".env").write_text(
        "TELEGRAM_ALLOW_WRITES=true\n"
        "TELEGRAM_WRITE_CHAT_ALLOWLIST=777000\n"
        "TELEGRAM_AUDIT_LOG_PATH=off\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "telegram_codex.config.find_dotenv",
        lambda: pytest.fail("workspace .env must not be consulted when user config exists"),
    )

    settings = Settings.from_env(
        environ={"TELEGRAM_CODEX_CONFIG_FILE": str(config_path)}
    )

    assert settings.allow_writes is False
    assert settings.write_chat_allowlist is None
    assert settings.audit_log_path == config_path.parent / "data" / "audit.jsonl"


def test_python_dotenv_disabled_preserves_explicit_environment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "TELEGRAM_API_ID=999999\nTELEGRAM_API_HASH=from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "telegram_codex.config.find_dotenv",
        lambda: pytest.fail("disabled dotenv loading must not search for a file"),
    )
    session_path = tmp_path / "private" / "codex"

    settings = Settings.from_env(
        environ={
            "PYTHON_DOTENV_DISABLED": "true",
            "TELEGRAM_API_ID": "123456",
            "TELEGRAM_API_HASH": "explicit-hash",
            "TELEGRAM_SESSION_PATH": str(session_path),
            "TELEGRAM_AUDIT_LOG_PATH": "off",
        }
    )

    assert settings.api_id == 123456
    assert settings.api_hash == "explicit-hash"


def test_from_env_rejects_invalid_private_user_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    if os.name != "nt":
        os.chmod(private, 0o700)
    config_path = private / "config.env"
    config_path.write_text("TELEGRAM_API_ID='unterminated\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(config_path, 0o600)

    with pytest.raises(ConfigurationError, match="invalid dotenv syntax"):
        Settings.from_env(
            environ={"TELEGRAM_CODEX_CONFIG_FILE": str(config_path)}
        )


def test_from_env_rejects_missing_explicit_user_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="does not exist"):
        Settings.from_env(
            environ={
                "TELEGRAM_CODEX_CONFIG_FILE": str(tmp_path / "missing.env"),
                "TELEGRAM_API_ID": "1",
                "TELEGRAM_API_HASH": "hash",
            }
        )


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
