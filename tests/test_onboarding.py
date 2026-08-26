from __future__ import annotations

import os
import socket
import sqlite3
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path

import pytest

from telegram_codex.config import ConfigurationError, _parse_user_config
from telegram_codex.onboarding import (
    SetupCredentials,
    doctor_main,
    run_doctor,
    setup_main,
    write_setup_config,
)

API_HASH = "0123456789abcdef0123456789abcdef"
OTHER_API_HASH = "fedcba9876543210fedcba9876543210"


def _credentials(api_hash: str = API_HASH) -> SetupCredentials:
    return SetupCredentials(api_id=123456, api_hash=api_hash, phone="+15551234567")


def _create_authorized_session(
    config_path: Path, auth_key: object = b"a" * 256
) -> Path:
    values = _parse_user_config(config_path)
    session_file = Path(f"{values['TELEGRAM_SESSION_PATH']}.session")
    connection = sqlite3.connect(session_file)
    try:
        connection.execute(
            "CREATE TABLE sessions (dc_id INTEGER PRIMARY KEY, server_address TEXT, "
            "port INTEGER, auth_key BLOB, takeout_id INTEGER)"
        )
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            (2, "149.154.167.50", 443, auth_key, None),
        )
        connection.commit()
    finally:
        connection.close()
    return session_file


def _which(command: str) -> str | None:
    return {
        "telegram-codex": "C:/tools/telegram-codex.exe",
        "codex": "C:/tools/codex.exe",
    }.get(command)


