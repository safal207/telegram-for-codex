from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    pass


_AUDIT_OFF_VALUES = {"off", "none", "disabled", "0", "false", ""}


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_allowlist(value: str | None) -> frozenset[int] | None:
    if value is None or not value.strip():
        return None
    ids: set[int] = set()
    for part in value.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError as exc:
            raise ConfigurationError(
                f"TELEGRAM_WRITE_CHAT_ALLOWLIST must contain comma-separated integers, got {chunk!r}"
            ) from exc
    return frozenset(ids) if ids else None


def _load_session_string() -> str | None:
    raw = os.getenv("TELEGRAM_SESSION_STRING")
    if raw and raw.strip():
        return raw.strip()

    file_raw = os.getenv("TELEGRAM_SESSION_STRING_FILE")
    if not file_raw or not file_raw.strip():
        return None
    path = Path(file_raw).expanduser()
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


@dataclass(frozen=True, slots=True)
class Settings:
    api_id: int
    api_hash: str
    phone: str | None
    session_path: Path
    allow_writes: bool = False
    write_chat_allowlist: frozenset[int] | None = None
    audit_log_path: Path | None = None
    session_string: str | None = None

    @property
    def session_mode(self) -> str:
        return "string" if self.session_string else "file"

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

        session_string = _load_session_string()

        session_path = Path(
            os.getenv("TELEGRAM_SESSION_PATH", ".telegram/codex")
        ).expanduser()
        if session_string is None:
            session_path.parent.mkdir(parents=True, exist_ok=True)

        audit_raw = os.getenv("TELEGRAM_AUDIT_LOG_PATH", ".telegram/audit.jsonl")
        if audit_raw.strip().lower() in _AUDIT_OFF_VALUES:
            audit_log_path: Path | None = None
        else:
            audit_log_path = Path(audit_raw).expanduser()
            audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=os.getenv("TELEGRAM_PHONE"),
            session_path=session_path,
            allow_writes=_as_bool(os.getenv("TELEGRAM_ALLOW_WRITES")),
            write_chat_allowlist=_parse_allowlist(
                os.getenv("TELEGRAM_WRITE_CHAT_ALLOWLIST")
            ),
            audit_log_path=audit_log_path,
            session_string=session_string,
        )
