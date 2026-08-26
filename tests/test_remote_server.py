from mcp.server.fastmcp import FastMCP

from telegram_codex import remote_server


_STATIC_TOKEN = "C0d3xMcp_7Gv9Q2rL5sN8wK4yF6hJ1bT3"


def _set_static_auth(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_MCP_AUTH_MODE", "static")
    monkeypatch.setenv("TELEGRAM_MCP_STATIC_TOKEN", _STATIC_TOKEN)
    monkeypatch.setenv("TELEGRAM_MCP_PUBLIC_URL", "http://localhost:8000/mcp")
    monkeypatch.delenv("TELEGRAM_CONNECT_TOKEN", raising=False)


def test_fastmcp_exposes_remote_settings(monkeypatch) -> None:
    _set_static_auth(monkeypatch)
    app = remote_server.build_remote_mcp()
    settings = app.settings
    for name in (
        "host",
        "port",
        "streamable_http_path",
        "stateless_http",
        "json_response",
        "transport_security",
        "auth",
    ):
        assert hasattr(settings, name), f"FastMCP settings missing expected field: {name}"
    assert settings.auth is not None


def test_remote_server_runs_streamable_http_with_auth(monkeypatch) -> None:
    calls: dict[str, object] = {}
    _set_static_auth(monkeypatch)
    monkeypatch.setenv("TELEGRAM_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setenv(
        "TELEGRAM_MCP_ALLOWED_HOSTS",
        "telegram.example.com,telegram.example.com:*",
    )
    monkeypatch.setenv(
        "TELEGRAM_MCP_ALLOWED_ORIGINS",
        "https://chatgpt.com,https://chat.openai.com",
    )
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: calls.update(kwargs))

    remote_server.main()

    assert calls == {"transport": "streamable-http"}


def test_configure_remote_mcp_applies_transport_security(monkeypatch) -> None:
    _set_static_auth(monkeypatch)
    monkeypatch.setenv("TELEGRAM_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setenv(
        "TELEGRAM_MCP_ALLOWED_HOSTS",
        "telegram.example.com,telegram.example.com:*",
    )
    monkeypatch.setenv(
        "TELEGRAM_MCP_ALLOWED_ORIGINS",
        "https://chatgpt.com,https://chat.openai.com",
    )
    app = remote_server.build_remote_mcp()
    settings = app.settings

    assert settings.host == "0.0.0.0"
    assert settings.port == 9123
    assert settings.streamable_http_path == "/mcp"
    assert settings.stateless_http is True
    assert settings.json_response is True
    assert settings.transport_security.enable_dns_rebinding_protection is True
    assert settings.transport_security.allowed_hosts == [
        "telegram.example.com",
        "telegram.example.com:*",
    ]
    assert settings.transport_security.allowed_origins == [
        "https://chatgpt.com",
        "https://chat.openai.com",
    ]


def test_csv_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TEST_LIST", raising=False)
    assert remote_server._csv_env("TEST_LIST", "one,two:*") == ["one", "two:*"]
