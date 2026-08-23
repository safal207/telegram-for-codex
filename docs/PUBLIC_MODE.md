# Public Mode — seamless multi-user design

Public Mode is **not** a hosted copy of a user's Telegram client. It is an AI secretary for explicitly selected private conversations from the moment a Telegram Business connection is enabled.

It uses Telegram's official Business Bot delegation instead of logging each customer in as a personal MTProto client.

Official references:

- https://core.telegram.org/api/bots/connected-business-bots
- https://core.telegram.org/api/business
- https://core.telegram.org/bots/features
- https://core.telegram.org/bots/api

## Product boundary

```text
Personal Mode = self-hosted / private "my Telegram" power-user mode
Public Mode   = AI secretary for explicitly permitted private chats
```

Public Mode must never promise:

- arbitrary full-history search;
- Saved Messages access;
- arbitrary group/channel access;
- retroactive search over messages from before the Business connection;
- the same capability envelope as a Telegram user client.

Telegram Business `can_reply` permits sending and editing messages in private chats that had incoming activity within the last 24 hours. That 24-hour window is a real product constraint, not an implementation detail.

Telegram currently permits one connected Business Bot per account, so installing this integration may displace another connected business assistant. The product must disclose that before setup.

## Identity linking happens before Business connection

OpenAI/app OAuth authenticates the user to **our service**. It does not itself bind a Telegram Business connection.

The Telegram identity must be linked first through Telegram itself:

```text
1. User is signed into our app / ChatGPT surface.
        |
        v
2. Generate random one-time link token
   - 10 minute TTL
   - one use
   - store SHA-256 only
        |
        v
3. Open https://t.me/<our_bot>?start=link_<token>
        |
        v
4. Telegram delivers /start from the real Telegram user
        |
        v
5. Verify token and bind:
   internal/app user <-> telegram_user_id
        |
        v
6. Only then ask the user to enable the bot under
   Telegram Settings -> Business -> Chatbots
        |
        v
7. business_connection update arrives with the same Telegram user id
        |
        v
8. Match it to the already-bound internal user
```

This avoids pretending Telegram Business setup is a redirect-based OAuth callback. The trust anchor for Telegram identity is the `/start` message delivered by Telegram from the user's own account.

## Required consent before content reaches ChatGPT/OpenAI

Business connection consent is not enough by itself for the product data flow.

Before any Telegram message body is returned through MCP to ChatGPT/OpenAI, the user must see and accept a separate, explicit disclosure that permitted Telegram message content will be sent to the configured AI provider for the requested task.

That consent must be versioned and revocable.

Suggested consent record:

```text
consents
- internal_user_id
- consent_type
- policy_version
- granted_at
- revoked_at
```

No Telegram message body should cross the AI boundary until the required consent is active.

## Identity and connection state

There are three separate identities and they must never be conflated:

```text
OpenAI/app user       app_user_id
Telegram person       telegram_user_id
Telegram delegation   business_connection_id
```

The `business_connection_id` is routing/delegation metadata, not a personal Telegram login credential. Telegram can disable or replace it when connection settings change.

The service stores a binding rather than a user session:

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
| send message | `can_reply` + Telegram's 24-hour private-chat rule |
| edit message | `can_reply` + Telegram's allowed business-message rules |
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

Product wording should therefore be:

> Assistant connected to the conversations you permit from the moment you connect it.

Not:

> Search my entire Telegram history.

A good acceptance question for Public Mode is:

> What did Ivan write after I connected the assistant to this chat?

Not:

> What did Ivan write over the last year?

## Data model

Recommended production shape:

```text
users
- internal_user_id
- telegram_user_id
- created_at

telegram_connections
- business_connection_id
- internal_user_id
- rights_json
- chat_scope
- status
- connected_at
- revoked_at

consents
- internal_user_id
- consent_type
- policy_version
- granted_at
- revoked_at

audit
- actor_id
- action_type
- connection_id
- chat_id
- message_id (optional)
- timestamp
- result
- error_type (optional)
```

**Audit never stores message text, previews, prompts, raw Telegram payloads, raw exception bodies, or embeddings.**

## Retention modes

### Default: Ephemeral / no-store

```text
Telegram update
   -> normalize
   -> serve current user-directed task if consent allows
   -> discard message body
```

The default event store is `NullBusinessEventStore`; it retains no message bodies.

### Optional searchable recent history

