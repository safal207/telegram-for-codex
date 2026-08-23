# Telegram for ChatGPT & Codex

Use your real Telegram **user account** from ChatGPT and Codex through MCP.

The product goal is simple: make Telegram feel like a native source — read chats, search history, send replies, and edit your own messages without leaving the AI conversation.

## Status

`v0.2 remote/plugin alpha`

Two execution modes now share the same Telegram tools:

1. **Local Codex** — STDIO MCP with `telegram-codex`.
2. **ChatGPT plugin path** — Streamable HTTP MCP at `/mcp` with `telegram-codex-remote`, packaged with `.codex-plugin/plugin.json`.

The remote alpha is deliberately **single-user**. It proves the UX and plugin transport before we add production multi-user OAuth and encrypted per-user Telegram session storage.

## Architecture

```text
ChatGPT / Codex
      |
      | MCP tools
      v
telegram-for-codex
      |
      | MTProto (Telethon)
      v
Your Telegram user account
```

Local Codex uses STDIO. Remote ChatGPT testing uses Streamable HTTP over a public HTTPS URL ending in `/mcp`.

## MCP tools

- `telegram_connection_status()` — verify which Telegram account is authorized.
- `telegram_list_chats(limit, unread_only)` — recent chats and unread counts.
- `telegram_get_messages(chat_id, limit)` — recent messages in one chat.
- `telegram_search_messages(query, chat_id?, limit)` — search globally or in one chat.
- `telegram_send_message(chat_id, text)` — send text (**write**).
- `telegram_edit_message(chat_id, message_id, text)` — edit one of your outgoing messages (**write**).

Read tools carry MCP read-only annotations. Send/edit carry write annotations and are additionally blocked by the server unless `TELEGRAM_ALLOW_WRITES=true`.

## Security model

- Never commit `.env`, `.env.remote`, Telegram session files, login codes, or 2FA passwords.
- Reads are enabled by default.
- Writes are disabled by default with `TELEGRAM_ALLOW_WRITES=false`.
- ChatGPT/Codex should still require approval for send/edit after writes are enabled.
- The remote alpha stores one Telegram user session. Do not treat it as a multi-user production service yet.
- Never pass Telegram login codes or 2FA passwords through an AI chat or MCP tool argument.

## Local Codex quickstart

Create Telegram API credentials at `https://my.telegram.org`, then:

```bash
git clone https://github.com/safal207/telegram-for-codex.git
cd telegram-for-codex
git switch feat/chatgpt-plugin-remote
python -m venv .venv
```

Activate the virtualenv and install:

```bash
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=+79990000000
TELEGRAM_SESSION_PATH=.telegram/codex
TELEGRAM_ALLOW_WRITES=false
```

Authorize once:

```bash
telegram-codex-auth
```

Run the local MCP server:

```bash
telegram-codex
```

## Remote ChatGPT plugin quickstart

Copy `.env.remote.example` to `.env.remote`, fill the Telegram API values, and keep writes disabled.

Build the container:

```bash
docker build -t telegram-for-codex .
```

Authorize the single-user Telegram session into a persistent volume:

```bash
mkdir -p ./telegram-data

docker run --rm -it \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  telegram-for-codex telegram-codex-auth
```

Start the remote MCP server:

```bash
docker run --rm \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  -p 8000:8000 \
  telegram-for-codex
```

Local endpoint:

```text
http://localhost:8000/mcp
```

For ChatGPT developer-mode testing, deploy the same container behind a stable **public HTTPS** endpoint such as:

```text
https://your-domain.example/mcp
```

Then register that MCP URL in ChatGPT developer mode. ChatGPT creates a technical connection ID starting with `plugin_asdk_app...`. That generated ID is the one remaining value needed to wire `.app.json` into this plugin package.

See the full flow in [`docs/CHATGPT_PLUGIN.md`](docs/CHATGPT_PLUGIN.md).

## Plugin package

The repository now includes:

```text
.codex-plugin/plugin.json
skills/telegram-for-codex/SKILL.md
src/telegram_codex/server.py
src/telegram_codex/remote_server.py
Dockerfile
```

OpenAI plugin packaging expects `.codex-plugin/plugin.json` as the entry point. Once a remote MCP connection is registered in ChatGPT, the generated `plugin_asdk_app...` ID can be mapped through `.app.json` and referenced by the manifest.

## Acceptance tests

### PASS-READ

With writes disabled:

```text
Покажи последние 10 чатов Telegram.
```

```text
Покажи непрочитанные чаты Telegram.
```

```text
Найди в Telegram сообщения про <topic>.
```

### PASS-WRITE

Only after PASS-READ, enable `TELEGRAM_ALLOW_WRITES=true` and test against Saved Messages or a dedicated safe chat.

Expected:

- send requires product approval;
- edit requires product approval;
- editing another person's incoming message is rejected server-side.

## Why not a Telegram bot?

A bot cannot act as your normal personal Telegram account or automatically access your ordinary private chat history. This project authenticates a Telegram user client instead.

## Roadmap

- [x] Local STDIO MCP vertical slice.
- [x] User-session authorization.
- [x] Read/search/send/edit tools.
- [x] Safety regression tests.
- [x] MCP read/write annotations.
- [x] Remote Streamable HTTP `/mcp` transport.
- [x] `.codex-plugin/plugin.json` package manifest.
- [x] Docker deployment scaffold.
- [ ] Run PASS-READ against a real Telegram account.
- [ ] Deploy a stable HTTPS MCP endpoint.
- [ ] Register the endpoint in ChatGPT developer mode and obtain `plugin_asdk_app...`.
- [ ] Generate `.app.json` and wire it into the plugin manifest.
- [ ] Run end-to-end plugin tests in ChatGPT.
- [ ] Add OAuth + encrypted per-user Telegram sessions for public use.
- [ ] Add privacy/terms/account-deletion flows and submit the plugin for public review.
