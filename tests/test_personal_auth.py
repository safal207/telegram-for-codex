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

_MISSING = object()
_STATIC_TOKEN = "C0d3xMcp_7Gv9Q2rL5sN8wK4yF6hJ1bT3"
_OTHER_STATIC_TOKEN = "R9m2K7v4Q1x8D5c3N6s0HjWfYpLaZbEu"
_CONNECT_TOKEN = "TgCnx_4V7qP2mR9sL5dK8hJ1fN6wY3zB"


def test_remote_auth_fails_closed_without_configuration(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "oauth")
    for name in (
        "TELEGRAM_MCP_PUBLIC_URL",
        "TELEGRAM_OAUTH_ISSUER_URL",
        "TELEGRAM_OAUTH_INTROSPECTION_URL",
        "TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID",
        "TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET",
        "TELEGRAM_MCP_OWNER_SUBJECT",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigurationError):
        load_personal_auth_from_env()


def test_oauth_configuration_requires_owner_subject(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "https://telegram.example.com/mcp")
    monkeypatch.setenv("TELEGRAM_OAUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv(
        "TELEGRAM_OAUTH_INTROSPECTION_URL", "https://auth.example.com/introspect"
    )
    monkeypatch.setenv("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID", "resource-server")
    monkeypatch.setenv("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET", "secret")
    monkeypatch.delenv("TELEGRAM_MCP_OWNER_SUBJECT", raising=False)

    with pytest.raises(ConfigurationError, match="TELEGRAM_MCP_OWNER_SUBJECT"):
        load_personal_auth_from_env()


def test_static_verifier_accepts_only_exact_high_entropy_token() -> None:
    verifier = StaticTokenVerifier(_STATIC_TOKEN, ["telegram:personal"])

    accepted = asyncio.run(verifier.verify_token(_STATIC_TOKEN))
    denied = asyncio.run(verifier.verify_token(_OTHER_STATIC_TOKEN))

    assert accepted is not None
    assert accepted.subject == "personal-owner"
    assert accepted.scopes == ["telegram:personal"]
    assert denied is None


def test_static_token_rejects_short_secret() -> None:
    with pytest.raises(ConfigurationError, match="at least 32"):
        StaticTokenVerifier("short", ["telegram:personal"])


@pytest.mark.parametrize(
    "token",
    [
        "x" * 32,
        "ab" * 16,
        "replace-me-with-a-random-secret-token-now",
        "YOUR_TELEGRAM_CONNECT_TOKEN_GOES_HERE",
    ],
)
def test_static_token_rejects_placeholders_and_repeated_patterns(token: str) -> None:
    with pytest.raises(ConfigurationError, match="high-entropy secret"):
        StaticTokenVerifier(token, ["telegram:personal"])


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TELEGRAM_MCP_PUBLIC_URL", "http://telegram.example.com/mcp"),
        ("TELEGRAM_OAUTH_ISSUER_URL", "http://auth.example.com"),
        (
            "TELEGRAM_OAUTH_INTROSPECTION_URL",
            "https://user:password@auth.example.com/introspect",
        ),
        (
            "TELEGRAM_OAUTH_INTROSPECTION_URL",
            "https://auth.example.com/introspect#fragment",
        ),
    ],
)
def test_oauth_rejects_insecure_or_ambiguous_urls(monkeypatch, name, value) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "https://telegram.example.com/mcp")
    monkeypatch.setenv("TELEGRAM_OAUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv(
        "TELEGRAM_OAUTH_INTROSPECTION_URL", "https://auth.example.com/introspect"
    )
    monkeypatch.setenv("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID", "resource-server")
    monkeypatch.setenv("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_MCP_OWNER_SUBJECT", "user-123")
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match="HTTPS"):
        load_personal_auth_from_env()


@pytest.mark.parametrize(
    "public_url",
    [
        "https://telegram.example.com/other-resource",
        "https://telegram.example.com/mcp/",
        "https://telegram.example.com/mcp?tenant=owner",
    ],
)
def test_public_resource_url_must_be_exact_mcp_endpoint(
    public_url: str, monkeypatch
) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", public_url)
    monkeypatch.setenv("TELEGRAM_OAUTH_ISSUER_URL", "https://auth.example.com")
    monkeypatch.setenv(
        "TELEGRAM_OAUTH_INTROSPECTION_URL", "https://auth.example.com/introspect"
    )
    monkeypatch.setenv("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID", "resource-server")
    monkeypatch.setenv("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_MCP_OWNER_SUBJECT", "user-123")

    with pytest.raises(ConfigurationError, match="exact /mcp endpoint"):
        load_personal_auth_from_env()


