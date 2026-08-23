import pytest

from pathlib import Path

from telegram_codex.config import ConfigurationError, Settings, _as_bool, _parse_allowlist


def test_as_bool_defaults_false() -> None:
    assert _as_bool(None) is False


def test_as_bool_true_values() -> None:
    for value in ("1", "true", "TRUE", "yes", "on"):
        assert _as_bool(value) is True


def test_as_bool_false_values() -> None:
    for value in ("0", "false", "no", "off", "anything"):
        assert _as_bool(value) is False


def test_parse_allowlist_empty_means_all_chats() -> None:
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
    monkeypatch.delenv("TELEGRAM_WRITE_CHAT_ALLOWLIST", raising=False)
    monkeypatch.delenv("TELEGRAM_AUDIT_LOG_PATH", raising=False)


def test_from_env_defaults_allow_all_chats_and_audit_on(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _set_base_env(monkeypatch)

    settings = Settings.from_env()

    assert settings.session_mode == "file"
    assert settings.session_string is None
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
