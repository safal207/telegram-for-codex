# Telegram for ChatGPT & Codex

Use Telegram from ChatGPT and Codex through MCP with two deliberately separate products and trust models:

- **Personal Mode** — self-hosted/private **“my Telegram”** access for one power user.
- **Public Mode** — multi-user **AI secretary for explicitly allowed private chats** through Telegram Business delegation.

Public Mode is intentionally **not** described as “Telegram like Gmail”. Telegram Business does not expose arbitrary whole-account history or every chat type. The product promise must follow the API boundary.

## Status

`v0.2 Personal remote alpha + frozen Public foundation`

### Personal Mode

- Local Codex STDIO MCP via `telegram-codex`.
- Remote Streamable HTTP MCP at `/mcp` via `telegram-codex-remote`.
- Phone-first `/connect` authorization; no Termux required for that flow.
- Telethon StringSession secret/file modes.
- Read/search/send/edit tools with `confirm=true`, allowlist and audit controls.
- **Remote caller auth is now fail-closed.** The production path is OAuth 2.1 resource-server auth; a static bearer mode exists only for private curl/MCP Inspector smoke tests.

### Public Mode foundation — intentionally frozen before MCP exposure

The branch contains a separate Telegram Business architecture that does **not** store a personal MTProto session for each public user:

- Telegram Business connection/right models;
- server-side capability enforcement;
- Bot API adapter for connection lookup/send/edit/mark-read/delete;
- business webhook normalization;
- privacy-first `NullBusinessEventStore` default;
- optional tenant-isolated TTL event-store contract;
- one-time hashed Telegram deep-link account binding;
- revocable app-user ↔ Telegram-user ↔ Business-connection registry.

This is a **domain/service scaffold, not a production public service**. Do not expose Public Mode as MCP tools until OAuth, verified webhook ingress, consent, idempotency/replay protection, durable encrypted storage and rate controls exist.

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

## Personal remote caller authentication

Remote `/mcp` has **no unauthenticated mode**.

### Production / ChatGPT path

The MCP server acts as an OAuth 2.1 Resource Server. It validates bearer access tokens issued by an external authorization server using RFC 7662 introspection and publishes RFC 9728 Protected Resource Metadata for client discovery.

Required configuration:

```dotenv
TELEGRAM_MCP_AUTH_MODE=oauth
TELEGRAM_MCP_PUBLIC_URL=https://telegram.example.com/mcp
TELEGRAM_MCP_OAUTH_SCOPES=telegram:personal
TELEGRAM_OAUTH_ISSUER_URL=https://your-auth-provider.example.com/
TELEGRAM_OAUTH_INTROSPECTION_URL=https://your-auth-provider.example.com/oauth2/introspect
TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID=...
TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET=...
```

ChatGPT must authenticate against the configured authorization server; the MCP endpoint itself never issues login tokens.

### Private smoke-test mode

For a trusted tunnel / MCP Inspector / curl test only:

```dotenv
TELEGRAM_MCP_AUTH_MODE=static
TELEGRAM_MCP_PUBLIC_URL=https://telegram.example.com/mcp
TELEGRAM_MCP_STATIC_TOKEN=<32+ random characters>
```

This proves the HTTP bearer gate but is **not** the production ChatGPT auth flow.

## Security rules

- Never commit `.env`, `.env.remote`, `*.session`, `TELEGRAM_SESSION_STRING`, login codes, Telegram 2FA passwords, bot tokens, OAuth secrets or webhook secrets.
- Never pass Telegram login codes, session strings or 2FA passwords through ChatGPT or MCP tool arguments.
- Personal `/connect` must only be exposed over HTTPS and requires a private `TELEGRAM_CONNECT_TOKEN`.
- Host/Origin allowlists are transport-security controls; OAuth bearer validation is caller authentication.
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

Fill in Telegram API credentials from `my.telegram.org`, then authorize a file session:

