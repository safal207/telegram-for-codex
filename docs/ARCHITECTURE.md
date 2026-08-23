# Telegram for ChatGPT & Codex — target architecture

## Product principle

The product has two intentionally different trust models:

1. **Personal Mode** — private/self-hosted user-client access for one power user.
2. **Public Mode** — Telegram Business Bot delegation for a scalable multi-user service.

Do not turn Personal Mode into the public architecture.

For the public / Plugin Directory path, prefer Telegram's official **Connected Business Bot** model. The user connects a bot, grants explicit rights, and can pause or disconnect it. This avoids storing a personal MTProto login session for every user.

Keep the existing Telethon/MTProto implementation as a separate Personal Mode for private/self-hosted users who need broader personal-account access.

## Why Telegram is not just another database connector

The hard problem is not where to put Telegram messages. The hard problem is the trust boundary.

A personal Telegram user session behaves much more like another logged-in device credential than a narrow OAuth token. A mass-market service built from hosted user sessions would need to protect one powerful long-lived credential per customer.

Telegram Business delegation gives us a cleaner model:

- Telegram owns connection lifecycle;
- Telegram owns recipient selection;
- Telegram owns business rights;
- Telegram can pause or revoke the connection;
- the service stores routing metadata rather than a customer's personal MTProto session.

## Two product modes

### 1. Public Mode — recommended for other users

```text
ChatGPT / Codex
      |
      | OpenAI/app OAuth
      v
Telegram for ChatGPT API
      |
      | authenticated app_user_id
      v
Connection registry
      |
      | server-resolved business_connection_id + rights
      v
Telegram Business Bot
      |
      v
User's allowed Telegram chats
```

Properties:

- No Telegram phone OTP is stored by our service.
- No Telegram 2FA password is handled by the public service.
- No MTProto StringSession is stored per public user.
- Telegram itself manages the Business connection and its rights.
- User can pause a chat or disconnect the bot in Telegram.
- Rights can be limited to only the operations we need.
- The model never selects a tenant or `business_connection_id` as an authority decision.
- Message retention defaults to **off**.

Expected feature set:

- receive new Business messages;
- surface recent connected conversations when retention/state permits;
- draft a reply;
- send/reply after ChatGPT confirmation;
- edit/delete/mark-read only when Telegram grants that Business right;
- pause/disable automation per chat;
- user-controlled recent-history retention when explicitly enabled.

Important limitation: Public Mode is event-driven. It does not promise arbitrary full-history search across every old personal chat. Telegram starts sending Business updates according to the connection settings; broader personal history remains a Personal Mode capability.

### 2. Personal Mode — private/self-hosted

Use the existing user-client path (Telethon today; TDLib remains a possible stronger long-term client runtime).

```text
User's private deployment
      |
      +-- /connect -> Telegram user authorization
      |
      +-- encrypted session credential
      |
      +-- private authenticated MCP endpoint
```

Properties:

- Designed for one user or a very small trusted deployment.
- Can provide broader personal-account functionality than Business Bot mode.
- Must never expose an unauthenticated MCP endpoint publicly.
- Session credentials are bearer credentials and require secret management.
- This mode is not the preferred foundation for a mass-market Plugin Directory product.

## Seamless Public Mode onboarding

The public UX should feel much closer to Gmail than to a developer tool.

```text
ChatGPT: Connect Telegram
        |
        | app OAuth establishes app_user_id
        v
Generate one-time link token
        |
        | retain only SHA-256; 10-minute TTL; one use
        v
Open t.me/<our_bot>?start=link_<token>
        |
        | Telegram identifies the person itself
        v
/start link_<token>
        |
        | app_user_id <-> telegram_user_id binding
        v
User enables our Business Bot
and chooses recipients / rights in Telegram
        |
        v
business_connection update
        |
        | current business_connection_id + rights
        v
Connected ✓
```

Public users never need to copy or type:

- Telegram `api_id`;
- Telegram `api_hash`;
- Telegram login code into our app;
- Telegram 2FA password into our app;
- Telethon StringSession;
- bot token.

The Telegram bot deep-link start parameter is suited to carrying a short authentication/link token for connecting a Telegram identity to an account on another platform. Our raw token is returned once, not stored, expires, and cannot be reused.

## Identity model

Keep three identifiers separate:

```text
app_user_id             authenticated app/OpenAI identity
telegram_user_id        Telegram person confirmed by Telegram
business_connection_id  revocable Telegram delegation/routing id
```

The service stores a binding:

```text
app_user_id
  -> telegram_user_id
  -> current business_connection_id
  -> enabled status
  -> current BusinessBotRights
```

The model must never supply `app_user_id` or `business_connection_id` as authority. They come from authenticated server-side context and the connection registry.

## Public multi-user control plane

```text
                   +-------------------------+
                   |     ChatGPT / Codex     |
                   +------------+------------+
                                |
                                | OAuth 2.1 / app auth
                                v
+-------------------+   +-------+--------+   +--------------------+
| Plugin package    |-->| API / MCP edge |-->| Policy + approvals |
| skills + metadata |   | stateless      |   | read/write scopes  |
+-------------------+   +-------+--------+   +--------------------+
                                |
                 +--------------+--------------+
                 |                             |
                 v                             v
        +--------+---------+          +--------+---------+
        | Identity binding |          | Consent / audit  |
        | OAuth <-> user   |          | minimal metadata |
        +--------+---------+          +------------------+
                 |
                 v
        +--------+-------------------------------+
        | PublicTelegramService                  |
        | resolves connection server-side        |
        +--------+-------------------------------+
                 |
          +------+-------+
          |              |
          v              v
 Business Bot API    Event Store
                    default: Null
                    optional: encrypted TTL
          |
          v
       Telegram
```

