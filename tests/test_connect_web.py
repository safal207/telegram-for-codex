from __future__ import annotations

import os
import stat

from starlette.testclient import TestClient

from telegram_codex import connect_web, remote_server


def test_persist_session_string_is_private_and_not_returned(tmp_path, monkeypatch) -> None:
    target = tmp_path / "private" / "session.string"
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(target))
    monkeypatch.delenv("TELEGRAM_SESSION_STRING", raising=False)

    result = connect_web._persist_session_string("super-secret-session")

    assert result == target
    assert target.read_text(encoding="utf-8") == "super-secret-session"
    assert os.environ["TELEGRAM_SESSION_STRING"] == "super-secret-session"
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "super-secret-session" not in connect_web._CONNECT_HTML


def test_connect_page_is_mobile_visible_but_start_requires_private_key(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", "correct-key")
    app = remote_server.mcp.streamable_http_app()

    with TestClient(app, base_url="http://localhost") as client:
        page = client.get("/connect", headers={"host": "localhost"})
        assert page.status_code == 200
        assert "Connect Telegram" in page.text
        assert "viewport" in page.text

        denied = client.post(
            "/connect/start",
            headers={"host": "localhost", "x-telegram-connect-token": "wrong-key"},
            json={"phone": "+79991234567"},
        )
        assert denied.status_code == 401
        assert denied.json() == {"ok": False, "error": "Invalid connect key."}
