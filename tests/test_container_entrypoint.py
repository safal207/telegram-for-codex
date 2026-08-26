from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from telegram_codex import container_entrypoint


@pytest.mark.skipif(os.name != "posix", reason="POSIX container paths only")
@pytest.mark.parametrize(
    "unsafe_path", ["/", "/data", "/etc/ssl", "/usr/local", "/tmp/foo"]
)
def test_data_directory_rejects_every_path_except_dedicated_volume(
    unsafe_path: str,
) -> None:
    with pytest.raises(RuntimeError, match="dedicated container volume"):
        container_entrypoint._data_directory(unsafe_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX container paths only")
def test_data_directory_accepts_only_dedicated_volume() -> None:
    assert container_entrypoint._data_directory("/data/telegram") == Path(
        "/data/telegram"
    )


def test_configured_private_files_must_stay_in_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(tmp_path / "outside"))

    with pytest.raises(RuntimeError, match="directly inside"):
        container_entrypoint._configured_private_files(data_dir)


@pytest.mark.parametrize("collision", ["active-audit", "audit-backup"])
def test_configured_private_files_reject_path_collisions(
    collision: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    audit_path = data_dir / "audit.jsonl"
    session_string_path = (
        audit_path
        if collision == "active-audit"
        else audit_path.with_name("audit.jsonl.1")
    )
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_string_path))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex"))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", str(audit_path))

    with pytest.raises(RuntimeError, match="paths must be distinct"):
        container_entrypoint._configured_private_files(data_dir)


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links are unavailable")
def test_configured_private_files_reject_hardlink_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    data_dir.mkdir()
    session_string = data_dir / "session.string"
    session_string.write_text("credential", encoding="utf-8")
    audit_path = data_dir / "audit.jsonl"
    os.link(session_string, audit_path)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_string))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex"))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", str(audit_path))

    with pytest.raises(RuntimeError, match="hard-link aliases"):
        container_entrypoint._configured_private_files(data_dir)


@pytest.mark.skipif(not hasattr(os, "link"), reason="hard links are unavailable")
def test_configured_private_files_reject_unconfigured_hardlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    data_dir.mkdir()
    session_string = data_dir / "session.string"
    session_string.write_text("credential", encoding="utf-8")
    os.link(session_string, data_dir / "unconfigured-backup")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_string))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex"))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")

    with pytest.raises(RuntimeError, match="must not have hard links"):
        container_entrypoint._configured_private_files(data_dir)


def test_configured_private_files_reject_existing_symlink_before_uid_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    data_dir.mkdir()
    target = data_dir / "target"
    target.write_text("credential", encoding="utf-8")
    session_link = data_dir / "session.string"
    try:
        session_link.symlink_to(target)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are unavailable")
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_link))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex"))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")

    with pytest.raises(RuntimeError, match="regular file"):
        container_entrypoint._configured_private_files(data_dir)


def test_main_validates_private_paths_before_nonroot_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    exec_called = False

    def reject_private_paths(path: Path) -> set[Path]:
        assert path == data_dir
        raise RuntimeError("credential path must be directly inside data directory")

    def unexpected_exec(*args) -> None:
        nonlocal exec_called
        exec_called = True

    monkeypatch.setattr(container_entrypoint.os, "name", "posix")
    monkeypatch.setattr(
        container_entrypoint.os, "geteuid", lambda: 10001, raising=False
    )
    monkeypatch.setattr(container_entrypoint, "_data_directory", lambda raw: data_dir)
    monkeypatch.setattr(
        container_entrypoint, "_configured_private_files", reject_private_paths
    )
    monkeypatch.setattr(container_entrypoint.os, "execvp", unexpected_exec)

    with pytest.raises(RuntimeError, match="directly inside"):
        container_entrypoint.main()

    assert exec_called is False


def test_root_bootstrap_uses_prevalidated_private_file_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    private_files = {data_dir / "session.string", data_dir / "codex.session"}
    secured: list[Path] = []

    def unexpected_revalidation(path: Path) -> set[Path]:
        raise AssertionError("root bootstrap re-read mutable environment configuration")

    monkeypatch.setattr(
        container_entrypoint, "_configured_private_files", unexpected_revalidation
    )
    monkeypatch.setattr(
        container_entrypoint, "_secure_data_directory", lambda *args: None
    )
    monkeypatch.setattr(
        container_entrypoint,
        "_secure_existing_file",
        lambda path, uid, gid: secured.append(path),
    )

    container_entrypoint._prepare_root_owned_volume(
        data_dir, uid=10001, gid=10001, private_files=private_files
    )

    assert set(secured) == private_files


@pytest.mark.skipif(os.name != "posix", reason="POSIX container permissions only")
def test_prepare_root_owned_volume_secures_known_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    data_dir.mkdir(mode=0o755)
    session_file = data_dir / "session.string"
    session_file.write_text("secret", encoding="utf-8")
    session_file.chmod(0o644)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_file))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex"))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", str(data_dir / "audit.jsonl"))

    container_entrypoint._prepare_root_owned_volume(
        data_dir, os.getuid(), os.getgid()
    )

    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(session_file.stat().st_mode) == 0o600
    container_entrypoint._verify_runtime_directory(data_dir)


@pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "symlink"),
    reason="POSIX symlink behavior only",
)
def test_prepare_root_owned_volume_rejects_credential_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "telegram"
    data_dir.mkdir(mode=0o700)
    target = data_dir / "real-session"
    target.write_text("secret", encoding="utf-8")
    session_link = data_dir / "session.string"
    session_link.symlink_to(target)
    monkeypatch.setenv("TELEGRAM_SESSION_STRING_FILE", str(session_link))
    monkeypatch.setenv("TELEGRAM_SESSION_PATH", str(data_dir / "codex"))
    monkeypatch.setenv("TELEGRAM_AUDIT_LOG_PATH", "off")

    with pytest.raises(RuntimeError, match="regular file"):
        container_entrypoint._prepare_root_owned_volume(
            data_dir, os.getuid(), os.getgid()
        )