def test_interactive_setup_creates_private_safe_config_without_leaking_secret(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "private" / "config.env"
    answers = iter(["123456", "+15551234567"])
    secret_prompts: list[str] = []
    stdout = StringIO()
    stderr = StringIO()

    result = setup_main(
        ["--config", str(config_path)],
        environ={},
        input_fn=lambda prompt: next(answers),
        secret_input_fn=lambda prompt: secret_prompts.append(prompt) or API_HASH,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert len(secret_prompts) == 1
    assert API_HASH not in stdout.getvalue()
    assert API_HASH not in stderr.getvalue()
    assert "Codex configuration was not changed" in stdout.getvalue()
    assert "telegram-codex-auth" in stdout.getvalue()
    values = _parse_user_config(config_path)
    assert values["TELEGRAM_API_ID"] == "123456"
    assert values["TELEGRAM_API_HASH"] == API_HASH
    assert values["TELEGRAM_PHONE"] == "+15551234567"
    assert values["TELEGRAM_ALLOW_WRITES"] == "false"
    assert values["TELEGRAM_AUDIT_LOG_PATH"].endswith("audit.jsonl")
    assert (config_path.parent / "data").is_dir()
    if os.name != "nt":
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE((config_path.parent / "data").stat().st_mode) == 0o700


def test_noninteractive_setup_reads_secrets_only_from_environment(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "config.env"
    stdout = StringIO()
    stderr = StringIO()
    result = setup_main(
        ["--config", str(config_path), "--non-interactive"],
        environ={
            "TELEGRAM_API_ID": "123456",
            "TELEGRAM_API_HASH": API_HASH,
            "TELEGRAM_PHONE": "+15551234567",
        },
        input_fn=lambda prompt: pytest.fail("interactive input must not be used"),
        secret_input_fn=lambda prompt: pytest.fail("secret prompt must not be used"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert API_HASH not in stdout.getvalue()
    assert API_HASH not in stderr.getvalue()


def test_setup_fails_closed_when_environment_enables_writes(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "config.env"
    stderr = StringIO()

    result = setup_main(
        ["--config", str(config_path), "--non-interactive"],
        environ={
            "TELEGRAM_API_ID": "123456",
            "TELEGRAM_API_HASH": API_HASH,
            "TELEGRAM_PHONE": "+15551234567",
            "TELEGRAM_ALLOW_WRITES": "true",
            "TELEGRAM_WRITE_CHAT_ALLOWLIST": "777000",
        },
        stderr=stderr,
    )

    assert result == 1
    assert "TELEGRAM_ALLOW_WRITES is enabled" in stderr.getvalue()
    assert API_HASH not in stderr.getvalue()
    assert not config_path.exists()


def test_noninteractive_setup_reports_missing_names_without_secret(tmp_path: Path) -> None:
    stderr = StringIO()
    result = setup_main(
        ["--config", str(tmp_path / "config.env"), "--non-interactive"],
        environ={"TELEGRAM_API_HASH": API_HASH},
        stderr=stderr,
    )

    assert result == 1
    assert "TELEGRAM_API_ID" in stderr.getvalue()
    assert "TELEGRAM_PHONE" in stderr.getvalue()
    assert API_HASH not in stderr.getvalue()


def test_interactive_setup_fails_closed_when_secret_input_cannot_be_hidden(
    tmp_path: Path,
) -> None:
    class NonInteractiveInput(StringIO):
        def isatty(self) -> bool:
            return False

    stderr = StringIO()
    result = setup_main(
        ["--config", str(tmp_path / "config.env")],
        environ={
            "TELEGRAM_API_ID": "123456",
            "TELEGRAM_PHONE": "+15551234567",
        },
        stdin=NonInteractiveInput(API_HASH),
        stderr=stderr,
    )

    assert result == 1
    assert "secure interactive terminal" in stderr.getvalue()
    assert "--non-interactive" in stderr.getvalue()
    assert API_HASH not in stderr.getvalue()
    assert not (tmp_path / "config.env").exists()


@pytest.mark.parametrize(
    ("api_id", "api_hash", "phone", "message"),
    [
        ("zero", API_HASH, "+15551234567", "positive integer"),
        ("123456", "not-a-secret", "+15551234567", "32 hexadecimal"),
        ("123456", API_HASH, "555123", "international format"),
    ],
)
def test_setup_validates_credentials_without_echoing_values(
    tmp_path: Path, api_id: str, api_hash: str, phone: str, message: str
) -> None:
    stderr = StringIO()
    result = setup_main(
        ["--config", str(tmp_path / "config.env"), "--non-interactive"],
        environ={
            "TELEGRAM_API_ID": api_id,
            "TELEGRAM_API_HASH": api_hash,
            "TELEGRAM_PHONE": phone,
        },
        stderr=stderr,
    )

    assert result == 1
    assert message in stderr.getvalue()
    assert api_hash not in stderr.getvalue()


def test_setup_refuses_existing_config_unless_force_is_explicit(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())

    with pytest.raises(ConfigurationError, match="--force"):
        write_setup_config(config_path, _credentials(OTHER_API_HASH))

    assert _parse_user_config(config_path)["TELEGRAM_API_HASH"] == API_HASH
    write_setup_config(config_path, _credentials(OTHER_API_HASH), overwrite=True)
    assert _parse_user_config(config_path)["TELEGRAM_API_HASH"] == OTHER_API_HASH


def test_parallel_setup_without_force_never_clobbers_existing_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "private" / "config.env"
    barrier = threading.Barrier(2)
    real_link = os.link

    def synchronized_link(source: Path, target: Path, **kwargs) -> None:
        barrier.wait(timeout=5)
        real_link(source, target, **kwargs)

    monkeypatch.setattr("telegram_codex.onboarding.os.link", synchronized_link)
    credentials = (_credentials(API_HASH), _credentials(OTHER_API_HASH))
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(write_setup_config, config_path, candidate)
            for candidate in credentials
        ]
    successes = [future for future in futures if future.exception() is None]
    failures = [future.exception() for future in futures if future.exception() is not None]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], ConfigurationError)
    assert "--force" in str(failures[0])
    assert _parse_user_config(config_path)["TELEGRAM_API_HASH"] in {
        API_HASH,
        OTHER_API_HASH,
    }
    assert not list(config_path.parent.glob(".config.env.*.tmp"))


def test_atomic_replace_failure_preserves_existing_config_and_cleans_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("telegram_codex.onboarding.os.replace", fail_replace)
    with pytest.raises(ConfigurationError, match="Unable to write private config"):
        write_setup_config(config_path, _credentials(OTHER_API_HASH), overwrite=True)

    assert _parse_user_config(config_path)["TELEGRAM_API_HASH"] == API_HASH
    assert not list(config_path.parent.glob(".config.env.*.tmp"))


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links are unavailable")
def test_setup_rejects_hardlinked_config(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    if os.name != "nt":
        os.chmod(private, 0o700)
    original = private / "original.env"
    original.write_text("do-not-replace", encoding="utf-8")
    config_path = private / "config.env"
    os.link(original, config_path)

    with pytest.raises(ConfigurationError, match="hard links"):
        write_setup_config(config_path, _credentials(), overwrite=True)

    assert original.read_text(encoding="utf-8") == "do-not-replace"


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics are unavailable on Windows")
def test_setup_rejects_symlink_config(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    os.chmod(private, 0o700)
    target = tmp_path / "outside"
    target.write_text("do-not-replace", encoding="utf-8")
    config_path = private / "config.env"
    config_path.symlink_to(target)

    with pytest.raises(ConfigurationError, match="non-symlink"):
        write_setup_config(config_path, _credentials(), overwrite=True)

    assert target.read_text(encoding="utf-8") == "do-not-replace"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions are unavailable on Windows")
def test_setup_rejects_preexisting_shared_config_directory(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o755)
    os.chmod(private, 0o755)

    with pytest.raises(ConfigurationError, match="mode 0700"):
        write_setup_config(private / "config.env", _credentials())


def test_config_quoting_round_trips_paths_with_spaces_and_apostrophes(tmp_path: Path) -> None:
    config_path = tmp_path / "private folder" / "config.env"
    data_directory = config_path.parent / "data's folder"
    write_setup_config(config_path, _credentials(), data_directory=data_directory)

    values = _parse_user_config(config_path)
    assert values["TELEGRAM_SESSION_PATH"] == str(data_directory / "codex")
    assert values["TELEGRAM_AUDIT_LOG_PATH"] == str(data_directory / "audit.jsonl")


def test_relative_config_generates_absolute_runtime_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    stdout = StringIO()
    result = setup_main(
        ["--config", "relative/config.env", "--non-interactive"],
        environ={
            "TELEGRAM_API_ID": "123456",
            "TELEGRAM_API_HASH": API_HASH,
            "TELEGRAM_PHONE": "+15551234567",
        },
        stdout=stdout,
    )

    config_path = tmp_path / "relative" / "config.env"
    assert result == 0
    assert str(config_path) in stdout.getvalue()
    values = _parse_user_config(config_path)
    assert Path(values["TELEGRAM_SESSION_PATH"]).is_absolute()
    assert Path(values["TELEGRAM_AUDIT_LOG_PATH"]).is_absolute()


def test_doctor_passes_offline_with_private_config_session_and_launchers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())
    _create_authorized_session(config_path)

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: pytest.fail("doctor must not access the network"),
    )
    checks = run_doctor(
        config_path=config_path,
        environ={},
        which_fn=_which,
        version_info=(3, 12, 2),
    )

    assert checks
    assert {check.status for check in checks} == {"PASS"}
    assert any(check.name == "Telegram session" for check in checks)


def test_doctor_supports_legacy_dotenv_when_default_user_config_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_dotenv = tmp_path / "source" / ".env"
    write_setup_config(legacy_dotenv, _credentials())
    _create_authorized_session(legacy_dotenv)
    monkeypatch.setattr(
        "telegram_codex.config.find_dotenv", lambda: str(legacy_dotenv)
    )

    checks = run_doctor(
        config_path=tmp_path / ".telegram-codex" / "config.env",
        environ={},
        which_fn=_which,
        version_info=(3, 12, 2),
        allow_legacy_fallback=True,
    )

    config = next(check for check in checks if check.name == "Config")
    assert config.status == "WARN"
    assert not any(check.status == "FAIL" for check in checks)


def test_doctor_main_uses_legacy_fallback_only_without_explicit_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_dotenv = tmp_path / "source" / ".env"
    write_setup_config(legacy_dotenv, _credentials())
    _create_authorized_session(legacy_dotenv)
    missing_default = tmp_path / ".telegram-codex" / "config.env"
    monkeypatch.setattr(
        "telegram_codex.onboarding.resolve_user_config_path",
        lambda **kwargs: missing_default,
    )
    monkeypatch.setattr(
        "telegram_codex.config.find_dotenv", lambda: str(legacy_dotenv)
    )
    stdout = StringIO()

    result = doctor_main(
        [],
        environ={},
        which_fn=_which,
        version_info=(3, 12, 2),
        stdout=stdout,
    )

    assert result == 0
    assert "WARN Config" in stdout.getvalue()
    assert "PASS Telegram session" in stdout.getvalue()


def test_doctor_main_returns_nonzero_for_blockers_without_leaking_secret(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "missing" / "config.env"
    stdout = StringIO()

    result = doctor_main(
        ["--config", str(config_path)],
        environ={"TELEGRAM_API_HASH": API_HASH},
        which_fn=lambda command: None,
        version_info=(3, 10, 14),
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert result == 1
    assert "FAIL Python" in output
    assert "FAIL Launcher" in output
    assert "FAIL Config" in output
    assert "FAIL Codex CLI" in output
    assert API_HASH not in output


def test_doctor_fails_when_session_is_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())

    checks = run_doctor(
        config_path=config_path,
        environ={},
        which_fn=_which,
        version_info=(3, 11, 0),
    )

    session = next(check for check in checks if check.name == "Telegram session")
    assert session.status == "FAIL"
    assert "telegram-codex-auth" in session.detail


def test_doctor_fails_closed_for_corrupt_session(tmp_path: Path) -> None:
    config_path = tmp_path / "private" / "config.env"
    data_directory = write_setup_config(config_path, _credentials())
    (data_directory / "codex.session").write_bytes(b"not sqlite")

    checks = run_doctor(
        config_path=config_path,
        environ={},
        which_fn=_which,
        version_info=(3, 11, 0),
    )

    session = next(check for check in checks if check.name == "Telegram session")
    assert session.status == "FAIL"
    assert "invalid" in session.detail


@pytest.mark.parametrize("malformed", ["1notvalid", "1a"])
def test_doctor_fails_closed_for_malformed_string_session_without_traceback(
    tmp_path: Path, malformed: str
) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())

    checks = run_doctor(
        config_path=config_path,
        environ={"TELEGRAM_SESSION_STRING": malformed},
        which_fn=_which,
        version_info=(3, 12, 0),
    )

    session = next(check for check in checks if check.name == "Telegram session")
    assert session.status == "FAIL"
    assert session.detail == "Session string is invalid"
    assert malformed not in session.detail


@pytest.mark.parametrize("auth_key", [123, b"\0" * 256, "x" * 256])
def test_doctor_rejects_wrong_type_or_empty_file_session_auth_key(
    tmp_path: Path, auth_key: object
) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())
    _create_authorized_session(config_path, auth_key)

    checks = run_doctor(
        config_path=config_path,
        environ={},
        which_fn=_which,
        version_info=(3, 12, 0),
    )

    session = next(check for check in checks if check.name == "Telegram session")
    assert session.status == "FAIL"
    assert "valid authorization key" in session.detail


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("TELEGRAM_API_ID", "0", "positive integer"),
        ("TELEGRAM_API_HASH", "not-valid", "32 hexadecimal"),
        ("TELEGRAM_PHONE", "secret-phone", "international format"),
    ],
)
def test_doctor_rejects_invalid_effective_credentials(
    tmp_path: Path, key: str, value: str, message: str
) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())

    checks = run_doctor(
        config_path=config_path,
        environ={key: value},
        which_fn=_which,
        version_info=(3, 12, 0),
    )

    settings = next(check for check in checks if check.name == "Settings")
    assert settings.status == "FAIL"
    assert message in settings.detail
    assert value not in settings.detail


def test_doctor_emits_warning_without_failing_for_explicit_write_mode(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "private" / "config.env"
    write_setup_config(config_path, _credentials())
    _create_authorized_session(config_path)
    content = config_path.read_text(encoding="utf-8")
    content = content.replace("TELEGRAM_ALLOW_WRITES='false'", "TELEGRAM_ALLOW_WRITES='true'")
    content += "TELEGRAM_WRITE_CHAT_ALLOWLIST='777000'\n"
    config_path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        os.chmod(config_path, 0o600)

    stdout = StringIO()
    result = doctor_main(
        ["--config", str(config_path)],
        environ={},
        which_fn=_which,
        version_info=(3, 12, 0),
        stdout=stdout,
    )

    assert result == 0
    assert "WARN Settings" in stdout.getvalue()
    assert "writes are explicitly enabled" in stdout.getvalue()
