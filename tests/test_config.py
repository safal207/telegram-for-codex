from telegram_codex.config import _as_bool


def test_as_bool_defaults_false() -> None:
    assert _as_bool(None) is False


def test_as_bool_true_values() -> None:
    for value in ("1", "true", "TRUE", "yes", "on"):
        assert _as_bool(value) is True


def test_as_bool_false_values() -> None:
    for value in ("0", "false", "no", "off", "anything"):
        assert _as_bool(value) is False
