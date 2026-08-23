from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from telegram_codex.public_mode.business_bot import TelegramBusinessBotClient
from telegram_codex.public_mode.models import (
    BusinessConnection,
    BusinessMessageEvent,
    BusinessRights,
    EventKind,
    PublicAction,
    RetentionMode,
    RetentionPolicy,
)
from telegram_codex.public_mode.policy import (
    BusinessPermissionDenied,
    action_allowed,
    require_action,
)
from telegram_codex.public_mode.store import (
    MemoryTTLBusinessEventStore,
    NullBusinessEventStore,
)
from telegram_codex.public_mode.webhook import parse_business_update


def _connection(*, enabled: bool = True, rights: BusinessRights | None = None) -> BusinessConnection:
    return BusinessConnection(
        connection_id="bc-123",
        user_id=1,
        user_chat_id=2,
        connected_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        rights=rights or BusinessRights(),
        is_enabled=enabled,
    )


def test_business_rights_gate_each_write_capability() -> None:
    connection = _connection(
        rights=BusinessRights(
            can_reply=True,
            can_read_messages=False,
            can_delete_sent_messages=True,
            can_delete_all_messages=False,
        )
    )

    assert action_allowed(connection, PublicAction.SEND)
    assert action_allowed(connection, PublicAction.EDIT)
    assert action_allowed(connection, PublicAction.DELETE_SENT)
    assert not action_allowed(connection, PublicAction.MARK_READ)
    assert not action_allowed(connection, PublicAction.DELETE_ANY)

    with pytest.raises(BusinessPermissionDenied):
        require_action(connection, PublicAction.MARK_READ)


def test_disabled_business_connection_denies_everything() -> None:
    connection = _connection(
        enabled=False,
        rights=BusinessRights(
            can_reply=True,
            can_read_messages=True,
            can_delete_sent_messages=True,
            can_delete_all_messages=True,
        ),
    )
    assert all(not action_allowed(connection, action) for action in PublicAction)


def test_webhook_parses_business_connection_and_message() -> None:
    connection_update = {
        "business_connection": {
            "id": "bc-123",
            "user": {"id": 99},
            "user_chat_id": 100,
            "date": 1_777_777_777,
            "rights": {"can_reply": True, "can_read_messages": True},
            "is_enabled": True,
        }
    }
    parsed = parse_business_update(connection_update)
    assert parsed is not None and parsed.connection is not None
    assert parsed.connection.connection_id == "bc-123"
    assert parsed.connection.rights.can_reply is True

    message_update = {
        "business_message": {
            "business_connection_id": "bc-123",
            "message_id": 55,
            "date": 1_777_777_778,
            "chat": {"id": 321},
            "text": "hello",
        }
    }
    parsed = parse_business_update(message_update)
    assert parsed is not None and parsed.message is not None
    assert parsed.message.kind is EventKind.NEW
    assert parsed.message.text == "hello"
    assert parsed.message.chat_id == 321


def test_default_null_store_retains_nothing() -> None:
    async def scenario() -> None:
        store = NullBusinessEventStore()
        event = BusinessMessageEvent(
            connection_id="bc-123",
            chat_id=1,
            message_id=2,
            kind=EventKind.NEW,
            occurred_at=datetime.now(timezone.utc),
            text="private text",
        )
        await store.append("tenant-a", event)
        assert await store.recent("tenant-a", "bc-123") == []
        assert await store.search("tenant-a", "bc-123", "private") == []

    asyncio.run(scenario())


def test_ttl_store_isolates_tenants() -> None:
    async def scenario() -> None:
        store = MemoryTTLBusinessEventStore(
            RetentionPolicy(mode=RetentionMode.TTL, ttl_seconds=60)
        )
        event = BusinessMessageEvent(
            connection_id="bc-123",
            chat_id=1,
            message_id=2,
            kind=EventKind.NEW,
            occurred_at=datetime.now(timezone.utc),
            text="alpha secret",
        )
        await store.append("tenant-a", event)
        assert len(await store.search("tenant-a", "bc-123", "alpha")) == 1
        assert await store.search("tenant-b", "bc-123", "alpha") == []

    asyncio.run(scenario())


def test_business_bot_client_uses_connection_id_and_rights() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {"message_id": 7, "chat": {"id": 123}, "date": 1, "text": "hi"},
                },
            )
        return httpx.Response(200, json={"ok": True, "result": True})

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            client = TelegramBusinessBotClient("bot-secret", client=http)
            connection = _connection(rights=BusinessRights(can_reply=True))
            result = await client.send_message(connection, chat_id=123, text="hi")
            assert result["message_id"] == 7

            denied = _connection(rights=BusinessRights(can_reply=False))
            with pytest.raises(BusinessPermissionDenied):
                await client.send_message(denied, chat_id=123, text="blocked")

    asyncio.run(scenario())
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/sendMessage")
    assert b'"business_connection_id":"bc-123"' in requests[0].content
