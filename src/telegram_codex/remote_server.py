from __future__ import annotations

import os

from .server import mcp


def main() -> None:
    host = os.getenv("TELEGRAM_MCP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("TELEGRAM_MCP_PORT", "8000")))
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path="/mcp",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
