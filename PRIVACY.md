# Privacy

Telegram for Codex is an open-source, self-hosted developer alpha. The project
maintainer does not operate a hosted Personal Mode service and does not receive
telemetry from the local plugin.

## What data moves where

- The local MCP server connects to Telegram with the API credentials and user
  session stored on the user's machine.
- When the user approves a read tool, only the requested Telegram data is
  returned to the active ChatGPT/Codex task for processing.
- The automatic authorization-status check returns only minimized safety
  fields. It excludes Telegram profile identifiers, usernames, phone numbers,
  chat data, and absolute local paths.
- A send or edit reaches Telegram only after writes are enabled for an explicit
  chat allowlist, the final action is approved, and the tool receives
  `confirm=true`.
- Telegram-derived content is untrusted external data. It is never treated as
  authorization or as instructions for the agent.

Processing performed by Telegram and by the selected ChatGPT/Codex account or
workspace is governed by those services' policies and the user's data controls.
Do not connect an account whose content you are not authorized to process.

## Local storage

The default local directory is `~/.telegram-codex/`. It may contain:

- `config.env`: Telegram API configuration and private file locations;
- `data/codex.session`: the Telethon login session;
- `data/audit.jsonl` plus up to two rotated backups: write-attempt metadata.

The audit excludes message text, previews, Telegram payloads, and raw exception
bodies. It can be disabled. On POSIX, the runtime requires private directory and
file modes. On Windows, the user is responsible for keeping these files in a
private profile and applying an appropriate ACL.

The local plugin has no analytics or advertising SDK. Public Mode is not an
available product and does not collect customer data.

## Retention and deletion

Telegram content is fetched on demand and is not copied into a local search
index by this project. ChatGPT/Codex conversation retention is controlled by
the user's account or workspace. To remove the local integration and its
credentials, follow [docs/UNINSTALL.md](docs/UNINSTALL.md).

Self-hosted remote deployments are operated by whoever deploys them. That
operator is responsible for access controls, logs, retention, disclosures, and
applicable law.

## Changes and questions

Material privacy changes will be recorded in the repository. For non-sensitive
questions, use the support process in [SUPPORT.md](SUPPORT.md). Never post a
Telegram session, login code, API hash, chat content, or OAuth secret publicly.
