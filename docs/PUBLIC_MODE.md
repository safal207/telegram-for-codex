# Public Mode — seamless multi-user design

Public Mode is the mass-market path for Telegram for ChatGPT & Codex. It uses Telegram's official Business Bot delegation instead of logging each customer in as a personal MTProto client.

Official references:

- https://core.telegram.org/api/bots/connected-business-bots
- https://core.telegram.org/bots/features
- https://core.telegram.org/bots/api

## User experience target

```text
ChatGPT: Connect Telegram
        |
        | OpenAI app OAuth establishes app_user_id
        v
Generate one-time link token (10 min, one use)
        |
        | store SHA-256 only
        v
Open https://t.me/<our_bot>?start=link_<token>
        |
        | Telegram itself identifies the user
        v
/start link_<token>
        |
        | bind app_user_id <-> telegram_user_id
        v
User enables our Telegram Business Bot
and chooses recipients + rights in Telegram
        |
        v
business_connection update
        |
        | business_connection_id + current rights
        v
Connected ✓
```

Public users never enter or copy:

- Telegram phone numbers into our web app;
- Telegram OTP/login codes;
- Telegram 2FA passwords;
- Telegram `api_id` / `api_hash`;
- MTProto or Telethon StringSession values.

The Telegram bot deep-link `start` parameter is explicitly suitable for passing an authentication token that connects a Telegram identity to an account on another platform. Our token is random, short-lived, one-use, and stored only as a hash.

## Identity and connection state

There are three separate identities and they must never be conflated:

```text
OpenAI/app user       app_user_id
Telegram person       telegram_user_id
Telegram delegation   business_connection_id
```

The `business_connection_id` is routing/delegation metadata, not a personal Telegram login credential. Telegram can disable or replace it when connection settings change.

The service therefore stores a binding rather than a user session:

```text
app_user_id
  -> telegram_user_id
  -> current business_connection_id
  -> enabled flag
  -> granted BusinessBotRights
```

A disabled/disconnected Business connection must immediately stop all routed actions.

## Capability model

Telegram Business rights are the source of truth. The public adapter maps them to tool capabilities:

| Product action | Telegram right |
| --- | --- |
| send message | `can_reply` |
| edit message | `can_reply` |
| mark message read | `can_read_messages` |
| delete bot-sent message | `can_delete_sent_messages` or `can_delete_all_messages` |
| delete arbitrary allowed message | `can_delete_all_messages` |

The server checks rights again immediately before every write. ChatGPT confirmation is an additional control, not a replacement for Telegram-side authorization.

## Message access is event-driven

Public Mode does **not** promise arbitrary old personal Telegram history.

After the Business Bot is connected, Telegram sends business updates such as:

- `business_message`;
- `edited_business_message`;
- `deleted_business_messages`;
- `business_connection` lifecycle changes.

That means Public Mode can work extremely well for current and future conversations while avoiding a personal user-client credential. It is intentionally different from Personal Mode, which can access broader user-client history.

## Retention modes

### Default: Ephemeral

```text
Telegram update
   -> normalize
   -> answer current user request / update unread state
   -> discard body
```

The default event store is a `NullBusinessEventStore`; it retains no message bodies.

### Optional: TTL history

Users who explicitly enable searchable recent history can use a bounded retention policy:

```text
Telegram update
   -> encrypt at rest
   -> tenant-scoped event row
   -> expires after configured TTL
```

Example product options later:

- Off / live only;
- 24 hours;
- 7 days;
- 30 days.

No unlimited retention should be the default. No global cross-user search index or whole-history embeddings.

## Multi-user isolation

Every retained event key includes both:

```text
tenant/app_user_id + business_connection_id
```

A connection id from tenant A must never return events for tenant B. The current development TTL store has an explicit isolation regression test; production replaces it with an encrypted transactional database implementation.

## Server credentials

The service has one Telegram Bot API token (or a controlled bot-token set) in the server secret manager.

Public customers do **not** receive or supply that token. The bot token must never be logged or returned through MCP.

## Public adapter already scaffolded

Current branch contains:

- `public_mode/models.py` — Business connections, rights, events, retention policy;
- `public_mode/policy.py` — Telegram-rights enforcement;
- `public_mode/business_bot.py` — Bot API adapter for connection lookup, send, edit, mark-read and delete;
- `public_mode/webhook.py` — business update normalization;
- `public_mode/store.py` — no-store default + tenant-isolated TTL development store;
- `public_mode/linking.py` — hashed one-time Telegram deep-link tokens;
- `public_mode/connections.py` — app user ↔ Telegram user ↔ business connection registry.

These modules are deliberately not exposed as public MCP tools yet. MCP exposure waits for real app OAuth and tenant identity so a caller can never choose another user's `business_connection_id` directly.

## Production request path

```text
ChatGPT tool call
     |
     | OAuth access token
     v
MCP/API edge
     |
     | resolve app_user_id from token
     v
Connection registry
     |
     | load current business connection + rights
     v
Policy engine
     |
     | user confirmation for writes
     v
Telegram Business Bot API
```

The model never supplies `app_user_id` or `business_connection_id` as an authority decision. They come from authenticated server-side context.

## Webhook path

```text
Telegram webhook
     |
     | verify webhook secret / trusted ingress
     v
Parse business update
     |
     +-- business_connection -> update/revoke connection registry
     |
     +-- message event -> resolve connection -> tenant
                              |
                              +-- ephemeral processing (default)
                              or
                              +-- encrypted TTL event store (opt-in)
```

## Remaining production work

1. Create and configure the real Telegram business-ready bot / Secretary Mode.
2. Add Telegram webhook ingress with secret verification and replay/idempotency protection.
3. Add app OAuth and derive tenant identity from the OAuth token.
4. Replace in-memory link/connection stores with a transactional encrypted database.
5. Add consent ledger, user-controlled retention and delete/export endpoints.
6. Expose Public Mode MCP tools only after server-side tenant binding exists.
7. Add rate limits, abuse/flood controls and write audit.
8. Complete Telegram/OpenAI policy and privacy review before public submission.

## Product split

```text
Personal Mode
  full/private power-user access
  personal Telegram session
  self-hosted / trusted deployment

Public Mode
  Telegram Business delegation
  no customer MTProto session
  revocable scoped rights
  multi-user SaaS / Plugin Directory
```

This split is intentional. Public Mode should never silently fall back to a hosted personal Telegram session when Business permissions are insufficient.