```bash
telegram-codex-auth
```

Run local MCP:

```bash
telegram-codex
```

## Personal remote alpha — phone-first

For a private single-user server:

1. Put `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in server secrets.
2. Set a long random `TELEGRAM_CONNECT_TOKEN`.
3. Mount `TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string` on a private persistent volume, or use secret-manager `TELEGRAM_SESSION_STRING`.
4. Configure remote caller auth (`oauth` for ChatGPT; `static` only for private smoke tests).
5. Keep `TELEGRAM_ALLOW_WRITES=false` for the first pass.
6. Open on the phone:

```text
https://your-private-domain.example/connect
```

Flow:

```text
private connect key → phone → Telegram code → optional 2FA → Connected
```

The resulting Telegram session secret is never returned to the browser or through MCP.

## Public Mode product boundary

Public Mode is an **AI secretary for selected private chats**, not whole-account Telegram access.

A realistic onboarding contains separate consent steps:

```text
ChatGPT/app OAuth
        ↓
Telegram deep-link identity binding
        ↓
Telegram Business Bot: choose chats + rights
        ↓
Explicit disclosure/consent that selected message content may be sent to OpenAI when the user invokes ChatGPT
        ↓
Connected
```

Public Mode should answer questions such as:

```text
“What did Ivan write after I connected the bot to this chat?”
```

It must not promise:

```text
“Search my entire Telegram history from 2019.”
```

Business access is event-driven and scoped. Broader personal history remains a Personal Mode capability.

Also treat “one connected business bot per Telegram account” as a product constraint, not a footnote: a user may have to choose our secretary instead of another connected Business bot.

## Public Mode data retention

Default:

```text
business update → process current user-directed task → discard message body
```

`NullBusinessEventStore` is the default design.

If a user explicitly enables searchable recent history, use bounded encrypted TTL retention such as 24 hours / 7 days / 30 days. No permanent whole-Telegram mirror, global corpus or whole-history embedding index.

## Acceptance

### Personal PASS-AUTH

- `/mcp` without a bearer token → `401 Unauthorized`.
- RFC 9728 protected-resource metadata is published.
- wrong/expired/inactive/wrong-audience OAuth tokens are rejected.
- static test token works only when explicitly configured.

### Personal PASS-CONNECT

On a phone, complete `/connect`, then call `telegram_whoami`. Expected: `authorized: true`, no session secret and no phone-number PII.

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

## Roadmap

### Personal Mode — active work

- [x] Local STDIO MCP vertical slice.
- [x] Telegram user-session authorization.
- [x] Read/search/send/edit tools.
- [x] `confirm=true`, allowlist, audit trail and MCP safety annotations.
- [x] Remote Streamable HTTP `/mcp` entrypoint.
- [x] Host/Origin transport-security allowlists.
- [x] Mobile `/connect` flow.
- [x] Fail-closed OAuth 2.1 resource-server caller auth + static private smoke-test mode.
- [ ] Configure a real OAuth/OIDC provider with refresh/offline access for ChatGPT.
- [ ] Run PASS-AUTH / PASS-CONNECT / PASS-READ against a real deployment and Telegram account.

### Public Mode — frozen until prerequisites exist

- [x] Product/trust split and Business domain scaffold.
- [x] Rights enforcement, Bot API adapter, webhook normalization, no-store/TTL contracts and revocation model.
- [ ] **Do not add Public MCP tools yet.**
- [ ] Verified Telegram webhook ingress + idempotency/replay protection.
- [ ] Real app OAuth/tenant middleware.
- [ ] Explicit consent ledger including disclosure of transfer to OpenAI for user-directed processing.
- [ ] Encrypted transactional connection/retention storage.
- [ ] Rate limits/flood protection/write audit.
- [ ] Telegram/OpenAI policy + privacy review.
- [ ] Only then expose Public Mode tools and prepare Directory submission.
