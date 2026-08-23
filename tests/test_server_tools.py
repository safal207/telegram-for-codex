from __future__ import annotations

import pytest

from telegram_codex.server import _require_confirm


def test_require_confirm_rejects_false() -> None:
    with pytest.raises(ValueError, match="confirm=true"):
        _require_confirm(False)


def test_require_confirm_accepts_true() -> None:
    assert _require_confirm(True) is None
