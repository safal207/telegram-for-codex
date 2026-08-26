from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

_DEFAULT_DATA_DIR = "/data/telegram"
_DEFAULT_UID = 10001
_DEFAULT_GID = 10001
_AUDIT_OFF_VALUES = {"off", "none", "disabled", "0", "false", ""}


def _numeric_id(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must identify a non-root account")
    return value


def _absolute_path(raw: str, name: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise RuntimeError(f"{name} must be an absolute path in the container")
    return Path(os.path.normpath(str(path)))


def _data_directory(raw: str) -> Path:
    path = _absolute_path(raw, "TELEGRAM_DATA_DIR")
    expected = Path(_DEFAULT_DATA_DIR)
    if path != expected:
        raise RuntimeError(
            f"TELEGRAM_DATA_DIR must be the dedicated container volume {expected}"
        )
    return path


def _configured_private_files(data_dir: Path) -> set[Path]:
    session_string = _absolute_path(
        os.getenv(
            "TELEGRAM_SESSION_STRING_FILE",
            str(data_dir / "session.string"),
        ),
        "TELEGRAM_SESSION_STRING_FILE",
    )
    session_base = _absolute_path(
        os.getenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex")),
        "TELEGRAM_SESSION_PATH",
    )
    session_file = (
        session_base
        if str(session_base).endswith(".session")
        else Path(f"{session_base}.session")
    )
    labeled_files: list[tuple[str, Path]] = [
        ("TELEGRAM_SESSION_STRING_FILE", session_string),
        ("Telethon session database", session_file),
        ("Telethon session journal", Path(f"{session_file}-journal")),
        ("Telethon session shared memory", Path(f"{session_file}-shm")),
        ("Telethon session write-ahead log", Path(f"{session_file}-wal")),
    ]

    audit_raw = os.getenv(
        "TELEGRAM_AUDIT_LOG_PATH", str(data_dir / "audit.jsonl")
    ).strip()
    if audit_raw.lower() not in _AUDIT_OFF_VALUES:
        audit_file = _absolute_path(audit_raw, "TELEGRAM_AUDIT_LOG_PATH")
        labeled_files.extend(
            [
                ("TELEGRAM_AUDIT_LOG_PATH", audit_file),
                ("audit backup 1", audit_file.with_name(f"{audit_file.name}.1")),
                ("audit backup 2", audit_file.with_name(f"{audit_file.name}.2")),
            ]
        )

    seen: dict[Path, str] = {}
    seen_inodes: dict[tuple[int, int], tuple[str, Path]] = {}
    multiply_linked: list[tuple[str, Path]] = []
    for label, path in labeled_files:
        if path.parent != data_dir:
            raise RuntimeError(
                f"Container credential path must be directly inside {data_dir}: {path}"
            )
        previous_label = seen.get(path)
        if previous_label is not None:
            raise RuntimeError(
                "Container credential and audit paths must be distinct: "
                f"{previous_label} collides with {label} at {path}"
            )
        seen[path] = label
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError(f"Unable to inspect container credential path: {path}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                f"Container credential path must be a regular file: {path}"
            )
        inode_key = (metadata.st_dev, metadata.st_ino)
        previous_inode = seen_inodes.get(inode_key)
        if previous_inode is not None:
            previous_label, previous_path = previous_inode
            raise RuntimeError(
                "Container credential and audit paths must not be hard-link aliases: "
                f"{previous_label} ({previous_path}) and {label} ({path})"
            )
        seen_inodes[inode_key] = (label, path)
        if metadata.st_nlink != 1:
            multiply_linked.append((label, path))
    if multiply_linked:
        label, path = multiply_linked[0]
        raise RuntimeError(
            f"Container credential file must not have hard links: {label} ({path})"
        )
    return set(seen)


def _secure_existing_file(path: Path, uid: int, gid: int) -> None:
    if not os.path.lexists(path):
        return
    initial = path.lstat()
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise RuntimeError(f"Container credential path must be a regular file: {path}")
    if initial.st_nlink != 1:
        raise RuntimeError(f"Container credential file must not have hard links: {path}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"Unable to open container credential file: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
        ):
            raise RuntimeError(f"Container credential file changed before securing: {path}")
        if opened.st_nlink != 1:
            raise RuntimeError(f"Container credential file must not have hard links: {path}")
        os.fchown(descriptor, uid, gid)
        os.fchmod(descriptor, 0o600)
        secured = os.fstat(descriptor)
        current = path.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != (secured.st_dev, secured.st_ino)
            or secured.st_nlink != 1
            or secured.st_uid != uid
            or secured.st_gid != gid
            or stat.S_IMODE(secured.st_mode) != 0o600
        ):
            raise RuntimeError(f"Container credential file was not secured: {path}")
    except OSError as exc:
        raise RuntimeError(f"Unable to secure container credential file: {path}") from exc
    finally:
        os.close(descriptor)


def _secure_data_directory(path: Path, uid: int, gid: int) -> None:
    initial = path.lstat()
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISDIR(initial.st_mode):
        raise RuntimeError(f"Container data path must be a real directory: {path}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"Unable to open container data directory: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
        ):
            raise RuntimeError(f"Container data directory changed before securing: {path}")
        os.fchown(descriptor, uid, gid)
        os.fchmod(descriptor, 0o700)
        secured = os.fstat(descriptor)
        current = path.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != (secured.st_dev, secured.st_ino)
            or secured.st_uid != uid
            or secured.st_gid != gid
            or stat.S_IMODE(secured.st_mode) != 0o700
        ):
            raise RuntimeError(f"Container data directory was not secured: {path}")
    except OSError as exc:
        raise RuntimeError(f"Unable to secure container data directory: {path}") from exc
    finally:
        os.close(descriptor)


