from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def install_health_routes(mcp: FastMCP) -> None:
    """Install a content-free health endpoint for hosting probes.

    The endpoint intentionally does not inspect or expose Telegram authorization,
    session state, OAuth tokens, phone numbers, chat state, or secret presence.
    If the process could build the authenticated MCP application and serve HTTP,
    it is healthy enough for the deployment platform to route traffic to it.
    """

    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> Response:
        return JSONResponse(
            {"ok": True, "service": "telegram-for-codex", "mode": "personal"},
            headers={"Cache-Control": "no-store"},
        )
