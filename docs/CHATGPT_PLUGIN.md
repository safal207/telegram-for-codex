# ChatGPT plugin deployment path

This repository contains the pieces required to move from a local Codex MCP to a real ChatGPT plugin, but the remote alpha must stay behind an authentication boundary until OAuth (or another client-compatible protection layer) is in place.

## What v0.2 contains

- `.codex-plugin/plugin.json` — OpenAI plugin package manifest.
- `telegram-codex` — local STDIO MCP entrypoint.
- `telegram-codex-remote` — Streamable HTTP MCP entrypoint at `/mcp`.
- `/connect` — phone-first Telegram authorization page.
- `telegram-codex-auth-string` — fallback command that generates a cloud Telethon StringSession secret.
- MCP read/write safety annotations.
- `confirm=true` guard on write tools from the base PoC.
- Optional write-chat allowlist and JSONL write audit trail.
- DNS-rebinding protection with explicit Host/Origin allowlists.
- Docker deployment scaffold with `/data/telegram` declared as a volume.

## Security blocker before public deployment

`/connect` is protected by `TELEGRAM_CONNECT_TOKEN`; `/mcp` currently is **not an authenticated application endpoint**.

Do **not** treat either of these as authentication:

```dotenv
TELEGRAM_MCP_ALLOWED_HOSTS=...
TELEGRAM_MCP_ALLOWED_ORIGINS=...
```

They are transport-security allowlists. A non-browser caller can omit `Origin`, and a caller can send the expected Host header. Therefore an unauthenticated public `/mcp` would expose Telegram read tools to anyone who can reach the URL.

For development, keep the MCP server behind a trusted private boundary or OpenAI's Secure MCP Tunnel. For a ChatGPT custom app that must be reachable remotely, configure an authentication mechanism the ChatGPT app flow supports. OpenAI documents OAuth for authenticated custom MCP apps; production OAuth should issue refresh tokens/offline access so connectivity survives access-token expiry.

## Scope: single-user remote alpha

The phone-first flow stores one Telethon `StringSession` in `TELEGRAM_SESSION_STRING_FILE`, typically:

```text
/data/telegram/session.string
```

That path must be backed by a **real private persistent volume** if the container can restart. The Dockerfile's `VOLUME` declaration documents the path; your hosting platform still needs to provision and mount durable storage.

Alternatively, a stateless host can load one StringSession from `TELEGRAM_SESSION_STRING` in its secret manager.

This is not the final public multi-user architecture. A public release needs OAuth for MCP access, per-user encrypted Telegram session storage, revocation/account deletion, and legal/privacy flows.

Never put Telegram login codes, session strings, or 2FA passwords into ChatGPT messages or MCP tool arguments.

## 1. Phone-first Telegram authorization

Configure the server with:

```dotenv
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELEGRAM_CONNECT_TOKEN=<long-random-private-key>
TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string
TELEGRAM_ALLOW_WRITES=false
```

Deploy behind HTTPS while keeping `/mcp` behind a trusted/authenticated boundary. Then open on the phone:

```text
https://your-domain.example/connect
```

The page performs:

```text
connect key → phone → Telegram code → optional 2FA → connected
```

The login code and 2FA password are used only for the live authorization request. The response contains account id/username/name only; the resulting StringSession is persisted server-side with restrictive file permissions and never returned to the browser.

If `TELEGRAM_CONNECT_TOKEN` is missing, all three authorization actions (`/connect/start`, `/connect/code`, `/connect/password`) fail closed with HTTP 401.

## 2. Alternative: generate a session secret outside the server

For a stateless secret-manager deployment, install the project locally and run:

```bash
telegram-codex-auth-string
```

Treat the resulting value like a password/bearer credential. Store it only in the hosting secret manager as `TELEGRAM_SESSION_STRING`. Never commit it and never paste it into ChatGPT.

## 3. Build and run Streamable HTTP MCP

Create `.env.remote` from `.env.remote.example` for non-secret settings and build:

```bash
docker build -t telegram-for-codex .
```

For trusted local/private testing:

```bash
docker run --rm \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  -p 8000:8000 \
  telegram-for-codex
```

Local endpoints:

```text
http://localhost:8000/connect
http://localhost:8000/mcp
```

The server uses FastMCP Streamable HTTP at `/mcp` and keeps DNS-rebinding protection enabled.

For a remote hostname such as:

```text
https://telegram.example.com
```

set the transport allowlists too:

```dotenv
TELEGRAM_MCP_ALLOWED_HOSTS=telegram.example.com,telegram.example.com:*
TELEGRAM_MCP_ALLOWED_ORIGINS=https://chatgpt.com,https://chat.openai.com
```

These settings remain necessary, but they do **not** replace authentication.

Keep `TELEGRAM_ALLOW_WRITES=false` during the first connection test. On stateless hosts, use `TELEGRAM_AUDIT_LOG_PATH=off` unless you have a durable log sink or private persistent volume.

## 4. Inspect the endpoint

Use MCP Inspector from a trusted environment:

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

1. `telegram_whoami` reports `authorized: true` and intentionally omits the phone number.
2. No session secret appears in MCP responses.
3. `telegram_list_chats` returns real Telegram chats.
4. Search/read work without enabling writes.

## 5. Register in ChatGPT developer mode — only after MCP auth exists

Do **not** register a bare public `/mcp` URL from this alpha.

After the endpoint has client-compatible authentication:

1. In ChatGPT web, enable Developer mode for an eligible workspace/account.
2. Create a custom MCP app.
3. Provide the HTTPS `/mcp` endpoint and choose the authentication mechanism.
4. If using OAuth, complete the authorization prompt and verify refresh-token/offline access support.
5. Scan tools and review the read/write safety annotations.
6. Create the draft app and test it from a new ChatGPT conversation.

OpenAI's current custom MCP-app surface is web-only; mobile ChatGPT does not currently run custom MCP apps. The `/connect` authorization page itself is mobile-friendly and can still be opened from a phone browser.

## 6. End-to-end prompts after authenticated registration

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

## 7. Public release path

Before public submission:

- stable authenticated HTTPS MCP endpoint;
- production OAuth/authorization;
- encrypted per-user Telegram session storage;
- disconnect/delete-account flow;
- privacy policy and terms URLs;
- submission test cases and policy attestations.

The current phone-first alpha is suitable for private testing once the MCP network/auth boundary is in place; it is not yet safe to expose as an unauthenticated public service.