Searchable history is a separate opt-in feature, disabled by default.

For v1, do **not** use embeddings.

If enabled, retain only the minimum encrypted message representation necessary for bounded full-text search:

```text
message_index
- internal_user_id
- business_connection_id
- message_id
- chat_id
- occurred_at
- encrypted_text
- expires_at
```

Requirements:

- explicit opt-in separate from Business connection;
- tenant isolation;
- encryption at rest;
- user-selectable bounded TTL;
- delete-all control;
- edit events replace retained content;
- delete events remove retained content;
- disconnect purges retained content;
- no global search corpus;
- no embeddings/vectorization in v1.

Example retention choices later:

- Off / live only — default;
- 24 hours;
- 7 days;
- 30 days.

Embeddings or any derived semantic index require a separate technical/legal review and must not be silently introduced as an implementation detail.

## Multi-user isolation

Every retained event key includes both:

```text
tenant/app_user_id + business_connection_id
```

A connection id from tenant A must never return events for tenant B. Production replaces in-memory development stores with an encrypted transactional implementation.

## Server credentials and bot scaling

Bot tokens are high-impact server credentials. They must live in a secret manager, support rotation, and never be logged or returned through MCP.

Do not start with a multi-bot pool unless real telemetry shows a need. A bot pool adds routing, rotation and blast-radius complexity. If/when per-bot limits or operational isolation require sharding, introduce a bot registry:

```text
bot_shards
- bot_id
- secret_ref
- status
- connection_count
- health
```

Connections are then assigned server-side to a shard. The model never chooses a bot token or shard.

Anomaly detection should watch for unusual send/delete volume, repeated failures and sudden cross-tenant fan-out.

## Public adapter already scaffolded

Current branch contains:

- `public_mode/models.py` — Business connections, rights, events, retention policy;
- `public_mode/policy.py` — Telegram-rights enforcement;
- `public_mode/business_bot.py` — Bot API adapter for connection lookup, send, edit, mark-read and delete;
- `public_mode/webhook.py` — business update normalization;
- `public_mode/store.py` — no-store default + tenant-isolated TTL development store with edit/delete/purge semantics;
- `public_mode/linking.py` — hashed one-time Telegram deep-link tokens;
- `public_mode/connections.py` — app user ↔ Telegram user ↔ business connection registry;
- `public_mode/service.py` — authenticated-user routing, recent/search access, writes and disconnect purge.

These modules are deliberately not exposed as public MCP tools yet.

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
Consent check
     |
     | AI-content transfer allowed?
     v
PublicTelegramService
     |
     | resolve current Business connection server-side
     v
Policy engine
     |
     | Telegram rights + 24h rule + user confirmation for writes
     v
Telegram Business Bot API
```

The model never supplies `app_user_id` or `business_connection_id` as an authority decision. They come from authenticated server-side context.

## Webhook path

```text
Telegram webhook
     |
     | verified secret + idempotency/replay protection
     v
Parse business update
     |
     +-- business_connection -> update/revoke connection registry
     |
     +-- message event -> resolve connection -> tenant
     |                         |
     |                         +-- ephemeral processing (default)
     |                         or
     |                         +-- encrypted TTL full-text store (explicit opt-in)
     |
     +-- delete event -> delete retained message bodies
```

A Telegram disconnect must revoke request routing and purge optional retained history immediately.

## Remaining production work

1. Freeze Public scaffold; do not expose it through MCP yet.
2. Finish and test Personal Mode first.
3. Create/configure the real Telegram business-ready bot.
4. Add verified Telegram webhook ingress + idempotency/replay protection.
5. Add real app OAuth and tenant identity middleware.
6. Add explicit consent gate for Telegram content -> ChatGPT/OpenAI transfer.
7. Replace in-memory link/connection stores with encrypted transactional storage.
8. Add retention controls, delete/export endpoints and metadata-only audit.
9. Add rate limits, abuse/flood controls and bot-secret monitoring.
10. Complete Telegram/OpenAI privacy + policy review before public submission.

## Decision

```text
Personal Mode
  self-hosted/private "my Telegram"
  Telethon user session
  broader history and account capability

Public Mode
  "AI secretary for permitted private chats"
  Telegram Business delegation
  event-driven from connection time
  24-hour reply constraint
  no customer MTProto session
  no embeddings in v1
```

This split is intentional. Public Mode must never silently fall back to a hosted personal Telegram session when Business permissions are insufficient.
