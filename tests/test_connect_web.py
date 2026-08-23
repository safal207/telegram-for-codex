from __future__ import annotations

import asyncio
import json
import os
import stat
import time
from types import SimpleNamespace

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


def test_all_connect_actions_fail_closed_when_token_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_CONNECT_TOKEN", raising=False)
    app = remote_server.mcp.streamable_http_app()

    with TestClient(app, base_url="http://localhost") as client:
        cases = (
            ("/connect/start", {"phone": "+79991234567"}),
            ("/connect/code", {"flow_id": "x", "code": "12345"}),
            ("/connect/password", {"flow_id": "x", "password": "secret"}),
        )
        for path, payload in cases:
            response = client.post(
                path,
                headers={"host": "localhost", "x-telegram-connect-token": "anything"},
                json=payload,
            )
            assert response.status_code == 401
            assert response.json() == {"ok": False, "error": "Invalid connect key."}


def test_code_and_password_endpoints_reject_wrong_private_key(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", "correct-key")
    app = remote_server.mcp.streamable_http_app()

    with TestClient(app, base_url="http://localhost") as client:
        for path, payload in (
            ("/connect/code", {"flow_id": "x", "code": "12345"}),
            ("/connect/password", {"flow_id": "x", "password": "secret"}),
        ):
            response = client.post(
                path,
                headers={"host": "localhost", "x-telegram-connect-token": "wrong-key"},
                json=payload,
            )
            assert response.status_code == 401
            assert response.json() == {"ok": False, "error": "Invalid connect key."}


def test_finish_login_never_returns_session_string(monkeypatch) -> None:
    secret = "super-secret-session"
    persisted: list[str] = []

    class FakeSession:
        def save(self) -> str:
            return secret

    class FakeClient:
        session = FakeSession()

        async def get_me(self):
            return SimpleNamespace(id=123, username="tester", first_name="Test")

        async def disconnect(self) -> None:
            return None

    monkeypatch.setattr(connect_web, "_persist_session_string", lambda value: persisted.append(value))
    flow_id = "test-flow"
    flow = connect_web.AuthFlow(
        client=FakeClient(),
        phone="+79991234567",
        phone_code_hash="hash",
        created_at=time.monotonic(),
    )
    connect_web._flows[flow_id] = flow

    response = asyncio.run(connect_web._finish_login(flow_id, flow, None))
    payload = json.loads(response.body)

    assert persisted == [secret]
    assert payload == {
        "ok": True,
        "status": "connected",
        "user": {"id": 123, "username": "tester", "first_name": "Test"},
    }
    assert secret not in response.body.decode("utf-8")
