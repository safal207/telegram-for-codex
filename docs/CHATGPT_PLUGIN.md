# ChatGPT plugin deployment path

This repository now has the pieces required to move from a local Codex MCP to a real ChatGPT plugin.

## What v0.2 contains

- `.codex-plugin/plugin.json` — OpenAI plugin package manifest.
- `telegram-codex` — local STDIO MCP entrypoint.
- `telegram-codex-remote` — Streamable HTTP MCP entrypoint at `/mcp`.
- MCP read/write safety annotations.
- `confirm=true` guard on write tools from the base PoC.
- Optional write-chat allowlist and JSONL write audit trail.
- Docker deployment scaffold.

## Scope: single-user remote alpha

The current remote mode intentionally reuses one Telethon user session file. This is enough to validate the ChatGPT UX with one personal Telegram account.

It is not the final public multi-user architecture. A public release must add OAuth for the MCP connection, per-user encrypted Telegram session storage, revocation/account deletion, and legal/privacy flows.

Never put Telegram login codes or 2FA passwords into ChatGPT messages or MCP tool arguments.

## 1. Build and authorize the remote container

Create `.env.remote` from `.env.remote.example` and fill in the Telegram API values.

```bash
docker build -t telegram-for-codex .
mkdir -p ./telegram-data

docker run --rm -it \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  telegram-for-codex telegram-codex-auth
```

The Telegram session remains in the mounted volume.

## 2. Run Streamable HTTP MCP

```bash
docker run --rm \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  -p 8000:8000 \
  telegram-for-codex
```

Local MCP endpoint:

```text
http://localhost:8000/mcp
```

For ChatGPT developer-mode testing, deploy the same container behind a stable public HTTPS URL, for example:

```text
https://telegram.example.com/mcp
```

Keep `TELEGRAM_ALLOW_WRITES=false` during the first connection test.

## 3. Inspect the endpoint

Use MCP Inspector with Streamable HTTP:

```bash
npx @modelcontextprotocol/inspector@latest
```

Verify discovery of:

- `telegram_whoami`
- `telegram_audit_log`
- `telegram_list_chats`
- `telegram_get_messages`
- `telegram_search_messages`
- `telegram_send_message`
- `telegram_edit_message`

Read-path acceptance:

1. `telegram_whoami` reports `authorized: true`.
2. `telegram_list_chats` returns real Telegram chats.
3. Search/read work without enabling writes.

## 4. Register the MCP server in ChatGPT developer mode

In ChatGPT web:

1. Enable Developer mode under Settings → Security and login.
2. Open ChatGPT Plugins.
3. Add an MCP connection.
4. Enter the public HTTPS URL ending in `/mcp`.
5. Review discovered tool metadata and safety annotations.
6. Copy the technical connection ID from the browser URL. It starts with `plugin_asdk_app`.

OpenAI creates this ID at registration time, so it cannot be committed in advance.

## 5. Wire the registered MCP connection into the plugin package

Once the `plugin_asdk_app...` ID exists, run the OpenAI `@plugin-creator` / `$plugin-creator` workflow for this repository. It should generate `.app.json` and add this field to `.codex-plugin/plugin.json`:

```json
"apps": "./.app.json"
```

The plugin package identity, skill, server implementation, and install-surface metadata are already present.

## 6. End-to-end prompts

```text
Покажи мои непрочитанные чаты Telegram.
```

```text
Что мне написал <name> в Telegram?
```

```text
Найди переписку про <topic>.
```

Only after read/search passes, set `TELEGRAM_ALLOW_WRITES=true`. Keep product approval enabled and require `confirm=true` for send/edit.

## 7. Public/mobile path

Before public submission:

- stable public HTTPS MCP endpoint;
- production OAuth/authorization;
- encrypted per-user Telegram session storage;
- disconnect/delete-account flow;
- privacy policy and terms URLs;
- submission test cases and policy attestations.

Public plugins are distributed through the universal plugin directory shared by ChatGPT and Codex. Mobile availability is controlled by the supported product surface; local/private desktop marketplace testing is not proof of mobile availability.
