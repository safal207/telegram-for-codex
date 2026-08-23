# Telegram for ChatGPT & Codex

Use Telegram from ChatGPT and Codex through MCP with two deliberately separate trust models:

- **Personal Mode** — private/self-hosted user-client access for a power user.
- **Public Mode** — Telegram Business Bot delegation for a scalable multi-user product.

The product goal is to make Telegram feel like another AI source: read the conversations the integration is allowed to see, draft replies, and perform user-approved actions without exposing personal Telegram login credentials to the public service.

## Status

`v0.2 remote/plugin alpha + Public Mode foundation`

### Personal Mode

- Local Codex STDIO MCP via `telegram-codex`.
- Remote Streamable HTTP MCP at `/mcp` via `telegram-codex-remote`.
- Phone-first `/connect` authorization; no Termux required for that flow.
- Telethon StringSession secret/file modes.
- Read/search/send/edit tools with `confirm=true`, allowlist and audit controls.
- **Private/trusted deployment only until MCP caller authentication is added.**

### Public Mode foundation

The branch now also contains a separate Telegram Business architecture that does **not** store a personal MTProto session for each public user:

- Telegram Business connection/right models;
- server-side capability enforcement;
- Bot API adapter for connection lookup/send/edit/mark-read/delete;
- business webhook normalization;
- privacy-first `NullBusinessEventStore` default;
- optional tenant-isolated TTL event-store contract;
- one-time hashed Telegram deep-link account binding;
- revocable app-user ↔ Telegram-user ↔ Business-connection registry.

Public Mode is deliberately **not exposed as MCP tools yet**. MCP exposure waits for real app OAuth/tenant identity so a model can never select another user's `business_connection_id` as an argument.

Architecture:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PUBLIC_MODE.md`](docs/PUBLIC_MODE.md)
- [`docs/CHATGPT_PLUGIN.md`](docs/CHATGPT_PLUGIN.md)

## Personal Mode MCP tools

- `telegram_whoami()` — authorization status and safety configuration; phone number is not returned.
- `telegram_audit_log(limit)` — recent audited write attempts.
- `telegram_list_chats(limit, unread_only)` — recent chats and unread counts.
- `telegram_get_messages(chat_id, limit)` — recent messages in one chat.
- `telegram_search_messages(query, chat_id?, limit)` — search globally or in one chat.
- `telegram_send_message(chat_id, text, confirm)` — send text; requires `confirm=true`.
- `telegram_edit_message(chat_id, message_id, text, confirm)` — edit your outgoing message; requires `confirm=true`.

Read tools carry MCP read-only annotations. Write tools remain disabled unless `TELEGRAM_ALLOW_WRITES=true`, can be restricted by `TELEGRAM_WRITE_CHAT_ALLOWLIST`, and can be written to the JSONL audit trail.

## Security rules

- Never commit `.env`, `.env.remote`, `*.session`, `TELEGRAM_SESSION_STRING`, login codes, Telegram 2FA passwords, bot tokens, OAuth secrets or webhook secrets.
- Never pass Telegram login codes, session strings or 2FA passwords through ChatGPT or MCP tool arguments.
- Personal `/connect` must only be exposed over HTTPS and requires a private `TELEGRAM_CONNECT_TOKEN`.
- Do **not** expose the Personal Mode `/mcp` endpoint directly to the public internet without application authentication.
- `TELEGRAM_MCP_ALLOWED_HOSTS` and `TELEGRAM_MCP_ALLOWED_ORIGINS` are transport-security controls, not caller authentication.
- Keep `TELEGRAM_ALLOW_WRITES=false` until read/search works end-to-end.
- Keep product approval enabled for send/edit even after server-side writes are enabled.
- A Telegram StringSession is a bearer credential. Keep it only in a private trusted deployment.
- Public Mode must derive tenant/user identity from authenticated server-side context; never accept `app_user_id` or `business_connection_id` from the model as authorization authority.

## Personal Mode quickstart

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

Fill in Telegram API credentials from `my.telegram.org` for Personal Mode, then authorize a normal file session once:

```bash
telegram-codex-auth
```

Run local MCP:

```bash
telegram-codex
```

## Personal remote alpha — phone-first

For a private single-user server:

1. Put `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in the server secret/config environment.
2. Set a long random `TELEGRAM_CONNECT_TOKEN`.
3. Set `TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string` and mount `/data/telegram` as a private persistent volume, or use a secret-manager `TELEGRAM_SESSION_STRING`.
4. Keep `TELEGRAM_ALLOW_WRITES=false`.
5. Keep `/mcp` behind a trusted/private boundary until caller auth exists.
6. Open on the phone:

