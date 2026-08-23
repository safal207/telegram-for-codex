from telegram_codex import remote_server


def test_fastmcp_exposes_remote_settings() -> None:
    settings = remote_server.mcp.settings
    for name in (
        "host",
        "port",
        "streamable_http_path",
        "stateless_http",
        "json_response",
        "transport_security",
    ):
        assert hasattr(settings, name), f"FastMCP settings missing expected field: {name}"


def test_remote_server_runs_streamable_http(monkeypatch) -> None:
    calls: dict[str, object] = {}

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
    monkeypatch.setattr(remote_server.mcp, "run", lambda **kwargs: calls.update(kwargs))

    remote_server.main()

    settings = remote_server.mcp.settings
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
    assert calls == {"transport": "streamable-http"}


def test_csv_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TEST_LIST", raising=False)
    assert remote_server._csv_env("TEST_LIST", "one,two:*") == ["one", "two:*"]