def test_static_mode_rejects_non_loopback_http_public_url(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", _STATIC_TOKEN)
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://telegram.example.com/mcp")
    monkeypatch.delenv("TELEGRAM_CONNECT_TOKEN", raising=False)

    with pytest.raises(ConfigurationError, match="HTTP only for a loopback host"):
        load_personal_auth_from_env()


def test_static_and_connect_tokens_must_be_different(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", _STATIC_TOKEN)
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", _STATIC_TOKEN)
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://127.0.0.1:8000/mcp")

    with pytest.raises(ConfigurationError, match="must be different secrets"):
        load_personal_auth_from_env()


def test_static_mode_rejects_non_ascii_connect_token_as_configuration_error(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", _STATIC_TOKEN)
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", "пароль-должен-быть-случайным-секретом")
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://127.0.0.1:8000/mcp")

    with pytest.raises(ConfigurationError, match="high-entropy secret"):
        load_personal_auth_from_env()


def test_static_mode_accepts_distinct_connect_token_on_loopback(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", _STATIC_TOKEN)
    monkeypatch.setenv("TELEGRAM_CONNECT_TOKEN", _CONNECT_TOKEN)
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://localhost:8000/mcp")

    bundle = load_personal_auth_from_env()

    assert bundle.mode == "static"


def test_remote_http_rejects_missing_bearer_and_publishes_resource_metadata(monkeypatch) -> None:
    token = _STATIC_TOKEN
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", token)
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://localhost/mcp")
    monkeypatch.delenv("TELEGRAM_CONNECT_TOKEN", raising=False)
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
        assert authorized.status_code == 406
        assert "www-authenticate" not in authorized.headers
        assert authorized.json()["error"]["code"] == -32600


def _introspection_verifier(
    monkeypatch, *payloads: dict[str, object]
) -> IntrospectionTokenVerifier:
    responses = [httpx.Response(200, json=payload) for payload in payloads]

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
    return IntrospectionTokenVerifier(
        introspection_url="https://auth.example.com/introspect",
        client_id="resource-server",
        client_secret="secret",
        issuer_url="https://auth.example.com",
        resource_url="https://telegram.example.com/mcp",
        owner_subject="user-123",
    )


def _active_payload(*, audience: object = _MISSING) -> dict[str, object]:
    return {
        "active": True,
        "client_id": "chatgpt-client",
        "sub": "user-123",
        "scope": "telegram:personal",
        "iss": "https://auth.example.com",
        "aud": ["https://telegram.example.com/mcp"]
        if audience is _MISSING
        else audience,
        "exp": 2_000_000_000,
    }


@pytest.mark.parametrize(
    "audience",
    [
        "https://telegram.example.com/mcp",
        ["another-audience", "https://telegram.example.com/mcp"],
    ],
    ids=["string-audience", "collection-audience"],
)
def test_introspection_verifier_accepts_only_owner_with_expected_issuer_and_audience(
    monkeypatch, audience
) -> None:
    verifier = _introspection_verifier(monkeypatch, _active_payload(audience=audience))

    accepted = asyncio.run(verifier.verify_token("good"))

    assert accepted is not None
    assert accepted.client_id == "chatgpt-client"
    assert accepted.subject == "user-123"
    assert accepted.resource == "https://telegram.example.com/mcp"
    assert accepted.claims == {"iss": "https://auth.example.com"}


@pytest.mark.parametrize(
    ("case", "claim", "value"),
    [
        ("missing-active", "active", _MISSING),
        ("inactive", "active", False),
        ("invalid-active", "active", 1),
        ("missing-issuer", "iss", _MISSING),
        ("wrong-issuer", "iss", "https://attacker.example.com"),
        ("non-string-issuer", "iss", None),
        ("missing-audience", "aud", _MISSING),
        ("wrong-audience-string", "aud", "https://other.example.com/mcp"),
        ("wrong-audience-collection", "aud", ["https://other.example.com/mcp"]),
        ("invalid-audience-type", "aud", None),
        ("missing-subject", "sub", _MISSING),
        ("wrong-subject", "sub", "user-456"),
        ("non-string-subject", "sub", 123),
        ("expired", "exp", 0),
        ("invalid-expiry", "exp", "not-a-timestamp"),
    ],
)
def test_introspection_verifier_rejects_missing_or_wrong_security_claim(
    monkeypatch, case, claim, value
) -> None:
    payload = _active_payload()
    if value is _MISSING:
        payload.pop(claim)
    else:
        payload[claim] = value
    verifier = _introspection_verifier(monkeypatch, payload)

    assert asyncio.run(verifier.verify_token(case)) is None


def test_introspection_verifier_requires_nonempty_owner_subject() -> None:
    with pytest.raises(ConfigurationError, match="TELEGRAM_MCP_OWNER_SUBJECT"):
        IntrospectionTokenVerifier(
            introspection_url="https://auth.example.com/introspect",
            client_id="resource-server",
            client_secret="secret",
            issuer_url="https://auth.example.com",
            resource_url="https://telegram.example.com/mcp",
            owner_subject="   ",
        )
