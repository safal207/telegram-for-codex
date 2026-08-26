from __future__ import annotations

import asyncio
import json
import os
import stat
import time
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from telegram_codex import connect_web


VALID_CONNECT_TOKEN = "7f9C2a4D6e8F0b1A3c5E7g9H2j4K6m8N"


def _test_app():
    mcp = FastMCP("connect-test")
    connect_web.install_connect_routes(mcp)
    return mcp.streamable_http_app()


def test_persist_session_string_is_private_and_not_returned(tmp_path, monkeypatch) -> None:
    target = tmp_path / "private" / "session.string"
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(target))
    monkeypatch.delenv("TELEGRAM_SESSION_STRING", raising=False)

    result = connect_web._persist_session_string("super-secret-session")

    assert result == target
    assert target.read_text(encoding="utf-8") == "super-secret-session"
    assert os.environ["TELEGRAM_SESSION_STRING"] == "super-secret-session"
    if os.name != "nt":
        assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert "super-secret-session" not in connect_web._CONNECT_HTML


def test_persist_session_string_removes_temporary_file_after_write_failure(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "private" / "session.string"
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(target))

    def failed_write(*args, **kwargs) -> int:
        raise OSError("simulated write failure")

    monkeypatch.setattr(connect_web.os, "write", failed_write)

    with pytest.raises(OSError, match="simulated write failure"):
        connect_web._persist_session_string("super-secret-session")

    assert not target.exists()
    assert list(target.parent.glob(".*.tmp")) == []


