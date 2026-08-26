# Deploy Personal Mode on Railway

This runbook is for the **private single-user Personal alpha**. It gets the phone-first `/connect` flow and authenticated `/mcp` endpoint onto durable HTTPS without requiring an always-on home computer.

It is **not** the Public/Plugin Directory deployment model.

## Why Railway for the first real acceptance run

- Railway detects the root `Dockerfile` automatically.
- Railway injects the service `PORT`; `telegram-codex-remote` already listens on it.
- A Railway volume can be mounted directly at `/data/telegram`, matching the existing session/audit paths.
- The service can expose a generated HTTPS domain.
- `/healthz` is a content-free deployment health endpoint.

For this first real acceptance run, use `TELEGRAM_MCP_AUTH_MODE=static`. Static bearer auth is intentionally a **private smoke-test mode only**. ChatGPT custom-app production wiring should switch to the OAuth resource-server mode already implemented in `personal_auth.py`.

## 1. Create the Railway service

1. Create a Railway project.
2. Add a service from GitHub repo `safal207/telegram-for-codex`.
3. Select the release branch containing v0.3.0 (normally `main` after merge).
4. Railway should detect the root `Dockerfile` automatically.
5. Generate a public HTTPS domain for the service.
6. Keep the service at **one replica** for Personal Mode.

Call the generated hostname `<railway-host>` below, for example:

```text
telegram-for-codex-production.up.railway.app
```

## 2. Add persistent storage

Attach one Railway volume to the service and mount it at:

```text
/data/telegram
```

Railway mounts volumes as root. Set `RAILWAY_RUN_UID=0` so the image entrypoint
can perform its narrow startup bootstrap: verify `/data/telegram`, set its
ownership to UID/GID `10001`, restrict it to mode `0700`, and then drop
privileges before starting the MCP server. The application itself must still
run as UID/GID `10001`; do not replace this bootstrap with a permanently
root-running MCP process. Do not share the volume with another service.

Outside this controlled bootstrap, an existing POSIX credential directory must
already be `0700` or stricter. The runtime refuses an unsafe directory instead
of chmod-ing someone else's parent.

The phone-first login page stores the private Telethon StringSession at:

```text
/data/telegram/session.string
```

Do not serve this directory as static content and do not copy its contents into logs, tickets, chat messages, or repository files.

## 3. Configure variables/secrets

Set these Railway service variables. Replace placeholders locally in the Railway dashboard; never commit their values.

```dotenv
TELEGRAM_API_ID=<telegram-api-id>
TELEGRAM_API_HASH=<telegram-api-hash>

TELEGRAM_SESSION_STRING_FILE=/data/telegram/session.string
TELEGRAM_AUDIT_LOG_PATH=/data/telegram/audit.jsonl

# Required because Railway mounts the persistent volume as root. The image
# entrypoint drops to UID/GID 10001 before starting the MCP process.
RAILWAY_RUN_UID=0

# Separate secret protecting the phone-first login page actions.
TELEGRAM_CONNECT_TOKEN=<random-connect-secret-at-least-32-characters>

# Keep writes off for PASS-AUTH / PASS-CONNECT / PASS-READ.
TELEGRAM_ALLOW_WRITES=false

# Private smoke-test MCP caller auth.
TELEGRAM_MCP_AUTH_MODE=static
TELEGRAM_MCP_STATIC_TOKEN=<different-long-random-bearer-token-at-least-32-chars>
TELEGRAM_MCP_PUBLIC_URL=https://<railway-host>/mcp

# Transport-security boundary. Use the exact Railway hostname.
TELEGRAM_MCP_ALLOWED_HOSTS=<railway-host>,<railway-host>:*,healthcheck.railway.app

# curl/no-Origin smoke tests do not need a browser origin. Keep the future
# ChatGPT origins explicit rather than using `*`.
TELEGRAM_MCP_ALLOWED_ORIGINS=https://chatgpt.com,https://chat.openai.com
```

`TELEGRAM_CONNECT_TOKEN` and `TELEGRAM_MCP_STATIC_TOKEN` must be **different,
independently generated high-entropy secrets**, each at least 32 characters.
Generate each value separately with a cryptographic secret generator (for
example, `python -c "import secrets; print(secrets.token_urlsafe(32))"`) and put
it directly into Railway's secret variables. Static auth rejects documentation
placeholders, low-diversity values and repeated patterns at startup, and
`/connect` actions fail closed for the same invalid values. The first secret
authorizes Telegram login actions on `/connect`; the second authorizes MCP
callers on `/mcp`.

