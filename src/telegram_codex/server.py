from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .client import TelegramGateway
from .config import Settings

mcp = FastMCP("telegram-for-codex")
_gateway: TelegramGateway | None = None

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False)
_DESTRUCTIVE_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


def gateway() -> TelegramGateway:
    global _gateway
    if _gateway is None:
        _gateway = TelegramGateway(Settings.from_env())
    return _gateway


async def reset_gateway() -> None:
    """Drop the cached Telegram client so new session credentials take effect."""
    global _gateway
    old = _gateway
    _gateway = None
    if old is not None and old.client.is_connected():
        await old.client.disconnect()


def _require_confirm(confirm: bool) -> None:
    if not confirm:
        raise ValueError(
            "Pass confirm=true only after the user approves this write action."
        )


@mcp.tool(annotations=_READ_ONLY)
async def telegram_whoami() -> dict:
    """Show authorization status of the local Telegram session and current safety configuration."""
    return await gateway().whoami()


@mcp.tool(annotations=_READ_ONLY)
def telegram_audit_log(limit: int = 20) -> list[dict]:
    """Show the most recent audited Telegram write attempts (send/edit), including denied ones."""
    return gateway().read_audit_tail(limit=max(1, min(limit, 100)))


@mcp.tool(annotations=_READ_ONLY)
async def telegram_list_chats(limit: int = 20, unread_only: bool = False) -> list[dict]:
    """List recent Telegram chats. Set unread_only=true to return only chats with unread messages."""
    return await gateway().list_chats(limit=limit, unread_only=unread_only)


@mcp.tool(annotations=_READ_ONLY)
async def telegram_get_messages(chat_id: int, limit: int = 20) -> list[dict]:
    """Read recent messages from a Telegram chat by chat_id."""
    return await gateway().get_messages(chat_id=chat_id, limit=limit)


@mcp.tool(annotations=_READ_ONLY)
async def telegram_search_messages(
    query: str, chat_id: int | None = None, limit: int = 20
) -> list[dict]:
    """Search Telegram messages globally or inside one chat."""
    return await gateway().search_messages(query=query, chat_id=chat_id, limit=limit)


@mcp.tool(annotations=_WRITE)
async def telegram_send_message(chat_id: int, text: str, confirm: bool) -> dict:
    """Send a Telegram text message. Requires confirm=true and user approval in Codex."""
    _require_confirm(confirm)
    return await gateway().send_message(chat_id=chat_id, text=text)


@mcp.tool(annotations=_DESTRUCTIVE_WRITE)
async def telegram_edit_message(
    chat_id: int, message_id: int, text: str, confirm: bool
) -> dict:
    """Edit one of the authenticated user's outgoing Telegram text messages. Requires confirm=true and user approval in Codex."""
    _require_confirm(confirm)
    return await gateway().edit_message(chat_id=chat_id, message_id=message_id, text=text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
