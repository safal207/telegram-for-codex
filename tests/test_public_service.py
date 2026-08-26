from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from telegram_codex.public_mode.connections import InMemoryBusinessConnectionRegistry
from telegram_codex.public_mode.models import (
    BusinessConnection,
    BusinessMessageEvent,
    BusinessRights,
    EventKind,
    RetentionMode,
    RetentionPolicy,
)
from telegram_codex.public_mode.service import PublicConnectionRequired, PublicTelegramService
from telegram_codex.public_mode.store import MemoryTTLBusinessEventStore
from telegram_codex.public_mode.webhook import DeletedBusinessMessages, ParsedBusinessUpdate


class FakeBot:
    def __init__(self) -> None:
        self.connection_ids: list[str] = []

    async def send_message(self, connection, *, chat_id: int, text: str) -> dict:
        self.connection_ids.append(connection.connection_id)
        return {"chat_id": chat_id, "text": text}

    async def edit_message(self, connection, *, chat_id: int, message_id: int, text: str) -> dict:
        self.connection_ids.append(connection.connection_id)
        return {"message_id": message_id, "text": text}

    async def mark_read(self, connection, *, chat_id: int, message_id: int) -> bool:
        self.connection_ids.append(connection.connection_id)
        return True

    async def delete_messages(self, connection, *, message_ids: list[int], sent_only: bool = True) -> bool:
        self.connection_ids.append(connection.connection_id)
        return True


def _connection(*, enabled: bool = True) -> BusinessConnection:
    return BusinessConnection(
        connection_id="bc-service",
        user_id=777,
        user_chat_id=888,
        connected_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        rights=BusinessRights(
            can_reply=True,
            can_read_messages=True,
            can_delete_sent_messages=True,
        ),
        is_enabled=enabled,
    )


def test_service_resolves_connection_server_side() -> None:
    async def scenario() -> None:
        registry = InMemoryBusinessConnectionRegistry()
        registry.bind_identity("app-user", 777)
        registry.upsert_connection(_connection())
        bot = FakeBot()
        service = PublicTelegramService(
            registry=registry,
            events=MemoryTTLBusinessEventStore(
                RetentionPolicy(mode=RetentionMode.TTL, ttl_seconds=60)
            ),
            bot=bot,
        )

        result = await service.send_message("app-user", chat_id=123, text="hello")
        assert result == {"chat_id": 123, "text": "hello"}
        assert bot.connection_ids == ["bc-service"]

        with pytest.raises(PublicConnectionRequired):
            await service.send_message("other-user", chat_id=123, text="blocked")

    asyncio.run(scenario())


def test_ingest_routes_events_to_bound_tenant_and_removes_deleted() -> None:
    async def scenario() -> None:
        registry = InMemoryBusinessConnectionRegistry()
        registry.bind_identity("tenant-a", 777)
        registry.upsert_connection(_connection())
        store = MemoryTTLBusinessEventStore(
            RetentionPolicy(mode=RetentionMode.TTL, ttl_seconds=60)
        )
        service = PublicTelegramService(registry=registry, events=store, bot=FakeBot())
        event = BusinessMessageEvent(
            connection_id="bc-service",
            chat_id=1,
            message_id=10,
            kind=EventKind.NEW,
            occurred_at=datetime.now(timezone.utc),
            text="needle",
        )

        await service.ingest(ParsedBusinessUpdate(message=event))
        assert len(await service.search("tenant-a", "needle")) == 1

        await service.ingest(
            ParsedBusinessUpdate(
                deleted=DeletedBusinessMessages(
                    connection_id="bc-service",
                    chat_id=1,
                    message_ids=(10,),
                )
            )
        )
        assert await service.search("tenant-a", "needle") == []

    asyncio.run(scenario())


def test_disconnect_purges_history_and_revokes_routing() -> None:
    async def scenario() -> None:
        registry = InMemoryBusinessConnectionRegistry()
        registry.bind_identity("tenant-a", 777)
        registry.upsert_connection(_connection())
        store = MemoryTTLBusinessEventStore(
            RetentionPolicy(mode=RetentionMode.TTL, ttl_seconds=60)
        )
        service = PublicTelegramService(registry=registry, events=store, bot=FakeBot())
        event = BusinessMessageEvent(
            connection_id="bc-service",
            chat_id=1,
            message_id=10,
            kind=EventKind.NEW,
            occurred_at=datetime.now(timezone.utc),
            text="will disappear",
        )
        await service.ingest(ParsedBusinessUpdate(message=event))

        await service.ingest(ParsedBusinessUpdate(connection=_connection(enabled=False)))

        assert registry.for_app_user("tenant-a") is None
        assert await store.search("tenant-a", "bc-service", "disappear") == []
        with pytest.raises(PublicConnectionRequired):
            await service.send_message("tenant-a", chat_id=1, text="blocked")

    asyncio.run(scenario())
