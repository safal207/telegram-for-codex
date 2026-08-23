"""Public multi-user Telegram Business mode.

This package deliberately does not use personal MTProto sessions. It models
Telegram Business connections as delegated, revocable capabilities.
"""

from .connections import ConnectionBinding, InMemoryBusinessConnectionRegistry
from .linking import LinkTokenInvalid, OneTimeTelegramLinkBroker
from .models import (
    BusinessConnection,
    BusinessMessageEvent,
    BusinessRights,
    EventKind,
    PublicAction,
    RetentionMode,
    RetentionPolicy,
)
from .policy import BusinessPermissionDenied
from .service import PublicConnectionRequired, PublicTelegramService
from .store import MemoryTTLBusinessEventStore, NullBusinessEventStore

__all__ = [
    "BusinessConnection",
    "BusinessMessageEvent",
    "BusinessPermissionDenied",
    "BusinessRights",
    "ConnectionBinding",
    "EventKind",
    "InMemoryBusinessConnectionRegistry",
    "LinkTokenInvalid",
    "MemoryTTLBusinessEventStore",
    "NullBusinessEventStore",
    "OneTimeTelegramLinkBroker",
    "PublicAction",
    "PublicConnectionRequired",
    "PublicTelegramService",
    "RetentionMode",
    "RetentionPolicy",
]
