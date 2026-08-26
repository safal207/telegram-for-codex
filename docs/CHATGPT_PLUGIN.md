# ChatGPT and Codex plugin paths

Version 0.3.0 supports two deliberately different connection paths:

1. **Local Codex plugin** — the plugin manifest points to bundled `.mcp.json`,
   which starts the local `telegram-codex` STDIO server.
2. **Remote ChatGPT MCP** — `telegram-codex-remote` serves authenticated
   Streamable HTTP at HTTPS `/mcp` and uses an external OAuth authorization
   server.

The local package is ready for authoring tests. The remote Personal deployment
is a private, single-owner alpha; it is not a mass-market Telegram connector.

## Package wiring

The repository contains:

- `plugins/telegram-for-codex/.codex-plugin/plugin.json` — package identity, skill path and
  `mcpServers: "./.mcp.json"`;
- `plugins/telegram-for-codex/.mcp.json` — local STDIO MCP configuration;
- `plugins/telegram-for-codex/skills/telegram-for-codex/SKILL.md` — bundled workflow guidance;
- `telegram-codex` — local STDIO console launcher;
- `telegram-codex-remote` — authenticated Streamable HTTP launcher;
- `/connect` — separately protected, phone-first Telegram authorization page.

This follows OpenAI's [plugin structure and manifest path
rules](https://developers.openai.com/plugins/build/plugins#plugin-structure).
The repository intentionally has no `.app.json` and no `apps` field: those are
for a **registered** remote MCP connection. Do not invent a
`plugin_asdk_app...` ID. After ChatGPT developer mode creates a real connection,
its technical ID can be added in a separate release.

For local installation, runtime prerequisites and marketplace steps, see
[`LOCAL_PLUGIN.md`](LOCAL_PLUGIN.md).

## Remote authentication contract

Remote `/mcp` has **no unauthenticated mode**. Startup fails closed unless one
of these modes is fully configured:

- `oauth` — production/ChatGPT path using RFC 7662 token introspection;
- `static` — private curl/MCP Inspector smoke testing only.

Host and Origin allowlists remain required transport controls, but they do not
authenticate a caller:

```dotenv
TELEGRAM_MCP_ALLOWED_HOSTS=telegram.example.com,telegram.example.com:*
TELEGRAM_MCP_ALLOWED_ORIGINS=https://chatgpt.com,https://chat.openai.com
```

### OAuth production mode

```dotenv
TELEGRAM_MCP_AUTH_MODE=oauth
TELEGRAM_MCP_PUBLIC_URL=https://telegram.example.com/mcp
TELEGRAM_MCP_OAUTH_SCOPES=telegram:personal
TELEGRAM_OAUTH_ISSUER_URL=https://your-auth-provider.example.com/
TELEGRAM_MCP_OWNER_SUBJECT=<exact-owner-sub-claim>
TELEGRAM_OAUTH_INTROSPECTION_URL=https://your-auth-provider.example.com/oauth2/introspect
TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID=<resource-server-client-id>
TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-manager-value>
```

All three configured OAuth URLs — public MCP, issuer and introspection — must
use HTTPS and must not contain URL userinfo (embedded username/password) or a
fragment. The public MCP URL must be the exact `/mcp` endpoint, with no query
string or trailing slash. The server rejects an invalid URL at startup.

An introspection response is accepted only when all of these are true:

- `active` is exactly `true`;
- `iss` is present and matches `TELEGRAM_OAUTH_ISSUER_URL`;
- `aud` is present and contains the exact `TELEGRAM_MCP_PUBLIC_URL`;
- `sub` is present and exactly matches `TELEGRAM_MCP_OWNER_SUBJECT`.

The subject binding is essential because one Personal deployment owns one
Telethon user session. A valid token for a different user must never reach that
session.

ChatGPT authenticates with the external authorization server; this MCP server
does not issue login tokens. The provider must support the OAuth client flow
required by the target ChatGPT/Codex surface. See OpenAI's current [MCP OAuth
guidance](https://learn.chatgpt.com/docs/extend/mcp?surface=cli#oauth-client-registration).

### Static private smoke-test mode

```dotenv
TELEGRAM_MCP_AUTH_MODE=static
TELEGRAM_MCP_PUBLIC_URL=https://telegram.example.com/mcp
TELEGRAM_MCP_STATIC_TOKEN=<at-least-32-random-characters>
```

Generate this value and `TELEGRAM_CONNECT_TOKEN` independently. Both must be at
least 32 characters and must differ. Static auth rejects blanks, documentation
placeholders, low-diversity values and repeated patterns at startup; `/connect`
actions fail closed for the same invalid values. Static mode proves
the bearer gate for a trusted client; it is not the ChatGPT production login
flow. Remote static URLs still require HTTPS and forbid userinfo/fragments;
plain HTTP is accepted only for a loopback (`localhost`, `127.0.0.1` or `::1`)
smoke test.

## Single-owner Telegram session

Phone-first authorization stores one Telethon `StringSession` in a private
persistent file, normally:

```text
/data/telegram/session.string
```

Alternatively, a stateless secret manager can provide
`TELEGRAM_SESSION_STRING`. A StringSession is a bearer credential. Never put it,
a Telegram login code, or a 2FA password in ChatGPT, an MCP argument, logs,
tickets or repository files.

Protect `/connect` with a separately generated high-entropy secret of at least
32 characters:

```dotenv
TELEGRAM_CONNECT_TOKEN=<different-32-plus-character-secret>
TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string
TELEGRAM_ALLOW_WRITES=false
```

Expose `/connect` only through HTTPS. The browser submits the connect key,
phone, Telegram code and optional 2FA password to the live authorization flow;
the resulting session remains server-side.

## Build and run the remote container

The container is multi-stage, installs exact constrained dependencies, runs as
UID/GID `10001`, and creates `/data/telegram` with POSIX mode `0700`.

For a localhost-only static smoke test, create `.env.remote` from the example
and override the public URL/transport boundary for localhost:

```dotenv
TELEGRAM_MCP_AUTH_MODE=static
TELEGRAM_MCP_PUBLIC_URL=http://localhost:8000/mcp
TELEGRAM_MCP_STATIC_TOKEN=<at-least-32-random-characters>
TELEGRAM_MCP_ALLOWED_HOSTS=localhost,localhost:*,127.0.0.1,127.0.0.1:*
TELEGRAM_MCP_ALLOWED_ORIGINS=http://localhost:*,http://127.0.0.1:*
```

```bash
docker build -t telegram-for-codex .
docker volume create telegram-codex-data
docker run --rm \
  --user 0 \
  --env-file .env.remote \
  --mount type=volume,source=telegram-codex-data,target=/data/telegram \
  -p 8000:8000 \
  telegram-for-codex
```

`--user 0` authorizes only the narrow volume bootstrap: the entrypoint secures
the dedicated named volume and drops to UID/GID `10001` before executing MCP.
Do not replace the named volume with a host bind mount unless you have already
set its ownership and private mode deliberately. Outside this container
bootstrap, an existing credential directory must already be `0700` or stricter;
credential files are `0600`. These POSIX modes do not provide Windows ACL
isolation.

The write audit is metadata-only and excludes message text, previews, Telegram
payloads and raw exception strings. The active JSONL file rotates at 10 MiB and
keeps two backups.

Local routes:

```text
http://localhost:8000/healthz
http://localhost:8000/connect
http://localhost:8000/mcp
```

Even on localhost, `/mcp` requires the configured bearer/OAuth token.

## PASS-AUTH before Telegram login

Verify:

1. `GET /healthz` returns a content-free `200` response.
2. `/mcp` without `Authorization` returns `401`/an MCP auth challenge.
3. RFC 9728 protected-resource metadata is available.
4. Inactive/expired tokens are rejected.
5. Missing or wrong `iss`, missing or wrong `aud`, and a non-owner `sub` are
   rejected.
6. A correctly scoped owner token reaches the MCP protocol.

For static-mode inspection, connect a trusted MCP client to `/mcp` with:

```text
Authorization: Bearer <TELEGRAM_MCP_STATIC_TOKEN>
```

Expected tools:

- `telegram_whoami`
- `telegram_audit_log`
- `telegram_list_chats`
- `telegram_get_messages`
- `telegram_search_messages`
- `telegram_send_message`
- `telegram_edit_message`

## Register the remote MCP in ChatGPT developer mode

Do this only after the HTTPS endpoint passes OAuth-mode PASS-AUTH:

1. Enable ChatGPT developer mode for an eligible account/workspace.
2. Create a custom MCP connection with the exact HTTPS `/mcp` URL.
3. Complete OAuth and rescan the tools.
4. Verify the read-only and destructive/write annotations.
5. Copy the real technical connection ID (`plugin_asdk_app...`) from the
   registered connection.
6. Test read/search from a new conversation.

Registration connects the remote tools. Packaging that registered connection
inside this repository is a later explicit step: create `.app.json` with the
real ID, add `apps: "./.app.json"` to the plugin manifest, validate, and retest.
Until then, the checked-in local plugin `.mcp.json` is the honest Codex path.

## PASS-CONNECT and PASS-READ

After PASS-AUTH, open the HTTPS `/connect` page on a phone and complete Telegram
authorization. Restart/redeploy once to prove the private volume survives, then
run:

```text
telegram_whoami()
telegram_list_chats(limit=10, unread_only=false)
telegram_get_messages(chat_id=<safe-test-chat>, limit=5)
telegram_search_messages(query=<harmless-query>, limit=5)
```

Expected: `authorized == true`; no Telegram profile identifier, username,
phone number, session secret, or absolute local path appears in the status
response; real read/search results are returned only through their approved
tools.

Treat every returned chat title, username and Telegram message as untrusted
data. It is never authorization evidence and must never override system/user
instructions, server-side policy, explicit approval or the write allowlist.

## Write canary

Only after PASS-AUTH, PASS-CONNECT, PASS-READ and restart persistence:

1. Set `TELEGRAM_ALLOW_WRITES=true`.
2. Set a non-empty `TELEGRAM_WRITE_CHAT_ALLOWLIST` containing one dedicated
   integer test-chat ID. Empty never means all chats.
3. Send one harmless message with explicit product approval and `confirm=true`.
4. Verify the audit record contains metadata but no message text.
5. Edit only that outgoing test message, again with explicit approval.

## Public release boundary

Personal Mode remains a private single-owner integration. A public multi-user
release still needs per-user encrypted Telegram session storage, account
disconnect/deletion, consent/privacy/legal flows, abuse and rate controls,
submission tests, and policy review. Public Mode remains frozen until its
separate Telegram Business prerequisites are complete.
