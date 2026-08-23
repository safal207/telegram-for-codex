from __future__ import annotations

import asyncio

import httpx
import pytest
from starlette.testclient import TestClient

from telegram_codex import remote_server
from telegram_codex.config import ConfigurationError
from telegram_codex.personal_auth import (
    IntrospectionTokenVerifier,
    StaticTokenVerifier,
    load_personal_auth_from_env,
)


def test_remote_auth_fails_closed_without_configuration(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "oauth")
    for name in (
        "TELEGRAM_MCP_PUBLIC_URL",
        "TELEGRAM_OAUTH_ISSUER_URL",
        "TELEGRAM_OAUTH_INTROSPECTION_URL",
        "TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID",
        "TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigurationError):
        load_personal_auth_from_env()


def test_static_verifier_accepts_only_exact_high_entropy_token() -> None:
    verifier = StaticTokenVerifier("a" * 40, ["telegram:personal"])

    accepted = asyncio.run(verifier.verify_token("a" * 40))
    denied = asyncio.run(verifier.verify_token("b" * 40))

    assert accepted is not None
    assert accepted.subject == "personal-owner"
    assert accepted.scopes == ["telegram:personal"]
    assert denied is None


def test_static_token_rejects_short_secret() -> None:
    with pytest.raises(ConfigurationError, match="at least 32"):
        StaticTokenVerifier("short", ["telegram:personal"])


def test_remote_http_rejects_missing_bearer_and_publishes_resource_metadata(monkeypatch) -> None:
    token = "t" * 40
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://localhost/mcp")
    app = remote_server.build_remote_mcp().streamable_http_app()

    with TestClient(app, base_url="http://localhost") as client:
        denied = client.get("/mcp", headers={"host": "localhost"})
        assert denied.status_code == 401
        assert "Bearer" in denied.headers.get("www-authenticate", "")

        metadata = client.get(
            "/.well-known/oauth-protected-resource/mcp",
            headers={"host": "localhost"},
        )
        assert metadata.status_code == 200
        body = metadata.json()
        assert body["resource"] == "http://localhost/mcp"
        assert body["scopes_supported"] == ["telegram:personal"]

        authorized = client.get(
            "/mcp",
            headers={"host": "localhost", "authorization": f"Bearer {token}"},
        )
        assert authorized.status_code != 401


def test_introspection_verifier_maps_active_token_and_rejects_wrong_audience(monkeypatch) -> None:
    responses = [
        httpx.Response(
            200,
            json={
                "active": True,
                "client_id": "chatgpt-client",
                "sub": "user-123",
                "scope": "telegram:personal",
                "iss": "https://auth.example.com",
                "aud": ["https://telegram.example.com/mcp"],
                "exp": 2_000_000_000,
            },
        ),
        httpx.Response(
            200,
            json={
                "active": True,
                "client_id": "chatgpt-client",
                "scope": "telegram:personal",
                "iss": "https://auth.example.com",
                "aud": ["https://other.example.com/mcp"],
            },
        ),
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args, **kwargs):
            return responses.pop(0)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    verifier = IntrospectionTokenVerifier(
        introspection_url="https://auth.example.com/introspect",
        client_id="resource-server",
        client_secret="secret",
        issuer_url="https://auth.example.com",
        resource_url="https://telegram.example.com/mcp",
    )

    accepted = asyncio.run(verifier.verify_token("good"))
    denied = asyncio.run(verifier.verify_token("wrong-aud"))

    assert accepted is not None
    assert accepted.client_id == "chatgpt-client"
    assert accepted.subject == "user-123"
    assert accepted.resource == "https://telegram.example.com/mcp"
    assert denied is None
