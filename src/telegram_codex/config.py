from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(RuntimeError):
    pass


_AUDIT_OFF_VALUES = {"off", "none", "disabled", "0", "false", ""}
_SECRET_MIN_LENGTH = 32
_SECRET_MIN_UNIQUE_CHARACTERS = 8
_MAX_SESSION_STRING_FILE_BYTES = 1024 * 1024
_SECRET_PLACEHOLDERS = (
    "changeme",
    "exampletoken",
    "inserttoken",
    "placeholder",
    "randomsecret",
    "replaceme",
    "replacewith",
    "telegramconnecttoken",
    "yourtoken",
)


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


def _is_repeated_pattern(value: str) -> bool:
    return bool(value) and value in (value + value)[1:-1]


def validate_high_entropy_secret(value: str, name: str) -> str:
    """Validate a generated bearer secret and return its normalized value."""
    token = value.strip()
    if len(token) < _SECRET_MIN_LENGTH:
        raise ConfigurationError(f"{name} must be at least {_SECRET_MIN_LENGTH} characters")
    normalized = "".join(character for character in token.lower() if character.isalnum())
    if (
        not token.isascii()
        or any(character.isspace() for character in token)
        or any(placeholder in normalized for placeholder in _SECRET_PLACEHOLDERS)
        or len(set(token)) < _SECRET_MIN_UNIQUE_CHARACTERS
        or _is_repeated_pattern(token)
    ):
        raise ConfigurationError(
            f"{name} must be a generated high-entropy secret, not a placeholder or repeated pattern"
        )
    return token