```text
https://your-private-domain.example/connect
```

Flow:

```text
private connect key → phone → Telegram code → optional 2FA → Connected
```

The resulting session secret is never returned to the browser or through MCP.

## Public Mode target onboarding

Public users should not see a terminal, phone OTP form, `api_id`, `api_hash`, or StringSession.

Target flow:

```text
ChatGPT: Connect Telegram
        ↓
OpenAI/app OAuth
        ↓
one-time link
        ↓
https://t.me/<our_bot>?start=link_<token>
        ↓
Telegram identifies the user
        ↓
User enables our Business Bot and chooses chats/rights
        ↓
business_connection update
        ↓
Connected ✓
```

The one-time link token is stored only as a hash, expires, and is single-use. Telegram's Business connection remains the revocable source of permissions.

## Public Mode data retention

Default:

```text
business update → process → discard message body
```

`NullBusinessEventStore` is the default design.

If a user explicitly enables searchable recent history, use a bounded encrypted TTL store such as 24 hours / 7 days / 30 days. Public Mode must not build a permanent whole-Telegram mirror or global embedding index.

Also note a product limitation: Business Bot mode is event-driven and is not intended to promise arbitrary full-history search over every old personal chat. Broader history remains a Personal Mode capability.

## Acceptance

### Personal PASS-CONNECT

On a phone, complete `/connect`, then call `telegram_whoami`. Expected: `authorized: true`, no session secret and no phone-number PII in the response.

### Personal PASS-READ

With writes disabled:

```text
Покажи мои непрочитанные чаты Telegram.
```

```text
Найди в Telegram переписку про <topic>.
```

### Public foundation acceptance

- disabled Business connections deny all write capabilities;
- Telegram-side Business rights gate each action;
- no-store mode retains no message bodies;
- TTL dev store is tenant-isolated;
- one-time Telegram link tokens expire and cannot be reused;
- revocation removes Business connection routing immediately;
- outbound Bot API calls use the server-resolved `business_connection_id`.

## Why not one hosted Telethon cluster?

A hosted personal-user client would require the service to safeguard a long-lived Telegram session credential for every customer. Public Mode instead uses Telegram Business delegation, where Telegram owns connection lifecycle and scoped rights. Personal Mode remains available for private power-user access but is intentionally not the mass-market trust model.

## Roadmap

### Personal Mode

- [x] Local STDIO MCP vertical slice.
- [x] Telegram user-session authorization.
- [x] Read/search/send/edit tools.
- [x] `confirm=true`, allowlist, audit trail and MCP safety annotations.
- [x] Remote Streamable HTTP `/mcp` entrypoint.
- [x] Host/Origin transport-security allowlists.
- [x] Mobile `/connect` flow.
- [ ] Run PASS-CONNECT / PASS-READ on a real Telegram account.
- [ ] Protect remote MCP with real caller authentication/trusted tunnel.

### Public Mode

- [x] Two-mode architecture decision.
- [x] Business connection + rights domain model.
- [x] Telegram Business Bot outbound adapter.
- [x] Business webhook normalization.
- [x] No-store default + TTL store contract.
- [x] One-time hashed Telegram deep-link identity binding.
- [x] Immediate connection revocation model.
- [ ] Create/configure real Telegram business-ready bot / Secretary Mode.
- [ ] Add verified Telegram webhook ingress + idempotency/replay protection.
- [ ] Add OpenAI/app OAuth and tenant identity middleware.
- [ ] Replace in-memory link/connection stores with encrypted transactional storage.
- [ ] Add consent ledger, retention controls and delete/export endpoints.
- [ ] Expose Public Mode MCP tools from authenticated server-side context.
- [ ] Add rate limits/flood protection/write audit.
- [ ] Complete Telegram/OpenAI privacy + policy review.
- [ ] Submit public plugin/app when product surface supports the target distribution.
