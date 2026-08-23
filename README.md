# Telegram for ChatGPT & Codex

Use your real Telegram **user account** from ChatGPT and Codex through MCP.

The goal is to make Telegram feel like another AI source: list chats, read messages, search history, send replies, and edit your own messages without opening Telegram separately.

## Status

`v0.2 remote/plugin alpha`

- **Local Codex:** STDIO MCP via `telegram-codex`.
- **Remote ChatGPT path:** Streamable HTTP MCP at `/mcp` via `telegram-codex-remote`.
- **Mobile authorization:** open `/connect` on a phone; no Termux required.
- **Plugin package:** `.codex-plugin/plugin.json` + bundled Telegram skill.
- **Cloud auth:** Telethon `StringSession` can be loaded from a secret manager or a private session-string file.
- **Current remote scope:** single-user alpha.

A public multi-user plugin still needs OAuth, encrypted per-user Telegram sessions, disconnect/deletion flows, legal pages, and OpenAI submission review.

## MCP tools

- `telegram_whoami()` — authorized user and safety configuration.
- `telegram_audit_log(limit)` — recent audited write attempts.
- `telegram_list_chats(limit, unread_only)` — recent chats and unread counts.
- `telegram_get_messages(chat_id, limit)` — recent messages in one chat.
- `telegram_search_messages(query, chat_id?, limit)` — search globally or in one chat.
- `telegram_send_message(chat_id, text, confirm)` — send text; requires `confirm=true`.
- `telegram_edit_message(chat_id, message_id, text, confirm)` — edit your outgoing message; requires `confirm=true`.

Read tools carry MCP read-only annotations. Write tools are annotated as writes, remain disabled unless `TELEGRAM_ALLOW_WRITES=true`, can be restricted by `TELEGRAM_WRITE_CHAT_ALLOWLIST`, and can be written to the JSONL audit trail.

## Security rules

- Never commit `.env`, `.env.remote`, `*.session`, `TELEGRAM_SESSION_STRING`, login codes, or Telegram 2FA passwords.
- Never pass Telegram login codes, session strings, or 2FA passwords through ChatGPT or MCP tool arguments.
- `/connect` must only be exposed over HTTPS and requires a private `TELEGRAM_CONNECT_TOKEN`.
- Keep `TELEGRAM_ALLOW_WRITES=false` until read/search works end-to-end.
- Keep product approval enabled for send/edit even after server-side writes are enabled.
- A Telegram StringSession is a bearer credential. Keep the session file on a private persistent volume or the value in a hosting secret manager.

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

Fill in your Telegram API credentials from `my.telegram.org`, then authorize a normal file session once:

```bash
telegram-codex-auth
```

Run the local server:

```bash
telegram-codex
```

## Remote ChatGPT plugin quickstart — phone-first

This is the intended single-user alpha flow when you do **not** want Termux or a desktop authorization step.

1. Put `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in the server's secret/config environment.
2. Set a long random `TELEGRAM_CONNECT_TOKEN`.
3. Set `TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string` and mount `/data/telegram` as a **private persistent volume**.
4. Keep `TELEGRAM_ALLOW_WRITES=false`.
5. Deploy the container behind HTTPS.
6. Open this URL on your phone:

```text
https://your-domain.example/connect
```

The page asks for:

```text
private connect key → phone number → Telegram code → 2FA password (only if enabled)
```

The Telegram login code and 2FA password are used only to complete the live Telegram authorization. They are not returned by the API, not written to the session file, and should never be pasted into ChatGPT. After success, the server stores only a Telethon StringSession in `TELEGRAM_SESSION_STRING_FILE` with restrictive file permissions and reloads the MCP Telegram client immediately.

The same remote process exposes:

```text
https://your-domain.example/mcp
```

For ChatGPT developer-mode testing, configure `TELEGRAM_MCP_ALLOWED_HOSTS` for the public hostname and `TELEGRAM_MCP_ALLOWED_ORIGINS` for the supported OpenAI web origins; DNS-rebinding protection stays enabled.

Register the `/mcp` URL in ChatGPT Plugins; ChatGPT creates a technical connection ID beginning with `plugin_asdk_app...`. That ID is then wired into `.app.json` and referenced by the plugin manifest.

## Alternative: stateless secret-manager mode

If the host has no persistent private volume, generate a StringSession separately with:

```bash
telegram-codex-auth-string
```

Store the result only in the hosting secret manager as `TELEGRAM_SESSION_STRING`. This direct secret takes precedence over `TELEGRAM_SESSION_STRING_FILE`.

Full flow: [`docs/CHATGPT_PLUGIN.md`](docs/CHATGPT_PLUGIN.md).

## Acceptance

### PASS-CONNECT

On a phone, open `/connect`, complete Telegram authorization, then call `telegram_whoami`. Expected result: `authorized: true` and no session secret in the response.

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
- [x] Production Host/Origin transport-security allowlists.
- [x] `.codex-plugin/plugin.json` package manifest.
- [x] Docker deployment scaffold.
- [x] Cloud `StringSession` secret mode.
- [x] Mobile `/connect` flow: phone → code → 2FA → private StringSession file.
- [ ] Run PASS-CONNECT against a real Telegram account.
- [ ] Run PASS-READ against a real Telegram account.
- [ ] Deploy a stable HTTPS MCP endpoint.
- [ ] Register the endpoint in ChatGPT developer mode and obtain `plugin_asdk_app...`.
- [ ] Generate `.app.json` and wire it into the plugin manifest.
- [ ] Run end-to-end plugin tests in ChatGPT.
- [ ] Add production OAuth + encrypted per-user Telegram session storage.
- [ ] Add privacy/terms/account-deletion flows and submit for public review.
