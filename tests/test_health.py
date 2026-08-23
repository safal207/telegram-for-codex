from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from telegram_codex.health import install_health_routes


def test_healthz_is_public_content_free_and_non_cacheable() -> None:
    mcp = FastMCP("health-test")
    install_health_routes(mcp)

    with TestClient(mcp.streamable_http_app(), base_url="http://localhost") as client:
        response = client.get("/healthz", headers={"host": "localhost"})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "telegram-for-codex",
        "mode": "personal",
    }
    assert response.headers["cache-control"] == "no-store"
    body = response.text.lower()
    for forbidden in ("phone", "session", "token", "chat", "username", "secret"):
        assert forbidden not in body
