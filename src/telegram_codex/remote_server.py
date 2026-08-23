from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .connect_web import install_connect_routes
from .health import install_health_routes
from .personal_auth import load_personal_auth_from_env
from .server import create_mcp, reset_gateway


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def configure_remote_mcp(app: FastMCP) -> FastMCP:
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

    app.settings.host = host
    app.settings.port = port
    app.settings.streamable_http_path = "/mcp"
    app.settings.stateless_http = True
    app.settings.json_response = True
    app.settings.transport_security = security
    return app


def build_remote_mcp() -> FastMCP:
    """Build the remote Personal MCP with fail-closed caller authentication."""
    auth = load_personal_auth_from_env()
    app = create_mcp(token_verifier=auth.verifier, auth=auth.settings)

    # `/connect` uses its separate TELEGRAM_CONNECT_TOKEN gate. MCP SDK auth
    # wraps `/mcp`; custom connect routes remain independently protected.
    install_connect_routes(app, reset_gateway)

    # Hosting probes need a stable, content-free route that does not require
    # Telegram authorization and does not reveal whether a session exists.
    install_health_routes(app)
    return configure_remote_mcp(app)


def main() -> None:
    build_remote_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()
