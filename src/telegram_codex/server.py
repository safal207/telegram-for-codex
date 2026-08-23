from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import TelegramGateway
from .config import Settings

mcp = FastMCP("telegram-for-codex")
_gateway: TelegramGateway | None = None


def gateway() -> TelegramGateway:
    global _gateway
    if _gateway is None:
        _gateway = TelegramGateway(Settings.from_env())
    return _gateway


@mcp.tool()
async def telegram_list_chats(limit: int = 20, unread_only: bool = False) -> list[dict]:
    """List recent Telegram chats. Set unread_only=true to return only chats with unread messages."""
    return await gateway().list_chats(limit=limit, unread_only=unread_only)


@mcp.tool()
async def telegram_get_messages(chat_id: int, limit: int = 20) -> list[dict]:
    """Read recent messages from a Telegram chat by chat_id."""
    return await gateway().get_messages(chat_id=chat_id, limit=limit)


@mcp.tool()
async def telegram_search_messages(
    query: str, chat_id: int | None = None, limit: int = 20
) -> list[dict]:
    """Search Telegram messages globally or inside one chat."""
    return await gateway().search_messages(query=query, chat_id=chat_id, limit=limit)


@mcp.tool()
async def telegram_send_message(chat_id: int, text: str) -> dict:
    """Send a Telegram text message. This is a write action and should require user approval in Codex."""
    return await gateway().send_message(chat_id=chat_id, text=text)


@mcp.tool()
async def telegram_edit_message(chat_id: int, message_id: int, text: str) -> dict:
    """Edit one of the authenticated user's outgoing Telegram text messages. This is a write action and should require user approval in Codex."""
    return await gateway().edit_message(chat_id=chat_id, message_id=message_id, text=text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
