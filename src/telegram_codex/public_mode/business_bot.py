from __future__ import annotations

from typing import Any

import httpx

from .models import BusinessConnection, PublicAction
from .policy import require_action


class TelegramBotAPIError(RuntimeError):
    pass


class TelegramBusinessBotClient:
    """Minimal Telegram Bot API client for delegated Business connections.

    The bot token is a server credential shared by the service. Public users are
    represented by revocable `business_connection_id` values, never by personal
    MTProto sessions.
    """

    def __init__(
        self,
        bot_token: str,
        *,
        client: httpx.AsyncClient | None = None,
        api_base: str = "https://api.telegram.org",
    ) -> None:
        if not bot_token:
            raise ValueError("bot_token is required")
        self._bot_token = bot_token
        self._client = client
        self._owns_client = client is None
        self._api_base = api_base.rstrip("/")

    async def __aenter__(self) -> "TelegramBusinessBotClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:
        url = f"{self._api_base}/bot{self._bot_token}/{method}"
        response = await self._http().post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            description = str(body.get("description") or "Telegram Bot API request failed")
            raise TelegramBotAPIError(description)
        return body.get("result")

    async def get_connection(self, connection_id: str) -> BusinessConnection:
        result = await self._call(
            "getBusinessConnection",
            {"business_connection_id": connection_id},
        )
        if not isinstance(result, dict):
            raise TelegramBotAPIError("getBusinessConnection returned an invalid result")
        return BusinessConnection.from_bot_api(result)

    async def send_message(
        self,
        connection: BusinessConnection,
        *,
        chat_id: int,
        text: str,
    ) -> dict[str, Any]:
        require_action(connection, PublicAction.SEND)
        result = await self._call(
            "sendMessage",
            {
                "business_connection_id": connection.connection_id,
                "chat_id": int(chat_id),
                "text": text,
            },
        )
        return dict(result)

    async def edit_message(
        self,
        connection: BusinessConnection,
        *,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> dict[str, Any]:
        require_action(connection, PublicAction.EDIT)
        result = await self._call(
            "editMessageText",
            {
                "business_connection_id": connection.connection_id,
                "chat_id": int(chat_id),
                "message_id": int(message_id),
                "text": text,
            },
        )
        return dict(result) if isinstance(result, dict) else {"ok": bool(result)}

    async def mark_read(
        self,
        connection: BusinessConnection,
        *,
        chat_id: int,
        message_id: int,
    ) -> bool:
        require_action(connection, PublicAction.MARK_READ)
        result = await self._call(
            "readBusinessMessage",
            {
                "business_connection_id": connection.connection_id,
                "chat_id": int(chat_id),
                "message_id": int(message_id),
            },
        )
        return bool(result)

    async def delete_messages(
        self,
        connection: BusinessConnection,
        *,
        message_ids: list[int],
        sent_only: bool = True,
    ) -> bool:
        action = PublicAction.DELETE_SENT if sent_only else PublicAction.DELETE_ANY
        require_action(connection, action)
        if not 1 <= len(message_ids) <= 100:
            raise ValueError("message_ids must contain 1..100 identifiers")
        result = await self._call(
            "deleteBusinessMessages",
            {
                "business_connection_id": connection.connection_id,
                "message_ids": [int(value) for value in message_ids],
            },
        )
        return bool(result)