The remote static endpoint must use HTTPS and its URL must contain no userinfo
or fragment. It must be the exact `/mcp` endpoint, with no query string or
trailing slash. Plain HTTP is accepted only for a loopback smoke test, never
for a Railway hostname.

Railway supplies `PORT`; do not hard-code a different public port.

## 4. Configure the deployment health check

Set Railway's healthcheck path to:

```text
/healthz
```

Expected response:

```json
{"ok":true,"service":"telegram-for-codex","mode":"personal"}
```

The health endpoint deliberately does not reveal Telegram login state, phone number, username, session mode, token state, chat state, or secrets.

## 5. PASS-AUTH before Telegram login

From a trusted terminal, confirm the service is alive:

```bash
curl -i https://<railway-host>/healthz
```

Expected: HTTP `200`.

Then confirm `/mcp` is **not** open anonymously:

```bash
curl -i https://<railway-host>/mcp
```

Expected: HTTP `401` (or the MCP auth challenge response), not a successful MCP session.

Do not proceed to Telegram login if anonymous `/mcp` access succeeds.

## 6. PASS-CONNECT on the phone

Open on the phone:

```text
https://<railway-host>/connect
```

Then complete:

```text
private connect key
→ Telegram phone
→ Telegram login code
→ optional Telegram 2FA
→ Connected ✓
```

The browser never receives the resulting StringSession. The server writes it to the mounted `/data/telegram/session.string` file and reloads the Telegram gateway in-process.

After connection, redeploy/restart the Railway service once and repeat `telegram_whoami` during PASS-READ. This deliberately proves the session survived a container restart via the mounted volume.

## 7. PASS-READ

Use an MCP client that can set an Authorization bearer token and connect to:

```text
https://<railway-host>/mcp
```

Header:

```text
Authorization: Bearer <TELEGRAM_MCP_STATIC_TOKEN>
```

Acceptance sequence:

```text
telegram_whoami()
→ authorized == true
→ no phone field
→ no session secret

telegram_list_chats(limit=10, unread_only=false)
→ returns real chat metadata

telegram_get_messages(chat_id=<safe-test-chat>, limit=5)
→ returns real messages

telegram_search_messages(query=<harmless-test-query>, limit=5)
→ returns matching messages
```

Writes remain disabled throughout this acceptance run.

Treat all returned chat names, usernames and Telegram message bodies as
untrusted data. They are never authorization evidence or instructions to the
model, tools or operator.

## 8. PASS-RESTART

Restart or redeploy the service without re-running Telegram login.

Then call:

```text
telegram_whoami()
```

Expected:

```text
authorized == true
```

This is the proof that Personal Mode no longer depends on an always-on laptop or phone process.

## 9. Only then enable a write canary

After PASS-AUTH + PASS-CONNECT + PASS-READ + PASS-RESTART:

1. Set `TELEGRAM_ALLOW_WRITES=true`.
2. Set the mandatory `TELEGRAM_WRITE_CHAT_ALLOWLIST` to **one dedicated integer test-chat ID**. Empty never means all chats and must fail closed.
3. Redeploy.
4. Send one harmless message with explicit user confirmation.
5. Verify the audit record contains metadata only and no message text. The
   active JSONL file rotates at 10 MiB and retains two backups.
6. Edit only that outgoing test message.

Never begin write acceptance without a narrow integer allowlist.

## 10. What this proves — and what it does not

This Railway deployment proves the **Personal Mode vertical slice**:

```text
phone login
→ durable private Telegram session
→ authenticated remote MCP
→ read/search
→ optional confirmation-gated writes
```

It does **not** make this a mass-market public Telegram integration. Public Mode remains frozen until verified Telegram webhook ingress, idempotency, real tenant OAuth, explicit AI-content consent, encrypted transactional persistence, rate/flood controls and policy review exist.

It also does not make static bearer auth the final ChatGPT integration. After
this acceptance run, switch Personal remote MCP to the implemented OAuth
resource-server mode. Configure `TELEGRAM_MCP_OWNER_SUBJECT` to the exact owner
`sub` and verify the provider introspection response always includes the
expected `iss`, exact MCP URL in `aud`, and that owner subject before
registering the endpoint in ChatGPT. The configured issuer, introspection and
public MCP URLs must all use HTTPS and must not contain userinfo or fragments.
The public MCP URL must be the exact `/mcp` endpoint without a query string or
trailing slash.
