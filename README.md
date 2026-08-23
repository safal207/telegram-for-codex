# Telegram for Codex

Use your real Telegram **user account** from Codex through a small MCP server.

The first goal is deliberately narrow: make Telegram feel like another Codex source — list chats, read messages, search history, send a reply, and edit your own message without opening a separate Telegram UI.

## Status

`v0.1 PoC` — MCP vertical slice. The repository is not yet a published Plugin Directory listing.

## Architecture

```text
Codex / ChatGPT
      |
      | MCP tools
      v
telegram-for-codex
      |
      | MTProto (Telethon)
      v
Your Telegram user account
```

The MCP contract is intentionally independent of the Telegram client library. Telethon is used for the first proof of concept because it is lightweight. A TDLib backend can replace it later without changing the Codex-facing tool names.

## MCP tools

- `telegram_list_chats(limit, unread_only)` — recent chats and unread counts.
- `telegram_get_messages(chat_id, limit)` — recent messages in one chat.
- `telegram_search_messages(query, chat_id?, limit)` — search globally or in one chat.
- `telegram_send_message(chat_id, text)` — send text (**write**).
- `telegram_edit_message(chat_id, message_id, text)` — edit one of your outgoing messages (**write**).

## Security model

- Telegram credentials come only from local environment variables.
- Telegram's local session database is ignored by git.
- Reads are enabled by default.
- Writes are disabled by default with `TELEGRAM_ALLOW_WRITES=false`.
- Even when writes are enabled locally, configure the custom app / Codex action policy so `telegram_send_message` and `telegram_edit_message` require user approval.
- Never commit `.env`, `*.session`, login codes, or Telegram 2FA passwords.

## 1. Create Telegram API credentials

Create an application at `https://my.telegram.org` and obtain `api_id` and `api_hash`.

Telegram documents `api_id`, `api_hash`, local database/session state and interactive user authorization as the normal client authorization flow.

## 2. Install

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
copy .env.example .env
```

Fill in `.env`:

```dotenv
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE=+79990000000
TELEGRAM_SESSION_PATH=.telegram/codex
TELEGRAM_ALLOW_WRITES=false
```

## 3. Authorize the Telegram user account once

```bash
telegram-codex-auth
```

Telegram will ask for the login code and, if enabled on your account, the 2FA password. They are entered directly into the local authorization process and must not be stored in the repository.

## 4. Run the MCP server

```bash
telegram-codex
```

The server uses MCP over stdio.

## 5. Connect it to Codex

Create/import a custom MCP app pointing at this MCP server, then include that app in the Codex plugin/workflow you use. OpenAI's current plugin model separates the plugin package (skills/workflow guidance) from the app that connects Codex to external data/actions.

For the two write tools configure approvals so the exact action remains reviewable:

- `telegram_send_message` → always confirm.
- `telegram_edit_message` → always confirm.

Keep `TELEGRAM_ALLOW_WRITES=false` until the read path works end-to-end.

## First acceptance test

With Telegram selected/available in Codex:

1. Ask: `Покажи последние 10 чатов Telegram.`
2. Pick a returned `chat_id`.
3. Ask: `Покажи последние 10 сообщений из chat_id ...`.
4. Ask Codex to search for a harmless phrase.
5. Only after reads work, enable writes locally and test a message to a safe test chat with approval.

`PASS` for v0.1 means those operations work from Codex without opening the Telegram client.

## Why not a Telegram bot?

A bot cannot act as your normal personal Telegram account or automatically access your ordinary private chat history. This project authenticates a Telegram user client instead.

## Roadmap

- [x] MCP tool contract.
- [x] Local user-session authorization command.
- [x] Read/search tools.
- [x] Guarded send/edit tools.
- [ ] Run the PoC against a real Telegram account.
- [ ] Add MCP integration tests with a mocked Telegram gateway.
- [ ] Package/import the app and skill as a first-class Codex plugin.
- [ ] Evaluate TDLib backend after the UX contract is proven.
