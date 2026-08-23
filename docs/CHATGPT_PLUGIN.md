# ChatGPT plugin deployment path

This repository now has the pieces required to move from a local Codex MCP to a real ChatGPT plugin.

## What v0.2 contains

- `.codex-plugin/plugin.json` — OpenAI plugin package manifest.
- `telegram-codex` — local STDIO MCP entrypoint.
- `telegram-codex-remote` — Streamable HTTP MCP entrypoint at `/mcp`.
- `telegram-codex-auth-string` — local command that generates a cloud Telethon StringSession secret.
- MCP read/write safety annotations.
- `confirm=true` guard on write tools from the base PoC.
- Optional write-chat allowlist and JSONL write audit trail.
- DNS-rebinding protection with explicit Host/Origin allowlists.
- Docker deployment scaffold.

## Scope: single-user remote alpha

The remote alpha can load one Telethon `StringSession` from `TELEGRAM_SESSION_STRING`. This lets a stateless/container host validate the ChatGPT UX without requiring a persistent disk.

A file-based session at `TELEGRAM_SESSION_PATH` remains supported when a private persistent volume is available.

This is not the final public multi-user architecture. A public release must add OAuth for the MCP connection, per-user encrypted Telegram session storage, revocation/account deletion, and legal/privacy flows.

Never put Telegram login codes, session strings, or 2FA passwords into ChatGPT messages or MCP tool arguments.

## 1. Generate the remote session secret locally

Install the project locally and set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE`. Then run:

```bash
telegram-codex-auth-string
```

Telegram will ask for the login code and, when enabled, the account 2FA password **in the local terminal**. The command then prints one Telethon StringSession value.

Treat that value like a password/bearer credential: copy it directly to the hosting platform's secret manager as `TELEGRAM_SESSION_STRING`. Never commit it and never paste it into ChatGPT.

## 2. Build and run Streamable HTTP MCP

Create `.env.remote` from `.env.remote.example` for non-secret settings and build:

```bash
docker build -t telegram-for-codex .
```

For local HTTP testing you may inject `TELEGRAM_SESSION_STRING` from your local secret store/environment and run:

```bash
docker run --rm \
  --env-file .env.remote \
  -p 8000:8000 \
  telegram-for-codex
```

Local MCP endpoint:

```text
http://localhost:8000/mcp
```

The server uses the current FastMCP Streamable HTTP option `streamable_http_path="/mcp"` and keeps DNS-rebinding protection enabled.

For a public deployment such as:

```text
https://telegram.example.com/mcp
```

set at least:

```dotenv
TELEGRAM_MCP_ALLOWED_HOSTS=telegram.example.com,telegram.example.com:*
TELEGRAM_MCP_ALLOWED_ORIGINS=https://chatgpt.com,https://chat.openai.com
```

Use the actual public hostname and the actual OpenAI browser origins observed for the supported product surface. Do not simply disable transport security to make a 421/403 disappear.

Keep `TELEGRAM_ALLOW_WRITES=false` during the first connection test. On stateless hosts, use `TELEGRAM_AUDIT_LOG_PATH=off` unless you have a durable log sink or persistent private volume.

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

1. `telegram_whoami` reports `authorized: true` and `session_mode: string` for the cloud-secret path.
2. `telegram_list_chats` returns real Telegram chats.
3. Search/read work without enabling writes.

If the deployed server returns HTTP 421, verify `TELEGRAM_MCP_ALLOWED_HOSTS`. If a browser receives HTTP 403, verify `TELEGRAM_MCP_ALLOWED_ORIGINS`.

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
