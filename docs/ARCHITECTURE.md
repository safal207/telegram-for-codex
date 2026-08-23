# Telegram for ChatGPT & Codex — target architecture

## Product principle

The public product should **not** behave like a hosted copy of the user's Telegram client.

For the public / Plugin Directory path, prefer Telegram's official **Connected Business Bot** model. The user connects a bot, grants explicit rights, and can pause or disconnect it. This avoids storing a personal MTProto login session for every user.

Keep the existing Telethon/MTProto implementation as a separate **Personal Mode** for private/self-hosted power users who need broader personal-account access.

## Two product modes

### 1. Public Mode — recommended for other users

Use a Telegram Business connected bot.

```text
ChatGPT / Codex
      |
      | OpenAI app OAuth
      v
Telegram for ChatGPT API
      |
      | user/account binding
      v
Telegram Business Bot
      |
      | business_connection_id + scoped rights
      v
User's allowed Telegram chats
```

Properties:

- No Telegram phone OTP is stored by our service.
- No MTProto StringSession is stored per public user.
- Telegram itself manages the business connection and its rights.
- User can pause a chat or disconnect the bot in Telegram.
- Rights can be limited to only the operations we need.
- The backend stores only the minimum connection metadata required to route requests.
- Message bodies are fetched/processed on demand and are not mirrored into a permanent database by default.

Expected feature set:

- receive new business messages;
- show unread/recent connected conversations;
- draft a reply;
- send/reply after ChatGPT confirmation;
- edit/delete/mark-read only when Telegram grants that business right;
- pause/disable automation per chat.

Important limitation: Public Mode is not intended to promise arbitrary full-history search across every personal chat. Telegram Business connections are a cleaner delegated integration, but their access model differs from a full user client.

### 2. Personal Mode — private/self-hosted

Use the existing user-client path (Telethon today; TDLib is the stronger long-term client runtime).

```text
User's private deployment
      |
      +-- /connect -> Telegram user authorization
      |
      +-- encrypted session credential
      |
      +-- private MCP endpoint
```

Properties:

- Designed for one user or a very small trusted deployment.
- Can provide broader personal-account functionality than Business Bot mode.
- Must never expose an unauthenticated MCP endpoint publicly.
- Session credentials are bearer credentials and require encrypted storage / secret management.
- This mode is not the preferred foundation for a mass-market Plugin Directory product.

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
        | Identity binding |          | Audit / consent  |
        | OpenAI <-> user  |          | minimal metadata |
        +--------+---------+          +------------------+
                 |
                 v
        +--------+-------------------------------+
        | Telegram adapter                       |
        | Public: Business Bot connection        |
        | Private: Personal MTProto/TDLib mode   |
        +--------+-------------------------------+
                 |
                 v
              Telegram
```

## What we store

### Public Mode

Store only:

- internal user/account id;
- OpenAI app/OAuth binding;
- Telegram `business_connection_id` and granted rights;
- minimal routing metadata;
- consent/version timestamps;
- audit records for write actions;
- optional short-lived encrypted cache with a strict TTL.

Do **not** store by default:

- full Telegram message history;
- contacts/address book replicas;
- raw phone login codes;
- Telegram 2FA passwords;
- personal MTProto auth keys;
- embeddings of entire Telegram histories.

### Personal Mode

Store only the encrypted Telegram session credential required to operate the private client plus minimal configuration/audit data.

## Seamless onboarding target

### Public Mode

```text
Install Telegram plugin
        -> Connect
        -> Open Telegram
        -> Enable/connect our Business Bot
        -> Choose recipients/rights
        -> Return to ChatGPT
        -> Ready
```

No terminal. No `api_id`. No `api_hash`. No copy/paste session secret.

### Personal Mode

```text
Open private /connect page
        -> phone
        -> Telegram code
        -> optional 2FA
        -> Ready
```

Still no terminal, but this remains the private/power-user path.

## Safety model

- Reads can run automatically only inside the granted source boundary.
- Send/edit/delete remain confirmation-gated in ChatGPT.
- Server also checks Telegram-side rights before every write.
- Every write is logged with actor, connection, chat, action, timestamp and result.
- User can disconnect the integration at any time.
- Revocation must invalidate our binding immediately.
- No action is allowed solely because the model requested it.

## Privacy and AI-use boundary

Telegram's API and content-licensing terms impose strong privacy obligations and restrictions around use of Telegram data for AI/ML. A public product must therefore be designed around explicit user intent, narrow source boundaries, minimal retention, and legal review before Plugin Directory submission.

Do not build a global Telegram corpus, search index or long-lived embedding store.

For any AI-assisted handling of content, keep the processing contextual and user-directed, with the smallest practical data window. Public release should not proceed until the Telegram terms are reviewed against the exact ChatGPT data flow and consent model.

## Why this is better than one hosted Telethon cluster

A hosted Telethon cluster would require us to safeguard a long-lived personal Telegram session for every user. That session behaves much more like a logged-in device credential than a normal revocable OAuth access token.

The Business Bot route moves delegation, scopes, pause/disconnect controls and business identity into Telegram's own supported model. That gives us a much cleaner trust boundary for a multi-user product.

## Roadmap

### Phase A — Personal alpha

- Keep PR #3 private-only.
- Finish PASS-CONNECT / PASS-READ.
- Protect MCP with a trusted boundary.

### Phase B — Public adapter

- Add `telegram_business` adapter.
- Create Telegram business-ready bot.
- Handle `business_connection_id` lifecycle.
- Map Telegram business rights to MCP tool availability.
- Implement receive/send/edit/read/delete only when rights permit.

### Phase C — Multi-user SaaS control plane

- OpenAI app OAuth.
- Tenant/user identity binding.
- Encrypted connection metadata store.
- Revocation/deletion endpoints.
- Consent ledger and write audit.
- Rate limits / abuse controls / flood protection.

### Phase D — Plugin Directory

- Privacy policy + terms.
- Security review.
- Telegram terms review for exact AI data flow.
- OpenAI app/plugin submission.
- Mobile enablement when the supported ChatGPT surface allows it.

## Decision

**Do not turn Personal Mode into the public architecture.**

Use Personal Mode to prove the UX. Build Public Mode on Telegram Business connected bots so that other users can connect with much less credential risk and a far more seamless onboarding experience.
