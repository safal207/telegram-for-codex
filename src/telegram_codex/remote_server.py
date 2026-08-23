from __future__ import annotations

import os

from mcp.server.transport_security import TransportSecuritySettings

from .server import mcp


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> None:
    host = os.getenv("TELEGRAM_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("TELEGRAM_MCP_PORT", "8000")))
    allowed_hosts = _csv_env(
        "TELEGRAM_MCP_ALLOWED_HOSTS",
        "localhost,localhost:*,127.0.0.1,127.0.0.1:*",
    )
    allowed_origins = _csv_env(
        "TELEGRAM_MCP_ALLOWED_ORIGINS",
        "http://localhost:*,http://127.0.0.1:*",
    )
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )

    # FastMCP 1.29 stores HTTP deployment options in `mcp.settings`;
    # `run()` itself accepts only the transport selector.
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.settings.streamable_http_path = "/mcp"
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.transport_security = security

    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
