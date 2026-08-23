# Telegram for Codex

Use your real Telegram **user account** from Codex through a small local MCP server.

The first goal is deliberately narrow: make Telegram feel like another Codex source — list chats, read messages, search history, send a reply, and edit your own message without opening a separate Telegram UI.

## Status

`v0.1 PoC` — local Codex MCP vertical slice. The repository is not yet a published Plugin Directory listing, but Codex desktop, CLI, and IDE can connect to it directly as a local STDIO MCP server.

## Architecture

```text
Codex desktop / CLI / IDE
      |
      | local MCP over stdio
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

- Telegram credentials come only from local environment variables / local `.env`.
- Telegram's local session database is ignored by git.
- Reads are enabled by default.
- Writes are disabled by default with `TELEGRAM_ALLOW_WRITES=false`.
- Codex is configured to prompt before `telegram_send_message` and `telegram_edit_message`.
- Never commit `.env`, `*.session`, login codes, or Telegram 2FA passwords.

## 1. Create Telegram API credentials

Create an application at `https://my.telegram.org` and obtain `api_id` and `api_hash`.

## 2. Install

### Windows PowerShell

```powershell
git clone https://github.com/safal207/telegram-for-codex.git
cd telegram-for-codex
git switch feat/mcp-poc

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

### macOS / Linux

```bash
git clone https://github.com/safal207/telegram-for-codex.git
cd telegram-for-codex
git switch feat/mcp-poc

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Fill in the local `.env`:

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

Telegram will ask for the login code and, if enabled on your account, the 2FA password. They are entered directly into the local authorization process. Do not paste them into Codex or commit them to the repository.

## 4. Connect it directly to Codex

Codex desktop, Codex CLI, and the IDE extension share MCP configuration. The default config file is:

```text
~/.codex/config.toml
```

You can also use a project-local `.codex/config.toml` in a trusted project.

### Windows example

Use the **absolute paths on your machine**:

```toml
[mcp_servers.telegram]
command = "C:\\Users\\YOUR_USER\\path\\telegram-for-codex\\.venv\\Scripts\\python.exe"
args = ["-m", "telegram_codex.server"]
cwd = "C:\\Users\\YOUR_USER\\path\\telegram-for-codex"
enabled = true
startup_timeout_sec = 20
tool_timeout_sec = 60
default_tools_approval_mode = "auto"

[mcp_servers.telegram.tools.telegram_send_message]
approval_mode = "prompt"

[mcp_servers.telegram.tools.telegram_edit_message]
approval_mode = "prompt"
```

### macOS / Linux example

```toml
[mcp_servers.telegram]
command = "/absolute/path/telegram-for-codex/.venv/bin/python"
args = ["-m", "telegram_codex.server"]
cwd = "/absolute/path/telegram-for-codex"
enabled = true
startup_timeout_sec = 20
tool_timeout_sec = 60
default_tools_approval_mode = "auto"

[mcp_servers.telegram.tools.telegram_send_message]
approval_mode = "prompt"

[mcp_servers.telegram.tools.telegram_edit_message]
approval_mode = "prompt"
```

Restart Codex after editing the configuration.

You can then verify the connection:

```text
/mcp
```

In Codex CLI you can also run:

```bash
codex mcp list
```

Codex also supports adding STDIO servers with `codex mcp add`, but the explicit `config.toml` setup above is recommended for this PoC because it lets us keep per-tool write approvals visible and reviewable.

## 5. First acceptance test: read-only

Keep:

```dotenv
TELEGRAM_ALLOW_WRITES=false
```

Then ask Codex:

1. `Покажи последние 10 чатов Telegram.`
2. Pick a returned `chat_id`.
3. `Покажи последние 10 сообщений из chat_id ...`.
4. `Найди в Telegram сообщения про <harmless phrase>.`

`PASS-READ` means these operations work from Codex without opening Telegram separately.

## 6. Enable writes only after read passes

Change the local `.env`:

```dotenv
TELEGRAM_ALLOW_WRITES=true
```

Restart Codex/MCP, then test only against a safe chat (for example Saved Messages or a dedicated test chat).

Expected behavior:

- `telegram_send_message` → Codex prompts for approval.
- `telegram_edit_message` → Codex prompts for approval.
- editing an incoming/other person's message → rejected by the MCP server.

`PASS-WRITE` means send and edit work only after explicit approval.

## Why not a Telegram bot?

A bot cannot act as your normal personal Telegram account or automatically access your ordinary private chat history. This project authenticates a Telegram user client instead.

## Roadmap

- [x] MCP tool contract.
- [x] Local user-session authorization command.
- [x] Read/search tools.
- [x] Guarded send/edit tools.
- [x] Safety regression tests for disabled writes and edit ownership.
- [x] Exact local Codex MCP configuration and per-tool approvals.
- [ ] Run `PASS-READ` against a real Telegram account.
- [ ] Run `PASS-WRITE` against a safe test chat.
- [ ] Add broader mocked gateway/MCP integration tests.
- [ ] Package the MCP + skill as a first-class installable Codex plugin.
- [ ] Evaluate TDLib backend after the UX contract is proven.
