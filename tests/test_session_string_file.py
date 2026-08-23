from __future__ import annotations

from telegram_codex.config import Settings


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


def test_direct_secret_takes_precedence_over_session_file(tmp_path, monkeypatch) -> None:
    _base(monkeypatch)
    path = tmp_path / "session.string"
    path.write_text("from-file", encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(path))
    monkeypatch.setenv("TELEGRAM_SESSION_STRING", "from-env")

    settings = Settings.from_env()

    assert settings.session_string == "from-env"
