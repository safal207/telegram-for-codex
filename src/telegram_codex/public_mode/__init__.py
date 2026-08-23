"""Public multi-user Telegram Business mode.

This package deliberately does not use personal MTProto sessions. It models
Telegram Business connections as delegated, revocable capabilities.
"""

from .models import (
    BusinessConnection,
    BusinessMessageEvent,
    BusinessRights,
    EventKind,
    PublicAction,
    RetentionMode,
    RetentionPolicy,
)

__all__ = [
    "BusinessConnection",
    "BusinessMessageEvent",
    "BusinessRights",
    "EventKind",
    "PublicAction",
    "RetentionMode",
    "RetentionPolicy",
]
