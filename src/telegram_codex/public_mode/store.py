from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .models import BusinessMessageEvent, RetentionMode, RetentionPolicy


class BusinessEventStore(Protocol):
    async def append(self, tenant_id: str, event: BusinessMessageEvent) -> None: ...

    async def recent(
        self,
        tenant_id: str,
        connection_id: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]: ...

    async def search(
        self,
        tenant_id: str,
        connection_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]: ...

    async def purge(self, tenant_id: str, connection_id: str) -> None: ...


class NullBusinessEventStore:
    """Default privacy mode: process live events without retaining message bodies."""

    async def append(self, tenant_id: str, event: BusinessMessageEvent) -> None:
        return None

    async def recent(
        self,
        tenant_id: str,
        connection_id: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]:
        return []

    async def search(
        self,
        tenant_id: str,
        connection_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]:
        return []

    async def purge(self, tenant_id: str, connection_id: str) -> None:
        return None


@dataclass(slots=True)
class _StoredEvent:
    event: BusinessMessageEvent
    expires_at: datetime


class MemoryTTLBusinessEventStore:
    """Development/test store proving tenant isolation + bounded retention.

    Production should use an encrypted database implementation with the same
    interface. This class must not be treated as durable storage.
    """

    def __init__(self, policy: RetentionPolicy) -> None:
        if policy.mode is not RetentionMode.TTL or policy.ttl_seconds is None:
            raise ValueError("MemoryTTLBusinessEventStore requires TTL retention")
        self._ttl = timedelta(seconds=policy.ttl_seconds)
        self._events: dict[tuple[str, str], list[_StoredEvent]] = defaultdict(list)

    def _prune(self, key: tuple[str, str]) -> None:
        now = datetime.now(timezone.utc)
        self._events[key] = [item for item in self._events[key] if item.expires_at > now]

    async def append(self, tenant_id: str, event: BusinessMessageEvent) -> None:
        key = (tenant_id, event.connection_id)
        self._prune(key)
        self._events[key].append(
            _StoredEvent(
                event=event,
                expires_at=datetime.now(timezone.utc) + self._ttl,
            )
        )

    async def recent(
        self,
        tenant_id: str,
        connection_id: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]:
        key = (tenant_id, connection_id)
        self._prune(key)
        return [item.event for item in self._events[key][-max(0, limit):]][::-1]

    async def search(
        self,
        tenant_id: str,
        connection_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[BusinessMessageEvent]:
        needle = query.casefold().strip()
        if not needle:
            return []
        recent = await self.recent(tenant_id, connection_id, limit=10_000)
        matches = [event for event in recent if needle in event.text.casefold()]
        return matches[: max(0, limit)]

    async def purge(self, tenant_id: str, connection_id: str) -> None:
        self._events.pop((tenant_id, connection_id), None)
