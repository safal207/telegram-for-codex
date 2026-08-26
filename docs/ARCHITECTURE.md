# Telegram for ChatGPT & Codex — target architecture

## Product principle

There are two different products. Do not market them as one interchangeable “Telegram like Gmail” experience.

1. **Personal Mode** — self-hosted/private **“my Telegram”** access for one trusted power user.
2. **Public Mode** — multi-user **AI secretary for explicitly allowed private chats** through Telegram Business delegation.

Do not turn Personal Mode into SaaS, and do not describe Public Mode as whole-account Telegram access.

## Why Telegram is not just another database connector

The hard part is not where messages live. The hard part is the trust boundary.

A personal Telegram user session behaves like another logged-in device credential. A mass-market hosted Telethon design would therefore become a vault of long-lived account credentials.

Telegram Business delegation is cleaner for public use because Telegram owns:

- connection lifecycle;
- selected recipients/chats;
- Business rights;
- pause/revocation.

But that delegation is narrower than a full user client. Public Mode is therefore a secretary for selected current/future private conversations, not a replacement for the user's complete Telegram client.

## Personal Mode — private “my Telegram”

```text
User's private deployment
      |
      +-- /connect -> Telegram user authorization
      |
      +-- private session credential
      |
      +-- OAuth-protected /mcp
```

Properties:

- one user or very small trusted deployment;
- broader personal-account history/functionality than Business Bot mode;
- remote `/mcp` has **no unauthenticated mode**;
- Telegram session credential is still a bearer credential and remains private;
- this mode is not the mass-market trust model.

### Personal caller authentication

```text
ChatGPT / MCP client
      |
      | OAuth access token
      v
/mcp Resource Server
      |
      | RFC 9728 protected-resource metadata
      | RFC 7662 token introspection
      v
External OAuth/OIDC provider
```

The MCP server validates bearer tokens on every remote request and does not issue login tokens itself. Production uses OAuth. A static bearer verifier exists only for trusted curl/MCP Inspector smoke tests.

Host/Origin allowlists remain transport-security controls, not authentication.

## Public Mode — scoped AI secretary

```text
ChatGPT / Codex
      |
      | app OAuth
      v
Telegram for ChatGPT service
      |
      | authenticated app_user_id
      v
Connection registry
      |
      | server-resolved business_connection_id + current rights
      v
Telegram Business Bot
      |
      v
Explicitly allowed private chats
```

Properties:

- no Telegram OTP/2FA handled by the public service;
- no personal MTProto StringSession per public user;
- Telegram owns Business connection scope and rights;
- message retention defaults to off;
- event-driven after connection;
- no arbitrary full-history promise;
- the one-connected-Business-bot-per-account constraint is a real product limitation.

Public Mode should answer questions like:

```text
“What did Ivan write after I connected the bot to this chat?”
```

It must not promise:

```text
“Search my entire Telegram history from 2019.”
```

## Public onboarding is explicit, not one-click

A correct flow contains separate trust decisions:

```text
1. ChatGPT/app OAuth
2. Telegram deep-link identity binding
3. Telegram Business UI: choose chats + rights
4. Explicit disclosure/consent that selected message content may be sent to OpenAI for the user's requested task
5. Connected
```

Public users still avoid developer credentials (`api_id`, `api_hash`, StringSession), but the UX must not hide the actual consent boundaries.

## Identity model

Keep these separate:

```text
app_user_id             authenticated app identity
telegram_user_id        Telegram person confirmed by Telegram
business_connection_id  revocable Telegram delegation/routing id
```

The model never supplies `app_user_id` or `business_connection_id` as authorization authority. The server derives the caller, resolves the current Business connection internally, then applies Telegram-side rights.

## Capability model

Telegram Business rights are the source of truth:

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

No write is allowed solely because the model requested it.

## Public message and retention model

Business mode is event-driven.

```text
Telegram webhook
      |
      | verified ingress + idempotency/replay protection
      v
Normalize update
      |
      +-- connection update -> refresh/revoke registry
      +-- new/edit message -> resolve tenant -> process / optional TTL retention
      +-- delete update -> remove retained representation
```

### Default: no message-body retention

```text
Telegram update -> user-directed processing -> discard body
```

`NullBusinessEventStore` is the default contract.

### Optional bounded recent history

Only after explicit opt-in:

```text
Telegram update
   -> encrypt at rest
   -> key by app_user_id + connection_id
   -> strict TTL
```

Possible product choices later: live only, 24 hours, 7 days, 30 days.

No permanent whole-account mirror, global corpus or whole-history embedding index.

A Telegram disconnect immediately:

1. revokes routing;
2. makes writes fail;
3. purges retained TTL history for that connection unless a documented legal requirement says otherwise.

## What we store

### Public Mode

Minimum durable metadata only:

- internal app user id and OAuth binding;
- Telegram user id needed for binding;
- current `business_connection_id`;
- current rights/enabled status;
- consent/version timestamps, including OpenAI content-transfer disclosure;
- write audit records;
- hashed pending link tokens until expiry;
- optional encrypted TTL message events only if the user opts in.

Do not store by default:

- personal MTProto auth keys;
- Telegram login codes or 2FA passwords;
- full Telegram history;
- contact/address-book replicas;
- permanent embeddings/corpora of Telegram content.

### Personal Mode

Store only the Telegram session credential required for that private client plus minimal configuration/audit data.

## Current code boundary

The branch already contains Public foundation modules:

- `public_mode/models.py`;
- `public_mode/policy.py`;
- `public_mode/business_bot.py`;
- `public_mode/webhook.py`;
- `public_mode/store.py`;
- `public_mode/linking.py`;
- `public_mode/connections.py`;
- `public_mode/service.py`.

These are a **domain/service scaffold, not a production public service**. Public MCP exposure stays blocked.

## Roadmap decision

### Active: Personal Mode

- OAuth-protected remote `/mcp`;
- configure a real OAuth/OIDC provider with refresh/offline access for ChatGPT;
- PASS-AUTH, PASS-CONNECT and PASS-READ on a real deployment/account.

### Frozen: Public Mode

Do not add more MCP surface until all of these exist:

- verified Telegram webhook ingress;
- idempotency/replay protection;
- real app OAuth/tenant middleware;
- explicit consent ledger including disclosure of content transfer to OpenAI;
- encrypted transactional registry/retention storage;
- retention/delete/export controls;
- rate/flood controls and write audit;
- Telegram/OpenAI privacy and policy review.

## Decision

**Personal Mode proves the full “my Telegram” UX. Public Mode is a narrower, revocable AI secretary for selected private chats.**

That boundary is intentional and should remain visible in code, documentation and marketing.
