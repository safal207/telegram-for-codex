# Disconnect and uninstall

Removing the Codex plugin does not revoke the Telegram user session by itself.
Use all applicable steps below.

## 1. Stop and remove the plugin

Close active tasks using Telegram, then run:

```text
codex plugin remove telegram-for-codex@telegram-for-codex
codex plugin marketplace remove telegram-for-codex
```

Restart the ChatGPT desktop app/Codex host and verify that the Telegram tools no
longer appear.

## 2. Revoke Telegram access

In Telegram, open the active-device/session settings, find the session created
for this integration, and terminate it. This invalidates the local Telethon
session even if a copy of the file remains.

For a self-hosted remote deployment, also revoke or rotate the OAuth client,
connect token, static smoke-test token, and any deployed session string.

## 3. Inspect and remove local data

The default directory is `~/.telegram-codex/`. Inspect it before deletion. It
may contain `config.env`, the Telegram session database and sidecars, and the
metadata-only audit log with `.1`/`.2` backups.

If `TELEGRAM_CODEX_CONFIG_FILE`, `TELEGRAM_SESSION_PATH`,
`TELEGRAM_SESSION_STRING_FILE`, or `TELEGRAM_AUDIT_LOG_PATH` was customized,
inspect those exact locations as well. Delete only the confirmed integration
files; do not recursively delete a broad home, profile, or workspace path.

## 4. Remove the Python launcher (optional)

If you installed the recommended isolated runtime with `pipx`, remove it after
revoking the session and inspecting the data:

```text
pipx uninstall telegram-for-codex
```

For a development virtual environment, remove only that confirmed environment
or uninstall the editable package with its own package manager. Do not delete a
shared Python environment.

## 5. Verify

Before removing the Python launcher, `telegram-codex-doctor` should report that
configuration/session setup is absent. After the complete removal, the
`telegram-codex*` launchers should no longer be on PATH, Telegram should no
longer list the integration session, and a new Codex task should have no
`telegram_*` tools.
