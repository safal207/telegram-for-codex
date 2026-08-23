from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    pass


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str | None
    session_path: Path
    allow_writes: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        api_id_raw = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        if not api_id_raw or not api_hash:
            raise ConfigurationError(
                "TELEGRAM_API_ID and TELEGRAM_API_HASH are required. "
                "Create them at https://my.telegram.org and put them in .env."
            )
        try:
            api_id = int(api_id_raw)
        except ValueError as exc:
            raise ConfigurationError("TELEGRAM_API_ID must be an integer") from exc

        session_path = Path(
            os.getenv("TELEGRAM_SESSION_PATH", ".telegram/codex")
        ).expanduser()
        session_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=os.getenv("TELEGRAM_PHONE"),
            session_path=session_path,
            allow_writes=_as_bool(os.getenv("TELEGRAM_ALLOW_WRITES")),
        )
