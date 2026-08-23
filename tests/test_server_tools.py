from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from telegram_codex import server
from telegram_codex.server import _require_confirm


def test_require_confirm_rejects_false() -> None:
    with pytest.raises(ValueError, match="confirm=true"):
        _require_confirm(False)


def test_require_confirm_accepts_true() -> None:
    assert _require_confirm(True) is None


def test_whoami_strips_phone_number(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGateway:
        async def whoami(self):
            return {
                "authorized": True,
                "user_id": 123,
                "username": "tester",
                "phone": "+79991234567",
            }

    monkeypatch.setattr(server, "gateway", lambda: FakeGateway())

    result = asyncio.run(server.telegram_whoami())

    assert result["authorized"] is True
    assert result["username"] == "tester"
    assert "phone" not in result
