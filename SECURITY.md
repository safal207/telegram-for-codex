# Security policy

## Supported versions

Security fixes target the current `main` branch and the latest tagged beta.
Older snapshots may not receive fixes.

## Report a vulnerability

Do not open a public issue containing a vulnerability, Telegram content, phone
number, API hash, login code, session file/string, bot token, OAuth secret, or
private log.

Use GitHub's private security-advisory flow for this repository:

https://github.com/safal207/telegram-for-codex/security/advisories/new

Include only the minimum reproduction details. Replace all real credentials,
account identifiers, chat IDs, message bodies, and private URLs with synthetic
values. Reports are handled on a best-effort basis until a formal support SLA is
published.

For ordinary non-sensitive bugs, follow [SUPPORT.md](SUPPORT.md).

## Immediate credential response

If a Telegram session or credential may have leaked, do not wait for a code
fix. Revoke the affected Telegram session from Telegram's active-device
settings, rotate API/OAuth/connect secrets where applicable, stop the MCP
process, and remove the exposed local or hosted credential. See
[docs/UNINSTALL.md](docs/UNINSTALL.md).