def _ensure_private_directory(path: Path) -> None:
    """Create a private leaf directory without mutating pre-existing parents."""
    created = False
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=False)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise ConfigurationError(f"Unable to create private directory {path}") from exc

    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ConfigurationError(f"Unable to inspect private directory {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ConfigurationError(f"Private directory path must be a real directory: {path}")
    if os.name == "nt":
        return
    if created:
        # mkdir's mode, filtered only by umask, cannot be more permissive than 0700.
        metadata = path.lstat()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ConfigurationError(
            f"Private directory {path} must already have POSIX mode 0700 or stricter"
        )


def _harden_private_file(path: Path) -> None:
    """Reject links/non-files and verify an existing private file is mode 0600."""
    if not os.path.lexists(path):
        return
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ConfigurationError(f"Unable to inspect private file {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ConfigurationError(f"Private file path must be a regular non-symlink file: {path}")
    if metadata.st_nlink != 1:
        raise ConfigurationError(f"Private file must not have hard links: {path}")
    if os.name == "nt":
        return
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ConfigurationError(f"Unable to open private file {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ConfigurationError(f"Private file path must be a regular file: {path}")
        if opened.st_nlink != 1:
            raise ConfigurationError(f"Private file must not have hard links: {path}")
        try:
            os.fchmod(descriptor, 0o600)
        except OSError as exc:
            raise ConfigurationError(f"Unable to secure private file {path}") from exc
        secured = os.fstat(descriptor)
        current = path.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (secured.st_dev, secured.st_ino)
            or secured.st_nlink != 1
        ):
            raise ConfigurationError(f"Private file changed while being secured: {path}")
        if stat.S_IMODE(secured.st_mode) & 0o077:
            raise ConfigurationError(
                f"Private file {path} must have POSIX mode 0600 or stricter"
            )
    finally:
        os.close(descriptor)


def _read_private_text_file(path: Path, *, max_bytes: int) -> str:
    """Read a bounded credential file without following a final-component symlink."""
    _harden_private_file(path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ConfigurationError(f"Unable to open private file {path}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ConfigurationError(
                f"Private file path must be a regular file: {path}"
            )
        if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ConfigurationError(
                f"Private file {path} must have POSIX mode 0600 or stricter"
            )
        chunks: list[bytes] = []
        total = 0
        while total <= max_bytes:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > max_bytes:
            raise ConfigurationError(f"Private file {path} exceeds the maximum safe size")
    finally:
        os.close(descriptor)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError(f"Private file {path} must contain UTF-8 text") from exc


def _telethon_session_file(session_path: Path) -> Path:
    """Return the SQLite filename Telethon derives from a file-session path."""
    if str(session_path).endswith(".session"):
        return session_path
    return Path(f"{session_path}.session")


def _telethon_session_files(session_path: Path) -> tuple[Path, ...]:
    """Return the Telethon SQLite database and every security-sensitive sidecar."""
    session_file = _telethon_session_file(session_path)
    return (
        session_file,
        Path(f"{session_file}-journal"),
        Path(f"{session_file}-shm"),
        Path(f"{session_file}-wal"),
    )


def _private_path_key(path: Path) -> str:
    absolute = os.path.abspath(os.path.normpath(os.fspath(path)))
    return os.path.normcase(os.path.realpath(absolute))


def _validate_private_path_collisions(
    *,
    session_path: Path,
    session_string_path: Path,
    audit_log_path: Path | None,
) -> None:
    session_file, session_journal, session_shm, session_wal = (
        _telethon_session_files(session_path)
    )
    labeled_paths: list[tuple[str, Path]] = [
        ("TELEGRAM_SESSION_STRING_FILE", session_string_path),
        ("Telethon session database", session_file),
        ("Telethon session journal", session_journal),
        ("Telethon session shared memory", session_shm),
        ("Telethon session write-ahead log", session_wal),
    ]
    if audit_log_path is not None:
        labeled_paths.extend(
            [
                ("TELEGRAM_AUDIT_LOG_PATH", audit_log_path),
                ("audit backup 1", audit_log_path.with_name(f"{audit_log_path.name}.1")),
                ("audit backup 2", audit_log_path.with_name(f"{audit_log_path.name}.2")),
            ]
        )

    seen: dict[str, tuple[str, Path]] = {}
    seen_inodes: dict[tuple[int, int], tuple[str, Path]] = {}
    multiply_linked: list[tuple[str, Path]] = []
    for label, path in labeled_paths:
        key = _private_path_key(path)
        previous = seen.get(key)
        if previous is not None:
            previous_label, previous_path = previous
            raise ConfigurationError(
                "Private credential and audit paths must be distinct: "
                f"{previous_label} ({previous_path}) collides with {label} ({path})"
            )
        seen[key] = (label, path)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ConfigurationError(f"Unable to inspect private path {path}") from exc
        if not stat.S_ISREG(metadata.st_mode):
            continue
        inode_key = (metadata.st_dev, metadata.st_ino)
        previous_inode = seen_inodes.get(inode_key)
        if previous_inode is not None:
            previous_label, previous_path = previous_inode
            raise ConfigurationError(
                "Private credential and audit paths must not be hard-link aliases: "
                f"{previous_label} ({previous_path}) and {label} ({path})"
            )
        seen_inodes[inode_key] = (label, path)
        if metadata.st_nlink != 1:
            multiply_linked.append((label, path))
    if multiply_linked:
        label, path = multiply_linked[0]
        raise ConfigurationError(
            f"Private credential or audit file must not have hard links: {label} ({path})"
        )


def prepare_file_session_storage(session_path: Path) -> None:
    """Prepare and harden local Telethon file-session storage."""
    _ensure_private_directory(session_path.parent)
    for path in _telethon_session_files(session_path):
        _harden_private_file(path)


def _load_session_string(path: Path) -> str | None:
    raw = os.getenv("TELEGRAM_SESSION_STRING")
    if raw and raw.strip():
        return raw.strip()

    if not os.path.lexists(path):
        return None
    _ensure_private_directory(path.parent)
    value = _read_private_text_file(
        path, max_bytes=_MAX_SESSION_STRING_FILE_BYTES
    ).strip()
    _harden_private_file(path)
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

        session_path = Path(
            os.getenv("TELEGRAM_SESSION_PATH", ".telegram/codex")
        ).expanduser()

        allow_writes = _as_bool(os.getenv("TELEGRAM_ALLOW_WRITES"))
        write_chat_allowlist = _parse_allowlist(
            os.getenv("TELEGRAM_WRITE_CHAT_ALLOWLIST")
        )
        if allow_writes and not write_chat_allowlist:
            raise ConfigurationError(
                "TELEGRAM_ALLOW_WRITES=true requires a non-empty "
                "TELEGRAM_WRITE_CHAT_ALLOWLIST of comma-separated integer chat IDs."
            )

        audit_raw = os.getenv("TELEGRAM_AUDIT_LOG_PATH", ".telegram/audit.jsonl")
        if audit_raw.strip().lower() in _AUDIT_OFF_VALUES:
            audit_log_path: Path | None = None
        else:
            audit_log_path = Path(audit_raw).expanduser()

        session_string_raw = os.getenv(
            "TELEGRAM_SESSION_STRING_FILE", ".telegram/remote.session.string"
        ).strip()
        session_string_path = Path(
            session_string_raw or ".telegram/remote.session.string"
        ).expanduser()
        _validate_private_path_collisions(
            session_path=session_path,
            session_string_path=session_string_path,
            audit_log_path=audit_log_path,
        )
        session_string = _load_session_string(session_string_path)
        if session_string is None:
            prepare_file_session_storage(session_path)
        if audit_log_path is not None:
            _ensure_private_directory(audit_log_path.parent)
            _harden_private_file(audit_log_path)

        return cls(
            api_id=api_id,
            api_hash=api_hash,
            phone=os.getenv("TELEGRAM_PHONE"),
            session_path=session_path,
            allow_writes=allow_writes,
            write_chat_allowlist=write_chat_allowlist,
            audit_log_path=audit_log_path,
            session_string=session_string,
        )
