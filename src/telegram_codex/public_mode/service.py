from __future__ import annotations

from typing import Protocol

from .connections import InMemoryBusinessConnectionRegistry
from .models import BusinessConnection, BusinessMessageEvent
from .store import BusinessEventStore
from .webhook import ParsedBusinessUpdate


class PublicBusinessBotPort(Protocol):
    async def send_message(
        self,
        connection: BusinessConnection,
        *,
        chat_id: int,
        text: str,
    ) -> dict: ...

    async def edit_message(
        self,
        connection: BusinessConnection,
        *,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> dict: ...

    async def mark_read(
        self,
        connection: BusinessConnection,
        *,
        chat_id: int,
        message_id: int,
    ) -> bool: ...

    async def delete_messages(
        self,
        connection: BusinessConnection,
        *,
        message_ids: list[int],
        sent_only: bool = True,
    ) -> bool: ...


class PublicConnectionRequired(PermissionError):
    pass


class PublicTelegramService:
    """Tenant-safe application service for Public Mode.

    `app_user_id` must come from authenticated server context (future OAuth
    middleware). The model/tool schema must never accept a connection id as an
    authority selector.
    """

    def __init__(
        self,
        *,
        registry: InMemoryBusinessConnectionRegistry,
        events: BusinessEventStore,
        bot: PublicBusinessBotPort,
    ) -> None:
        self._registry = registry
        self._events = events
        self._bot = bot

    def _connection_for(self, app_user_id: str) -> BusinessConnection:
        binding = self._registry.for_app_user(app_user_id)
        if binding is None or not binding.connection.is_enabled:
            raise PublicConnectionRequired("No active Telegram Business connection")
        return binding.connection

    async def ingest(self, update: ParsedBusinessUpdate) -> None:
        if update.connection is not None:
            binding = self._registry.upsert_connection(update.connection)
            if not update.connection.is_enabled:
                await self._events.purge(
                    binding.app_user_id,
                    update.connection.connection_id,
                )
                self._registry.disconnect(update.connection.connection_id)
            return

        if update.message is not None:
            binding = self._registry.for_connection(update.message.connection_id)
            if binding is None or not binding.connection.is_enabled:
                return
            await self._events.append(binding.app_user_id, update.message)
            return

        if update.deleted is not None:
            binding = self._registry.for_connection(update.deleted.connection_id)
            if binding is None:
                return
            await self._events.remove_messages(
                binding.app_user_id,
                update.deleted.connection_id,
                update.deleted.message_ids,
            )

    async def recent(self, app_user_id: str, *, limit: int = 20) -> list[BusinessMessageEvent]:
        connection = self._connection_for(app_user_id)
        return await self._events.recent(
            app_user_id,
            connection.connection_id,
            limit=limit,
        )

    async def search(
        self,
        app_user_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]:
        connection = self._connection_for(app_user_id)
        return await self._events.search(
            app_user_id,
            connection.connection_id,
            query,
            limit=limit,
        )

    async def send_message(self, app_user_id: str, *, chat_id: int, text: str) -> dict:
        connection = self._connection_for(app_user_id)
        return await self._bot.send_message(connection, chat_id=chat_id, text=text)

    async def edit_message(
        self,
        app_user_id: str,
        *,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> dict:
        connection = self._connection_for(app_user_id)
        return await self._bot.edit_message(
            connection,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
        )

    async def mark_read(
        self,
        app_user_id: str,
        *,
        chat_id: int,
        message_id: int,
    ) -> bool:
        connection = self._connection_for(app_user_id)
        return await self._bot.mark_read(
            connection,
            chat_id=chat_id,
            message_id=message_id,
        )

    async def delete_messages(
        self,
        app_user_id: str,
        *,
        message_ids: list[int],
        sent_only: bool = True,
    ) -> bool:
        connection = self._connection_for(app_user_id)
        return await self._bot.delete_messages(
            connection,
            message_ids=message_ids,
            sent_only=sent_only,
        )
