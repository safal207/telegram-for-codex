from __future__ import annotations

import argparse
import binascii
import getpass
import os
import re
import shutil
import sqlite3
import stat
import struct
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence, TextIO

from telethon.sessions import StringSession

from .config import (
    ConfigurationError,
    Settings,
    _ensure_private_directory,
    _harden_private_file,
    _parse_user_config,
    _telethon_session_file,
    resolve_user_config_path,
)

_API_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{32}\Z")
_PHONE_PATTERN = re.compile(r"\+[1-9][0-9]{6,14}\Z")


@dataclass(frozen=True, slots=True)
class SetupCredentials:
    api_id: int
    api_hash: str = field(repr=False)
    phone: str


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    status: str
    name: str
    detail: str


def _validated_credentials(api_id: str, api_hash: str, phone: str) -> SetupCredentials:
    try:
        parsed_api_id = int(api_id.strip())
    except ValueError as exc:
        raise ConfigurationError("Telegram API ID must be a positive integer") from exc
    if parsed_api_id <= 0:
        raise ConfigurationError("Telegram API ID must be a positive integer")

    normalized_hash = api_hash.strip()
    if not _API_HASH_PATTERN.fullmatch(normalized_hash):
        raise ConfigurationError("Telegram API hash must be exactly 32 hexadecimal characters")

    normalized_phone = phone.strip()
    if not _PHONE_PATTERN.fullmatch(normalized_phone):
        raise ConfigurationError(
            "Telegram phone must use international format, for example +15551234567"
        )
    return SetupCredentials(parsed_api_id, normalized_hash, normalized_phone)


