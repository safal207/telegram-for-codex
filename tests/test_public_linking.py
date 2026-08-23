from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from telegram_codex.public_mode.connections import (
    InMemoryBusinessConnectionRegistry,
    UnboundTelegramBusinessUser,
)
from telegram_codex.public_mode.linking import LinkTokenInvalid, OneTimeTelegramLinkBroker
from telegram_codex.public_mode.models import BusinessConnection, BusinessRights


def _business_connection(*, user_id: int = 777, enabled: bool = True) -> BusinessConnection:
    return BusinessConnection(
        connection_id="bc-public-1",
        user_id=user_id,
        user_chat_id=888,
        connected_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        rights=BusinessRights(can_reply=True),
        is_enabled=enabled,
    )


def test_deep_link_token_is_one_time_and_not_stored_raw() -> None:
    broker = OneTimeTelegramLinkBroker(ttl_seconds=600)
    token, deep_link = broker.create("app-user-1", bot_username="our_business_bot")

    assert deep_link.startswith("https://t.me/our_business_bot?start=link_")
    assert token in deep_link
    assert token not in repr(broker._pending)
    assert broker.consume(f"link_{token}") == "app-user-1"

    with pytest.raises(LinkTokenInvalid, match="already used"):
        broker.consume(f"link_{token}")


def test_deep_link_token_expires() -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    current = [now]
    broker = OneTimeTelegramLinkBroker(ttl_seconds=60, clock=lambda: current[0])
    token, _ = broker.create("app-user-1", bot_username="our_business_bot")
    current[0] = now + timedelta(seconds=61)

    with pytest.raises(LinkTokenInvalid, match="expired"):
        broker.consume(f"link_{token}")


def test_business_connection_binds_only_after_telegram_identity_link() -> None:
    registry = InMemoryBusinessConnectionRegistry()
    connection = _business_connection(user_id=777)

    with pytest.raises(UnboundTelegramBusinessUser):
        registry.upsert_connection(connection)

    registry.bind_identity("app-user-1", 777)
    binding = registry.upsert_connection(connection)

    assert binding.app_user_id == "app-user-1"
    assert registry.for_app_user("app-user-1") == binding
    assert registry.for_connection("bc-public-1") == binding


def test_disconnect_revokes_connection_routing_immediately() -> None:
    registry = InMemoryBusinessConnectionRegistry()
    registry.bind_identity("app-user-1", 777)
    registry.upsert_connection(_business_connection(user_id=777))

    registry.disconnect("bc-public-1")

    assert registry.for_app_user("app-user-1") is None
    assert registry.for_connection("bc-public-1") is None
