# ChatGPT / mobile plugin path

This document tracks the path from the local Codex PoC to a real ChatGPT plugin.

## What exists in v0.2

- A plugin package manifest at `.codex-plugin/plugin.json`.
- A local STDIO MCP entrypoint: `telegram-codex`.
- A remote Streamable HTTP MCP entrypoint: `telegram-codex-remote`.
- The remote MCP endpoint is `/mcp`.
- Read/search tools are marked read-only in MCP metadata.
- Send/edit tools are marked as writes and remain blocked unless `TELEGRAM_ALLOW_WRITES=true`.
- A Dockerfile for deploying the MCP server behind HTTPS.

## Current scope: single-user remote alpha

The current Telegram session model is deliberately single-user. The server reads one Telethon session file from `TELEGRAM_SESSION_PATH`.

That is enough to validate the product UX with one personal Telegram account, but it is **not** the final public-plugin authentication architecture. A public multi-user release must add per-user identity, OAuth for the MCP connection, encrypted per-user Telegram session storage, revocation, and account deletion.

Never put Telegram login codes or 2FA passwords into ChatGPT messages or MCP tool arguments.

## 1. Build and run the remote server

```bash
docker build -t telegram-for-codex .
mkdir -p ./telegram-data

docker run --rm -it \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  telegram-for-codex telegram-codex-auth
```

Authorize the Telegram account in the interactive shell. The resulting session file stays in the mounted volume.

Then run the MCP server:

```bash
docker run --rm \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  -p 8000:8000 \
  telegram-for-codex
```

The endpoint is:

```text
http://localhost:8000/mcp
```

For ChatGPT developer-mode testing, deploy the container behind a stable **public HTTPS** URL, for example:

```text
https://telegram.example.com/mcp
```

Keep `TELEGRAM_ALLOW_WRITES=false` for the first connection test.

## 2. Inspect the MCP endpoint

Use MCP Inspector and connect with Streamable HTTP:

```bash
npx @modelcontextprotocol/inspector@latest
```

Verify these tools are discoverable:

- `telegram_connection_status`
- `telegram_list_chats`
- `telegram_get_messages`
- `telegram_search_messages`
- `telegram_send_message`
- `telegram_edit_message`

First acceptance test: `telegram_connection_status` returns `authorized: true` and `telegram_list_chats` returns real chats.

## 3. Register the MCP server in ChatGPT developer mode

In ChatGPT web:

1. Enable **Developer mode** under Settings → Security and login.
2. Open ChatGPT Plugins.
3. Add a new MCP connection.
4. Use the public HTTPS URL ending in `/mcp`.
5. Review the discovered tools and annotations.
6. Copy the technical connection ID from the browser URL. It starts with `plugin_asdk_app`.

That technical ID cannot be committed in advance because ChatGPT creates it when the MCP connection is registered.

## 4. Wire the registered connection into this plugin package

Once the `plugin_asdk_app...` ID exists, use OpenAI's `@plugin-creator` / `$plugin-creator` flow to generate `.app.json` for this repository and add:

```json
"apps": "./.app.json"
```

to `.codex-plugin/plugin.json`.

The rest of the plugin package is already present: identity, install-surface metadata, skills, and the MCP implementation.

## 5. Test the installed plugin

Target prompts:

```text
Покажи мои непрочитанные чаты Telegram.
```

```text
Что мне написал <name> в Telegram?
```

```text
Найди переписку про <topic>.
```

Only after read/search is proven end-to-end, set:

```dotenv
TELEGRAM_ALLOW_WRITES=true
```

and keep ChatGPT/Codex approval policy enabled for `telegram_send_message` and `telegram_edit_message`.

## 6. Public/mobile path

For a public plugin submission:

- host a stable public HTTPS MCP endpoint;
- add production authentication/authorization;
- add privacy policy and terms URLs;
- add multi-user encrypted Telegram session storage;
- add account disconnect/deletion;
- provide submission test cases and policy attestations;
- submit the MCP-backed plugin through the OpenAI Platform plugin submission flow.

The universal public plugin directory is the distribution path shared by ChatGPT and Codex. Mobile availability is a product-surface capability; do not treat local/private desktop marketplace testing as proof of mobile availability.