def collect_setup_credentials(
    *,
    environ: Mapping[str, str],
    non_interactive: bool,
    input_fn: Callable[[str], str],
    secret_input_fn: Callable[[str], str],
) -> SetupCredentials:
    """Collect credentials without ever echoing the API hash."""
    api_id = environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = environ.get("TELEGRAM_API_HASH", "").strip()
    phone = environ.get("TELEGRAM_PHONE", "").strip()

    if non_interactive:
        missing = [
            name
            for name, value in (
                ("TELEGRAM_API_ID", api_id),
                ("TELEGRAM_API_HASH", api_hash),
                ("TELEGRAM_PHONE", phone),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Non-interactive setup requires these environment variables: "
                + ", ".join(missing)
            )
    else:
        if not api_id:
            api_id = input_fn("Telegram API ID: ")
        if not api_hash:
            api_hash = secret_input_fn("Telegram API hash (hidden): ")
        if not phone:
            phone = input_fn("Telegram phone in international format: ")

    return _validated_credentials(api_id, api_hash, phone)


def _secure_secret_input(prompt: str, *, stdin: TextIO) -> str:
    """Read a secret only when getpass can fail closed instead of echoing stdin."""
    if not stdin.isatty():
        raise ConfigurationError(
            "A secure interactive terminal is required for the API hash; "
            "use --non-interactive with TELEGRAM_API_HASH instead"
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass(prompt, stream=None)
    except (EOFError, getpass.GetPassWarning) as exc:
        raise ConfigurationError(
            "Unable to hide API hash input; use --non-interactive with "
            "TELEGRAM_API_HASH instead"
        ) from exc


def _dotenv_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _absolute_private_path(path: Path) -> Path:
    """Make persisted paths independent of whichever cwd launches Codex later."""
    try:
        expanded = os.fspath(path.expanduser())
        if "\0" in expanded:
            raise ValueError("embedded null byte")
        return Path(os.path.abspath(expanded))
    except (OSError, RuntimeError, ValueError) as exc:
        raise ConfigurationError("Unable to resolve private config or data path") from exc


def _render_config(credentials: SetupCredentials, data_directory: Path) -> str:
    session_path = data_directory / "codex"
    session_string_path = data_directory / "remote.session.string"
    audit_path = data_directory / "audit.jsonl"
    values = (
        ("TELEGRAM_API_ID", str(credentials.api_id)),
        ("TELEGRAM_API_HASH", credentials.api_hash),
        ("TELEGRAM_PHONE", credentials.phone),
        ("TELEGRAM_SESSION_PATH", str(session_path)),
        ("TELEGRAM_SESSION_STRING_FILE", str(session_string_path)),
        ("TELEGRAM_ALLOW_WRITES", "false"),
        ("TELEGRAM_AUDIT_LOG_PATH", str(audit_path)),
    )
    lines = [
        "# Generated by telegram-codex-setup.",
        "# Writes stay disabled until explicitly enabled with a non-empty chat allowlist.",
        "# The audit log records metadata only and never message text.",
    ]
    lines.extend(f"{key}={_dotenv_quote(value)}" for key, value in values)
    return "\n".join(lines) + "\n"


def _atomic_write_private(path: Path, content: str, *, overwrite: bool) -> None:
    _ensure_private_directory(path.parent)
    target_exists = os.path.lexists(path)
    if target_exists:
        _harden_private_file(path)
        if not overwrite:
            raise ConfigurationError(
                f"Private config already exists: {path}. Re-run with --force to replace it."
            )

    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        payload = content.encode("utf-8")
        written = 0
        while written < len(payload):
            written += os.write(descriptor, payload[written:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None

        if overwrite:
            if os.path.lexists(path):
                _harden_private_file(path)
            os.replace(temporary_path, path)
            temporary_path = None
        else:
            try:
                # A same-directory hard link atomically publishes the complete file
                # only if the destination is still absent. This preserves both
                # no-clobber and atomic-reader semantics across POSIX and Windows.
                os.link(temporary_path, path, follow_symlinks=False)
            except FileExistsError as exc:
                raise ConfigurationError(
                    f"Private config already exists: {path}. Re-run with --force to replace it."
                ) from exc
            temporary_path.unlink()
            temporary_path = None
        _harden_private_file(path)
    except ConfigurationError:
        raise
    except OSError as exc:
        raise ConfigurationError(f"Unable to write private config {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                # Do not hide the original failure. The leftover stays mode 0600
                # inside the already-validated private directory.
                pass


def write_setup_config(
    config_path: Path,
    credentials: SetupCredentials,
    *,
    overwrite: bool = False,
    data_directory: Path | None = None,
) -> Path:
    """Create private local storage and atomically write the safe first-run config."""
    credentials = _validated_credentials(
        str(credentials.api_id), credentials.api_hash, credentials.phone
    )
    config_path = _absolute_private_path(config_path)
    private_data = (
        _absolute_private_path(data_directory)
        if data_directory is not None
        else config_path.parent / "data"
    )
    _ensure_private_directory(config_path.parent)
    _ensure_private_directory(private_data)
    content = _render_config(credentials, private_data)
    _atomic_write_private(config_path, content, overwrite=overwrite)
    return private_data


def _config_check(
    config_path: Path, *, allow_legacy_fallback: bool = False
) -> DoctorCheck:
    if not os.path.lexists(config_path):
        if allow_legacy_fallback:
            return DoctorCheck(
                "WARN",
                "Config",
                "User config not found; checking the legacy source .env fallback",
            )
        return DoctorCheck("FAIL", "Config", f"Not found: {config_path}")
    try:
        _parse_user_config(config_path)
    except ConfigurationError as exc:
        return DoctorCheck("FAIL", "Config", str(exc))
    return DoctorCheck("PASS", "Config", f"Private config parses: {config_path}")


def _file_session_check(settings: Settings) -> DoctorCheck:
    session_file = _telethon_session_file(settings.session_path)
    if not os.path.lexists(session_file):
        return DoctorCheck(
            "FAIL",
            "Telegram session",
            "Not authorized yet; run telegram-codex-auth when ready",
        )
    try:
        _ensure_private_directory(session_file.parent)
        _harden_private_file(session_file)
        resolved = session_file.resolve(strict=True)
        connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT auth_key FROM sessions WHERE auth_key IS NOT NULL LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except (ConfigurationError, OSError, sqlite3.Error):
        return DoctorCheck(
            "FAIL", "Telegram session", "Session file is unsafe, unreadable, or invalid"
        )
    auth_key = row[0] if row else None
    valid_auth_key = (
        isinstance(auth_key, (bytes, bytearray, memoryview))
        and len(auth_key) == 256
        and any(bytes(auth_key))
    )
    if not valid_auth_key:
        return DoctorCheck(
            "FAIL",
            "Telegram session",
            "Session has no valid authorization key; run telegram-codex-auth",
        )
    return DoctorCheck("PASS", "Telegram session", "Authorization key is present (offline check)")


def _session_check(settings: Settings) -> DoctorCheck:
    if settings.session_string:
        try:
            session = StringSession(settings.session_string)
        except (binascii.Error, TypeError, ValueError, struct.error):
            return DoctorCheck("FAIL", "Telegram session", "Session string is invalid")
        if session.auth_key is None:
            return DoctorCheck("FAIL", "Telegram session", "Session string has no authorization key")
        return DoctorCheck("PASS", "Telegram session", "Authorization key is present (offline check)")
    return _file_session_check(settings)


def run_doctor(
    *,
    config_path: Path,
    environ: Mapping[str, str],
    which_fn: Callable[[str], str | None] = shutil.which,
    version_info: Sequence[int] = sys.version_info,
    allow_legacy_fallback: bool = False,
) -> list[DoctorCheck]:
    """Run deterministic local readiness checks without making a network request."""
    checks: list[DoctorCheck] = []
    version = tuple(version_info[:3])
    if version >= (3, 11, 0):
        checks.append(DoctorCheck("PASS", "Python", ".".join(map(str, version))))
    else:
        checks.append(DoctorCheck("FAIL", "Python", "Python 3.11 or newer is required"))

    launcher = which_fn("telegram-codex")
    checks.append(
        DoctorCheck(
            "PASS" if launcher else "FAIL",
            "Launcher",
            launcher or "telegram-codex is not available on PATH",
        )
    )
    checks.append(
        _config_check(config_path, allow_legacy_fallback=allow_legacy_fallback)
    )

    doctor_environment = dict(environ)
    if os.path.lexists(config_path) or not allow_legacy_fallback:
        doctor_environment["TELEGRAM_CODEX_CONFIG_FILE"] = str(config_path)
    else:
        doctor_environment.pop("TELEGRAM_CODEX_CONFIG_FILE", None)
    settings: Settings | None = None
    try:
        settings = Settings.from_env(environ=doctor_environment)
        if settings.api_id <= 0:
            raise ConfigurationError("Telegram API ID must be a positive integer")
        if not _API_HASH_PATTERN.fullmatch(settings.api_hash.strip()):
            raise ConfigurationError(
                "Telegram API hash must be exactly 32 hexadecimal characters"
            )
        if settings.phone and not _PHONE_PATTERN.fullmatch(settings.phone.strip()):
            raise ConfigurationError(
                "Telegram phone must use international format, for example +15551234567"
            )
    except ConfigurationError as exc:
        checks.append(DoctorCheck("FAIL", "Settings", str(exc)))
    else:
        settings_warning = settings.allow_writes or not settings.phone
        checks.append(
            DoctorCheck(
                "WARN" if settings_warning else "PASS",
                "Settings",
                "Effective settings are valid; writes are explicitly enabled"
                if settings.allow_writes
                else (
                    "Effective settings are valid; writes are disabled; phone is not saved"
                    if not settings.phone
                    else "Effective settings are valid; writes are disabled"
                ),
            )
        )
        checks.append(_session_check(settings))

    codex = which_fn("codex")
    checks.append(
        DoctorCheck(
            "PASS" if codex else "FAIL",
            "Codex CLI",
            codex or "codex is not available on PATH",
        )
    )
    return checks


def setup_main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    input_fn: Callable[[str], str] = input,
    secret_input_fn: Callable[[str], str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(
        prog="telegram-codex-setup",
        description="Create a private Telegram for Codex config without changing Codex itself.",
    )
    parser.add_argument("--config", type=Path, help="Override the private config file path")
    parser.add_argument("--non-interactive", action="store_true", help="Read credentials only from environment variables")
    parser.add_argument("--force", action="store_true", help="Replace an existing regular private config")
    args = parser.parse_args(argv)
    source = dict(os.environ if environ is None else environ)
    try:
        config_path = _absolute_private_path(
            args.config or resolve_user_config_path(environ=source)
        )
        if source.get("TELEGRAM_ALLOW_WRITES", "").strip().casefold() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise ConfigurationError(
                "TELEGRAM_ALLOW_WRITES is enabled in the environment; unset it or "
                "set it to false before running safe setup"
            )
        secret_reader = secret_input_fn or (
            lambda prompt: _secure_secret_input(
                prompt, stdin=sys.stdin if stdin is None else stdin
            )
        )
        credentials = collect_setup_credentials(
            environ=source,
            non_interactive=args.non_interactive,
            input_fn=input_fn,
            secret_input_fn=secret_reader,
        )
        data_directory = write_setup_config(
            config_path, credentials, overwrite=args.force
        )
    except ConfigurationError as exc:
        print(f"Setup failed: {exc}", file=stderr)
        return 1

    print(f"Config created: {config_path}", file=stdout)
    print(f"Private data directory: {data_directory}", file=stdout)
    print("Writes are disabled; audit entries contain metadata only.", file=stdout)
    print("Codex configuration was not changed.", file=stdout)
    print("Next, authorize explicitly with: telegram-codex-auth", file=stdout)
    return 0


def doctor_main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    which_fn: Callable[[str], str | None] = shutil.which,
    version_info: Sequence[int] = sys.version_info,
    stdout: TextIO = sys.stdout,
) -> int:
    parser = argparse.ArgumentParser(
        prog="telegram-codex-doctor",
        description="Check local readiness without contacting Telegram.",
    )
    parser.add_argument("--config", type=Path, help="Override the private config file path")
    args = parser.parse_args(argv)
    source = dict(os.environ if environ is None else environ)
    explicit_config = args.config is not None or bool(
        source.get("TELEGRAM_CODEX_CONFIG_FILE", "").strip()
    )
    try:
        config_path = _absolute_private_path(
            args.config or resolve_user_config_path(environ=source)
        )
    except ConfigurationError as exc:
        print(f"FAIL Config: {exc}", file=stdout)
        return 1
    checks = run_doctor(
        config_path=config_path,
        environ=source,
        which_fn=which_fn,
        version_info=version_info,
        allow_legacy_fallback=not explicit_config,
    )
    for check in checks:
        print(f"{check.status} {check.name}: {check.detail}", file=stdout)
    return 1 if any(check.status == "FAIL" for check in checks) else 0
