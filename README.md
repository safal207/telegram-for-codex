# Telegram for ChatGPT & Codex

Use your real Telegram **user account** from ChatGPT and Codex through MCP.

The goal is to make Telegram feel like another AI source: list chats, read messages, search history, send replies, and edit your own messages without opening Telegram separately.

## Status

`v0.2 remote/plugin alpha`

- **Local Codex:** STDIO MCP via `telegram-codex`.
- **Remote ChatGPT path:** Streamable HTTP MCP at `/mcp` via `telegram-codex-remote`.
- **Plugin package:** `.codex-plugin/plugin.json` + bundled Telegram skill.
- **Current remote scope:** single-user alpha using one persistent Telethon session.

A public multi-user plugin still needs OAuth, encrypted per-user Telegram sessions, disconnect/deletion flows, legal pages, and OpenAI submission review.

## MCP tools

- `telegram_whoami()` — authorized user and safety configuration.
- `telegram_audit_log(limit)` — recent audited write attempts.
- `telegram_list_chats(limit, unread_only)` — recent chats and unread counts.
- `telegram_get_messages(chat_id, limit)` — recent messages in one chat.
- `telegram_search_messages(query, chat_id?, limit)` — search globally or in one chat.
- `telegram_send_message(chat_id, text, confirm)` — send text; requires `confirm=true`.
- `telegram_edit_message(chat_id, message_id, text, confirm)` — edit your outgoing message; requires `confirm=true`.

Read tools carry MCP read-only annotations. Write tools are annotated as writes, remain disabled unless `TELEGRAM_ALLOW_WRITES=true`, can be restricted by `TELEGRAM_WRITE_CHAT_ALLOWLIST`, and are written to the JSONL audit trail.

## Security rules

- Never commit `.env`, `.env.remote`, `*.session`, login codes, or Telegram 2FA passwords.
- Never pass Telegram login codes or 2FA passwords through ChatGPT or MCP tool arguments.
- Keep `TELEGRAM_ALLOW_WRITES=false` until read/search works end-to-end.
- Keep product approval enabled for send/edit even after server-side writes are enabled.
- For remote mode, persist the Telegram session on an encrypted/private volume.

## Local Codex quickstart

```bash
git clone https://github.com/safal207/telegram-for-codex.git
cd telegram-for-codex
git switch feat/chatgpt-plugin-remote-v2
python -m venv .venv
```

Activate the virtual environment, then:

```bash
python -m pip install -e ".[dev]"
cp .env.example .env   # Windows PowerShell: Copy-Item .env.example .env
```

Fill in your Telegram API credentials from `my.telegram.org`, then authorize once:

```bash
telegram-codex-auth
```

Run the local server:

```bash
telegram-codex
```

## Remote ChatGPT plugin quickstart

Create `.env.remote` from `.env.remote.example`, then:

```bash
docker build -t telegram-for-codex .
mkdir -p ./telegram-data

docker run --rm -it \
  --env-file .env.remote \
  -v "$PWD/telegram-data:/data/telegram" \
  telegram-for-codex telegram-codex-auth
```

Start the Streamable HTTP server:

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

For ChatGPT developer-mode testing, deploy that container behind a stable **public HTTPS** URL ending in `/mcp`. Register the URL in ChatGPT Plugins; ChatGPT will create a technical connection ID beginning with `plugin_asdk_app...`. That ID is then wired into `.app.json` and referenced by this plugin manifest.

Full flow: [`docs/CHATGPT_PLUGIN.md`](docs/CHATGPT_PLUGIN.md).

## Acceptance

### PASS-READ

With writes disabled:

```text
Покажи мои непрочитанные чаты Telegram.
```

```text
Найди в Telegram переписку про <topic>.
```

### PASS-WRITE

Only after PASS-READ, enable writes and test against Saved Messages or a dedicated safe chat. Send/edit must still require product approval plus `confirm=true`.

## Why not a Telegram bot?

A bot cannot act as your normal personal Telegram account or automatically access your ordinary private chat history. This project authenticates a Telegram user client instead.

## Roadmap

- [x] Local STDIO MCP vertical slice.
- [x] Telegram user-session authorization.
- [x] Read/search/send/edit tools.
- [x] `confirm=true`, allowlist, audit trail, and MCP safety annotations.
- [x] Remote Streamable HTTP `/mcp` entrypoint.
- [x] `.codex-plugin/plugin.json` package manifest.
- [x] Docker deployment scaffold.
- [ ] Run PASS-READ against a real Telegram account.
- [ ] Deploy a stable HTTPS MCP endpoint.
- [ ] Register the endpoint in ChatGPT developer mode and obtain `plugin_asdk_app...`.
- [ ] Generate `.app.json` and wire it into the plugin manifest.
- [ ] Run end-to-end plugin tests in ChatGPT.
- [ ] Add OAuth + encrypted per-user Telegram session storage.
- [ ] Add privacy/terms/account-deletion flows and submit for public review.
