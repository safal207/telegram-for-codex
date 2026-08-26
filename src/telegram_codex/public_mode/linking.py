from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote


class LinkTokenInvalid(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class PendingLink:
    app_user_id: str
    token_hash: str
    expires_at: datetime


class OneTimeTelegramLinkBroker:
    """Prototype one-time account linker for the public onboarding flow.

    The raw deep-link token is returned once and never stored. Only SHA-256 of
    the token is retained, so a database leak does not reveal usable pending
    Telegram deep links.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 10 * 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._pending: dict[str, PendingLink] = {}

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create(self, app_user_id: str, *, bot_username: str) -> tuple[str, str]:
        if not app_user_id:
            raise ValueError("app_user_id is required")
        username = bot_username.strip().lstrip("@")
        if not username:
            raise ValueError("bot_username is required")

        token = secrets.token_urlsafe(24)
        token_hash = self._hash(token)
        self._pending[token_hash] = PendingLink(
            app_user_id=app_user_id,
            token_hash=token_hash,
            expires_at=self._clock() + self._ttl,
        )
        # Telegram bot start parameters allow base64url-style characters and are
        # capped at 64 chars. Our token is shorter and URL-safe.
        deep_link = f"https://t.me/{quote(username)}?start=link_{quote(token)}"
        return token, deep_link

    def consume(self, start_parameter: str) -> str:
        if not start_parameter.startswith("link_"):
            raise LinkTokenInvalid("Unexpected Telegram link parameter")
        token = start_parameter.removeprefix("link_")
        token_hash = self._hash(token)
        pending = self._pending.pop(token_hash, None)
        if pending is None:
            raise LinkTokenInvalid("Link token is invalid or already used")
        if pending.expires_at <= self._clock():
            raise LinkTokenInvalid("Link token expired")
        return pending.app_user_id