def _prepare_root_owned_volume(
    data_dir: Path,
    uid: int,
    gid: int,
    private_files: set[Path] | None = None,
) -> None:
    if private_files is None:
        private_files = _configured_private_files(data_dir)
    try:
        data_dir.mkdir(mode=0o700, parents=False, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Unable to prepare container data directory {data_dir}") from exc
    _secure_data_directory(data_dir, uid, gid)
    for path in private_files:
        _secure_existing_file(path, uid, gid)


def _verify_runtime_directory(data_dir: Path) -> None:
    metadata = data_dir.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"Container data path must be a real directory: {data_dir}")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError(f"Container data directory must have mode 0700: {data_dir}")
    if not os.access(data_dir, os.R_OK | os.W_OK | os.X_OK):
        raise RuntimeError(
            f"Container data directory is not writable by the service account: {data_dir}. "
            "For a root-owned Railway volume, set RAILWAY_RUN_UID=0; this bootstrap "
            "will secure the mount and drop privileges before starting MCP."
        )


def main() -> None:
    if os.name != "posix":
        raise RuntimeError("The container entrypoint requires a POSIX runtime")
    data_dir = _data_directory(os.getenv("TELEGRAM_DATA_DIR", _DEFAULT_DATA_DIR))
    uid = _numeric_id("TELEGRAM_SERVICE_UID", _DEFAULT_UID)
    gid = _numeric_id("TELEGRAM_SERVICE_GID", _DEFAULT_GID)
    effective_uid = os.geteuid()
    os.umask(0o077)
    private_files = _configured_private_files(data_dir)

    if effective_uid == 0:
        _prepare_root_owned_volume(data_dir, uid, gid, private_files)
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
    elif effective_uid != uid:
        raise RuntimeError(
            f"Container must start as root for bootstrap or as service UID {uid}, "
            f"not UID {effective_uid}"
        )

    _verify_runtime_directory(data_dir)
    command = sys.argv[1:] or ["telegram-codex-remote"]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise RuntimeError("No container command was provided")
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