## Capability model

Telegram Business rights remain the source of truth:

| Product action | Required Telegram right |
| --- | --- |
| send | `can_reply` |
| edit | `can_reply` |
| mark read | `can_read_messages` |
| delete sent | `can_delete_sent_messages` or `can_delete_all_messages` |
| delete arbitrary allowed message | `can_delete_all_messages` |

Every write has two independent gates:

```text
ChatGPT/user approval
        AND
Telegram Business right
```

No action is allowed solely because the model requested it.

## Event-driven message path

Telegram sends Business lifecycle/message updates after connection, including new, edited and deleted Business messages.

```text
Telegram webhook
      |
      | verified ingress + idempotency
      v
Normalize business update
      |
      +-- connection update -> refresh/revoke registry
      |
      +-- new/edit message -> resolve connection -> app_user_id
      |                         |
      |                         +-- live processing
      |                         +-- optional TTL retention
      |
      +-- delete update -> remove retained representation
```

A Telegram disconnect must immediately:

1. revoke request routing;
2. make all writes fail;
3. purge any retained TTL history for that connection unless policy/legal requirements explicitly require otherwise.

## Retention model

### Default: no message-body retention

```text
Telegram update -> process -> discard body
```

The code uses `NullBusinessEventStore` as the privacy-first default contract.

### Optional bounded recent history

If the user explicitly enables searchable recent history:

```text
Telegram update
   -> encrypt at rest
   -> key by app_user_id + connection_id
   -> strict TTL
```

Possible future product choices:

- Live only / Off;
- 24 hours;
- 7 days;
- 30 days.

No unlimited retention by default. No cross-user corpus. No whole-history embedding index.

## Tenant isolation

All retained content is scoped by both tenant and connection:

```text
(app_user_id, business_connection_id)
```

The PublicTelegramService receives `app_user_id` from authenticated server context, resolves the current connection internally, and only then calls Telegram or the event store.

The model-facing tool schema should contain business inputs such as `chat_id`, `message_id`, `text`, `query` — not tenant/connection authority selectors.

## What we store

### Public Mode

Minimum durable metadata:

- internal app user id;
- OAuth/app binding;
- Telegram user id required for binding;
- current `business_connection_id`;
- current granted rights / enabled status;
- consent/version timestamps;
- write audit records;
- hashed pending link tokens until they expire;
- optional encrypted TTL message events only if the user opts in.

Do **not** store by default:

- personal MTProto auth keys;
- Telegram phone login codes;
- Telegram 2FA passwords;
- full Telegram message history;
- contacts/address-book replicas;
- permanent embeddings of Telegram histories.

### Personal Mode

Store only the Telegram session credential required for the private client plus minimal configuration/audit data.

## Public request path

```text
ChatGPT tool call
     |
     | OAuth access token
     v
MCP/API edge
     |
     | derive app_user_id
     v
PublicTelegramService
     |
     | server-side registry lookup
     v
current BusinessConnection
     |
     | policy check + user approval for writes
     v
Telegram Business Bot API
```

## Public code boundary already scaffolded

Current branch contains:

- `public_mode/models.py` — rights, connection, event and retention models;
- `public_mode/policy.py` — rights-to-action enforcement;
- `public_mode/business_bot.py` — Telegram Bot API Business adapter;
- `public_mode/webhook.py` — Business update normalization;
- `public_mode/store.py` — Null store + tenant-isolated TTL development store;
- `public_mode/linking.py` — one-time hashed Telegram deep-link tokens;
- `public_mode/connections.py` — app/Telegram/connection registry + revocation;
- `public_mode/service.py` — tenant-safe server-side routing and disconnect purge.

These Public Mode modules are deliberately not exposed as public MCP tools yet. MCP exposure waits for real OAuth/tenant middleware and verified Telegram webhook ingress.

## Remaining production boundary

Before Public Mode becomes a real multi-user service:

- create/configure the real Telegram business-ready bot / Secretary Mode;
- verified Telegram webhook ingress with webhook secret and replay/idempotency protection;
- app/OpenAI OAuth and tenant identity middleware;
- transactional encrypted persistence for identity, connection, consent and optional TTL events;
- user-visible retention controls;
- disconnect/delete/export endpoints;
- write audit, rate limits and Telegram flood protection;
- legal/privacy review against Telegram and OpenAI terms;
- Plugin Directory submission and supported-surface validation.

## Privacy and AI-use boundary

Telegram's API/content terms impose strong privacy obligations and restrictions around use of Telegram data for AI/ML. Public Mode should therefore be designed around explicit user intent, narrow connected-chat boundaries, minimal retention and legal review before public submission.

Do not build a global Telegram corpus, whole-history search index or long-lived embedding store.

For AI-assisted handling of content, keep processing contextual and user-directed, with the smallest practical data window.

## Decision

**Personal Mode proves the full-power UX. Public Mode is the scalable product.**

Public Mode uses Telegram Business connected bots, one-time Telegram identity linking, server-side tenant resolution, rights-derived capabilities and no-store-by-default message processing. That gives other users a substantially safer and more seamless onboarding path without turning our infrastructure into a vault of personal Telegram device credentials.
