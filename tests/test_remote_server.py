from telegram_codex import remote_server


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

    security = calls.pop("transport_security")
    assert security.enable_dns_rebinding_protection is True
    assert security.allowed_hosts == [
        "telegram.example.com",
        "telegram.example.com:*",
    ]
    assert security.allowed_origins == [
        "https://chatgpt.com",
        "https://chat.openai.com",
    ]
    assert calls == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 9123,
        "streamable_http_path": "/mcp",
        "stateless_http": True,
        "json_response": True,
    }


def test_csv_env_uses_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TEST_LIST", raising=False)
    assert remote_server._csv_env("TEST_LIST", "one,two:*") == ["one", "two:*"]
