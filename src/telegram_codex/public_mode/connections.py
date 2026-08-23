from __future__ import annotations

from dataclasses import dataclass

from .models import BusinessConnection


class UnboundTelegramBusinessUser(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ConnectionBinding:
    app_user_id: str
    telegram_user_id: int
    connection: BusinessConnection


class InMemoryBusinessConnectionRegistry:
    """Development registry for identity -> Telegram Business delegation.

    Production replaces this with a transactional database implementation.
    `business_connection_id` is revocable routing metadata, not a Telegram login
    credential.
    """

    def __init__(self) -> None:
        self._telegram_to_app: dict[int, str] = {}
        self._by_app: dict[str, ConnectionBinding] = {}
        self._by_connection: dict[str, ConnectionBinding] = {}

    def bind_identity(self, app_user_id: str, telegram_user_id: int) -> None:
        if not app_user_id:
            raise ValueError("app_user_id is required")
        self._telegram_to_app[int(telegram_user_id)] = app_user_id

    def upsert_connection(self, connection: BusinessConnection) -> ConnectionBinding:
        app_user_id = self._telegram_to_app.get(connection.user_id)
        if app_user_id is None:
            raise UnboundTelegramBusinessUser(
                f"Telegram user {connection.user_id} has no completed app link"
            )
        binding = ConnectionBinding(
            app_user_id=app_user_id,
            telegram_user_id=connection.user_id,
            connection=connection,
        )
        old = self._by_app.get(app_user_id)
        if old is not None:
            self._by_connection.pop(old.connection.connection_id, None)
        self._by_app[app_user_id] = binding
        self._by_connection[connection.connection_id] = binding
        return binding

    def for_app_user(self, app_user_id: str) -> ConnectionBinding | None:
        return self._by_app.get(app_user_id)

    def for_connection(self, connection_id: str) -> ConnectionBinding | None:
        return self._by_connection.get(connection_id)

    def disconnect(self, connection_id: str) -> None:
        binding = self._by_connection.pop(connection_id, None)
        if binding is None:
            return
        current = self._by_app.get(binding.app_user_id)
        if current is not None and current.connection.connection_id == connection_id:
            self._by_app.pop(binding.app_user_id, None)
