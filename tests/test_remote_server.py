from telegram_codex import remote_server


def test_remote_server_runs_streamable_http(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setenv("TELEGRAM_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9123")
    monkeypatch.setattr(remote_server.mcp, "run", lambda **kwargs: calls.update(kwargs))

    remote_server.main()

    assert calls == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 9123,
        "path": "/mcp",
        "stateless_http": True,
        "json_response": True,
    }
