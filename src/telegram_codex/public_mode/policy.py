from __future__ import annotations

from .models import BusinessConnection, PublicAction


class BusinessPermissionDenied(PermissionError):
    pass


def action_allowed(connection: BusinessConnection, action: PublicAction) -> bool:
    if not connection.is_enabled:
        return False

    rights = connection.rights
    if action in {PublicAction.SEND, PublicAction.EDIT}:
        return rights.can_reply
    if action is PublicAction.MARK_READ:
        return rights.can_read_messages
    if action is PublicAction.DELETE_SENT:
        return rights.can_delete_sent_messages or rights.can_delete_all_messages
    if action is PublicAction.DELETE_ANY:
        return rights.can_delete_all_messages
    return False


def require_action(connection: BusinessConnection, action: PublicAction) -> None:
    if not action_allowed(connection, action):
        raise BusinessPermissionDenied(
            f"Telegram Business connection {connection.connection_id!r} does not grant {action.value!r}"
        )
