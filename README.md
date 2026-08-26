# Telegram for Codex

**A private, local Telegram inbox for Codex.** Review unread chats, search your
history, and draft replies without copy/paste. Reading private chat content is
reviewable; sending and editing stay disabled until you explicitly enable and
approve them.

> Developer alpha (`0.3.0`). Personal Mode is the product available today. It
> gives Codex access to your Telegram account; it does **not** control Codex from
> Telegram. ChatGPT remote access and the multi-user Business product remain
> separate, unfinished tracks.

## What it does

- summarize unread Telegram chats;
- find a message or conversation by topic;
- read recent context before drafting a reply;
- send or edit text only after recipient/text review and explicit approval;
- keep the Telegram session on your machine in local mode;
- record optional metadata-only write audit events without message text.

Example prompts:

```text
Show my unread Telegram chats.
Find my recent Telegram conversation about Project Aurora.
Draft a reply to the latest message in the test chat. Do not send it.
```

## Who it is for

Personal Mode is for a single technical user who already uses Codex Desktop/CLI
and wants self-hosted access to their own Telegram account. It requires Python
3.11 or newer (CI currently covers 3.11/3.12) and Telegram API credentials from
`my.telegram.org`.

It is not a hosted consumer service, a team connector, or a Telegram Business
automation product. Public Mode is intentionally not exposed through MCP.

## Quick start

### 1. Install the Python runtime

The recommended developer-alpha path uses `pipx`, which keeps the package
isolated while placing the `telegram-codex*` launchers on the user PATH. Install
[`pipx` from its official guide](https://pipx.pypa.io/latest/how-to/install-pipx.html),
then run:

```text
pipx ensurepath
```

Open a new terminal, then install this project:

```text
pipx install "git+https://github.com/safal207/telegram-for-codex.git@main"
```

For source development instead:

```text
git clone https://github.com/safal207/telegram-for-codex.git
cd telegram-for-codex
python -m venv .venv
```

Activate the environment, then install:

```text
python -m pip install --constraint constraints.txt ".[dev]"
```

If you use a virtual environment, launch Codex from that environment or make
its scripts directory visible to the Codex host. `telegram-codex-doctor` checks
this prerequisite without printing credentials.

### 2. Create private local configuration

Run:

```text
telegram-codex-setup
```

The guided setup asks for the Telegram API ID/hash without echoing the hash,
creates `~/.telegram-codex/config.env`, and keeps writes off. Explicit
`TELEGRAM_*` environment variables still take precedence for advanced use. If
the current environment already enables writes, setup stops and asks you to
disable that override first.

Authorize the Telegram session in a real terminal:

```text
telegram-codex-auth
telegram-codex-doctor
```

Never enter a Telegram login code, 2FA password, API hash, or session string in
a Codex prompt or MCP argument.

### 3. Install the Codex plugin

Add this repository as a standard marketplace and install its plugin:

```text
codex plugin marketplace add safal207/telegram-for-codex --ref main
codex plugin add telegram-for-codex@telegram-for-codex
```

This follows the [official OpenAI marketplace
flow](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)
and does not require hand-editing `config.toml` or marketplace JSON.

Restart the ChatGPT desktop app/Codex host, open a new task, and ask:

```text
Use Telegram to show my authorization and safety status.
```

For the developer checkout flow, upgrades, and troubleshooting, see
[docs/LOCAL_PLUGIN.md](docs/LOCAL_PLUGIN.md).

## Safety model

Telegram access is powerful. The defaults are deliberately conservative:

- `telegram_whoami` reports minimized safety status without Telegram account
  identifiers or local paths;
- tools that retrieve private chat content require product approval;
- writes default to `TELEGRAM_ALLOW_WRITES=false`;
- enabling writes requires a non-empty numeric chat allowlist;
- send/edit also require app approval and `confirm=true`;
- Telegram-derived content is untrusted data, never authorization or agent
  instructions;
- local credential directories/files use private POSIX modes where supported;
- the optional rotating audit stores action metadata, not message bodies.

When a read is approved, the requested Telegram content is returned to the
active ChatGPT/Codex task for processing. Review [PRIVACY.md](PRIVACY.md),
[TERMS.md](TERMS.md), and your selected product/workspace data controls before
connecting a sensitive account.

If a session may have leaked, revoke it in Telegram immediately. Full removal
instructions are in [docs/UNINSTALL.md](docs/UNINSTALL.md).

## MCP tools

| Tool | Effect | Default approval |
| --- | --- | --- |
| `telegram_whoami` | authorization and safety status | automatic |
| `telegram_audit_log` | metadata-only write audit tail | prompt |
| `telegram_list_chats` | chat titles and unread counts | prompt |
| `telegram_get_messages` | recent content from one chat | prompt |
| `telegram_search_messages` | global or per-chat search | prompt |
| `telegram_send_message` | send text | prompt + server confirmation |
| `telegram_edit_message` | edit an outgoing text message | prompt + server confirmation |

The server currently exposes seven focused text tools. Media, voice, reactions,
administration, and background mirroring are outside the Personal alpha scope.

## Product tracks

### Personal Mode — active developer alpha

Local Codex uses the bundled STDIO MCP server. A separate single-owner remote
server and phone-first `/connect` flow also exist for private self-hosting, but
the production ChatGPT OAuth deployment has not completed live acceptance.

See:

- [local plugin](docs/LOCAL_PLUGIN.md)
- [remote ChatGPT/Codex architecture](docs/CHATGPT_PLUGIN.md)
- [personal Railway deployment](docs/DEPLOY_PERSONAL_RAILWAY.md)
- [system architecture](docs/ARCHITECTURE.md)

### Public Mode — architecture only

The future multi-user product is an AI secretary for explicitly permitted
private chats through Telegram Business delegation. It is not whole-account
history and it is not available today. The scaffold stays frozen until verified
webhooks, OAuth tenant identity, consent, encrypted storage, deletion controls,
rate limits, and privacy/policy review exist.

See [docs/PUBLIC_MODE.md](docs/PUBLIC_MODE.md).

## Development

```text
python -m pip install --constraint constraints.txt ".[dev]"
pytest -q
```

CI tests Python 3.11/3.12, validates the marketplace/plugin manifests, and
builds the non-root container. The live release gate is stricter than unit CI:

1. PASS-AUTH against the real OAuth deployment;
2. PASS-CONNECT with a dedicated Telegram account;
3. PASS-READ against synthetic test chats;
4. record the real [60-second demo](docs/DEMO.md);
5. only then create a tagged beta release.

## Roadmap

- [x] Local read/search/send/edit vertical slice.
- [x] Approval, allowlist, audit, and untrusted-content boundaries.
- [x] Bundled Codex plugin and repository marketplace.
- [x] Guided local setup and diagnostic doctor.
- [ ] Complete real-account Personal acceptance and publish the demo.
- [ ] Add richer sender/reply context before expanding tool count.
- [ ] Add attachments and voice as separately reviewable capabilities.
- [ ] Configure and verify production OAuth for the single-owner remote path.
- [ ] Keep Public Mode unexposed until every documented prerequisite passes.

## Project

- [Changelog](CHANGELOG.md)
- [Support](SUPPORT.md)
- [Security policy](SECURITY.md)
- [Privacy](PRIVACY.md)
- [Terms](TERMS.md)
- [MIT License](LICENSE)