def test_authorized_rejects_non_ascii_header_without_error(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", VALID_CONNECT_TOKEN)
    request = SimpleNamespace(headers={"x-telegram-connect-token": "пароль"})

    assert connect_web._authorized(request) is False


def test_connect_page_is_mobile_visible_but_start_requires_private_key(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", VALID_CONNECT_TOKEN)

    with TestClient(_test_app(), base_url="http://localhost") as client:
        page = client.get("/connect", headers={"host": "localhost"})
        assert page.status_code == 200
        assert "Connect Telegram" in page.text
        assert "viewport" in page.text
        assert page.headers["cache-control"] == "no-store"
        assert page.headers["referrer-policy"] == "no-referrer"
        assert page.headers["x-content-type-options"] == "nosniff"
        assert page.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]

        denied = client.post(
            "/connect/start",
            headers={"host": "localhost", "x-telegram-connect-token": "wrong-key"},
            json={"phone": "+79991234567"},
        )
        assert denied.status_code == 401
        assert denied.json() == {"ok": False, "error": "Invalid connect key."}
        assert denied.headers["cache-control"] == "no-store"


def test_all_connect_actions_fail_closed_when_token_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_CONNECT_TOKEN", raising=False)

    with TestClient(_test_app(), base_url="http://localhost") as client:
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
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", VALID_CONNECT_TOKEN)

    with TestClient(_test_app(), base_url="http://localhost") as client:
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


@pytest.mark.parametrize(
    "configured_token",
    [
        "too-short",
        "x" * 32,
        "ab" * 16,
        "replace-me-with-a-random-secret-token-now",
        "YOUR_TELEGRAM_CONNECT_TOKEN_GOES_HERE",
    ],
)
def test_connect_token_rejects_short_and_obvious_placeholders(
    configured_token: str, monkeypatch
) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", configured_token)

    with TestClient(_test_app(), base_url="http://localhost") as client:
        response = client.post(
            "/connect/start",
            headers={
                "host": "localhost",
                "x-telegram-connect-token": configured_token,
            },
            json={"phone": "+79991234567"},
        )

    assert response.status_code == 401
    assert response.json() == {"ok": False, "error": "Invalid connect key."}


def test_connect_start_disconnects_client_when_code_request_fails(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", VALID_CONNECT_TOKEN)

    class FakeClient:
        instance = None

        def __init__(self, *args, **kwargs) -> None:
            self.disconnected = False
            FakeClient.instance = self

        async def connect(self) -> None:
            return None

        async def send_code_request(self, phone: str):
            raise RuntimeError("Telegram unavailable")

        async def disconnect(self) -> None:
            self.disconnected = True

    monkeypatch.setattr(connect_web, "TelegramClient", FakeClient)
    monkeypatch.setattr(
        connect_web.Settings,
        "from_env",
        staticmethod(lambda: SimpleNamespace(api_id=1, api_hash="hash")),
    )

    with TestClient(_test_app(), base_url="http://localhost") as client:
        response = client.post(
            "/connect/start",
            headers={
                "host": "localhost",
                "x-telegram-connect-token": VALID_CONNECT_TOKEN,
            },
            json={"phone": "+79991234567"},
        )

    assert response.status_code == 400
    assert FakeClient.instance is not None
    assert FakeClient.instance.disconnected is True


def test_finish_login_never_returns_session_string(monkeypatch) -> None:
    secret = "super-secret-session"
    persisted: list[str] = []

    class FakeSession:
        def save(self) -> str:
            return secret

    class FakeClient:
        session = FakeSession()

        def __init__(self) -> None:
            self.disconnected = False

        async def get_me(self):
            return SimpleNamespace(id=123, username="tester", first_name="Test")

        async def disconnect(self) -> None:
            self.disconnected = True

    monkeypatch.setattr(connect_web, "_persist_session_string", lambda value: persisted.append(value))
    flow_id = "test-flow"
    fake_client = FakeClient()
    flow = connect_web.AuthFlow(
        client=fake_client,
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
    assert response.headers["cache-control"] == "no-store"
    assert fake_client.disconnected is True
    assert flow_id not in connect_web._flows


def test_finish_login_serialization_failure_discards_flow() -> None:
    class EmptySession:
        def save(self) -> str:
            return ""

    class FakeClient:
        session = EmptySession()

        def __init__(self) -> None:
            self.disconnected = False

        async def get_me(self):
            return SimpleNamespace(id=123)

        async def disconnect(self) -> None:
            self.disconnected = True

    flow_id = "serialization-failure"
    fake_client = FakeClient()
    flow = connect_web.AuthFlow(
        client=fake_client,
        phone="+79991234567",
        phone_code_hash="hash",
        created_at=time.monotonic(),
    )
    connect_web._flows[flow_id] = flow

    response = asyncio.run(connect_web._finish_login(flow_id, flow, None))

    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert fake_client.disconnected is True
    assert flow_id not in connect_web._flows


@pytest.mark.parametrize(
    ("path", "credentials"),
    [
        ("/connect/code", {"code": "12345"}),
        ("/connect/password", {"password": "secret"}),
    ],
)
def test_terminal_code_and_password_errors_discard_flow(
    path: str, credentials: dict[str, str], monkeypatch
) -> None:
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", VALID_CONNECT_TOKEN)

    class BrokenClient:
        def __init__(self) -> None:
            self.disconnected = False

        async def sign_in(self, **kwargs) -> None:
            raise RuntimeError("terminal Telegram failure")

        async def disconnect(self) -> None:
            self.disconnected = True

    flow_id = f"terminal-{path.rsplit('/', 1)[-1]}"
    client_instance = BrokenClient()
    connect_web._flows[flow_id] = connect_web.AuthFlow(
        client=client_instance,
        phone="+79991234567",
        phone_code_hash="hash",
        created_at=time.monotonic(),
    )

    with TestClient(_test_app(), base_url="http://localhost") as client:
        response = client.post(
            path,
            headers={
                "host": "localhost",
                "x-telegram-connect-token": VALID_CONNECT_TOKEN,
            },
            json={"flow_id": flow_id, **credentials},
        )

    assert response.status_code == 400
    assert flow_id not in connect_web._flows
    assert client_instance.disconnected is True


def test_prune_flows_disconnects_only_expired_clients() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.disconnected = False

        async def disconnect(self) -> None:
            self.disconnected = True

    assert not connect_web._flows
    expired_client = FakeClient()
    active_client = FakeClient()
    connect_web._flows.update(
        {
            "expired": connect_web.AuthFlow(
                client=expired_client,
                phone="+79990000001",
                phone_code_hash="expired-hash",
                created_at=time.monotonic() - connect_web._FLOW_TTL_SECONDS - 1,
            ),
            "active": connect_web.AuthFlow(
                client=active_client,
                phone="+79990000002",
                phone_code_hash="active-hash",
                created_at=time.monotonic(),
            ),
        }
    )

    asyncio.run(connect_web._prune_flows())

    assert expired_client.disconnected is True
    assert "expired" not in connect_web._flows
    assert active_client.disconnected is False
    assert "active" in connect_web._flows

    asyncio.run(connect_web._discard_flow("active"))
    assert active_client.disconnected is True
    assert not connect_web._flows


def test_prune_flow_disconnect_failure_does_not_break_cleanup() -> None:
    class BrokenDisconnectClient:
        async def disconnect(self) -> None:
            raise RuntimeError("disconnect failed")

    connect_web._flows["expired-broken-disconnect"] = connect_web.AuthFlow(
        client=BrokenDisconnectClient(),
        phone="+79990000003",
        phone_code_hash="hash",
        created_at=time.monotonic() - connect_web._FLOW_TTL_SECONDS - 1,
    )

    asyncio.run(connect_web._prune_flows())

    assert "expired-broken-disconnect" not in connect_web._flows
