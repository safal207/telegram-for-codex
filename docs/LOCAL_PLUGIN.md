# Install and test the local Codex plugin

The repository is both a Python project and a standard Codex marketplace:

```text
.agents/plugins/marketplace.json
plugins/telegram-for-codex/
├── .codex-plugin/plugin.json
├── .mcp.json
└── skills/telegram-for-codex/SKILL.md
```

The bundled `.mcp.json` starts the installed `telegram-codex` STDIO launcher.
ChatGPT web cannot run that local process. The remote ChatGPT path is a separate
single-owner alpha described in [CHATGPT_PLUGIN.md](CHATGPT_PLUGIN.md).

## 1. Install the launcher

Python 3.11 or newer is required; CI currently covers 3.11/3.12. The recommended
developer-alpha install uses `pipx`. First follow the [official pipx install
guide](https://pipx.pypa.io/latest/how-to/install-pipx.html), then run:

```text
pipx ensurepath
```

Open a new terminal and install:

```text
pipx install "git+https://github.com/safal207/telegram-for-codex.git@main"
```

Verify from the same user account that starts Codex:

```text
PowerShell:  Get-Command telegram-codex
macOS/Linux: command -v telegram-codex
```

For a development checkout, create/activate a virtual environment and run:

```text
python -m pip install --constraint constraints.txt -e ".[dev]"
```

The Codex host must inherit that environment, or its scripts directory must be
on PATH. The plugin intentionally does not download or execute package code at
runtime.

## 2. Create the private configuration

Run the guided setup in a real terminal:

```text
telegram-codex-setup
```

It writes the default user config to:

```text
~/.telegram-codex/config.env
```

Use `TELEGRAM_CODEX_CONFIG_FILE` only when you intentionally need another
absolute location. Explicit `TELEGRAM_*` environment variables override file
values. Never place the config or session inside the marketplace/plugin cache.

The setup keeps writes disabled and uses private defaults for the Telethon
session and metadata-only audit. On POSIX, existing credential directories must
already be mode `0700` or stricter. On Windows, keep them in the signed-in
profile and apply a private ACL when stronger isolation is required.

Authorize once:

```text
telegram-codex-auth
telegram-codex-doctor
```

Telegram normally delivers the login code through an existing Telegram client.
Enter it only in the terminal prompt. Never send it, the API hash, the 2FA
password, or a session string through Codex.

## 3. Add the repository marketplace

For the published `main` snapshot:

```text
codex plugin marketplace add safal207/telegram-for-codex --ref main
codex plugin add telegram-for-codex@telegram-for-codex
```

For an unmerged local checkout, use its absolute repository root instead:

```text
codex plugin marketplace add <absolute-repository-root>
codex plugin add telegram-for-codex@telegram-for-codex
```

Do not edit `config.toml` or marketplace JSON by hand. Confirm the source with:

```text
codex plugin marketplace list
codex plugin list
```

## 4. Restart and activate

Restart the ChatGPT desktop app/Codex host and open a new task. First ask:

```text
Use Telegram to show my authorization and safety status.
```

Expected:

- seven `telegram_*` tools are available;
- `telegram_whoami` reports minimized authorization/safety status without
  Telegram profile identifiers or local paths;
- private read tools request approval;
- writes remain disabled.

Then approve a harmless read against a dedicated test chat:

```text
Show my unread Telegram chats and summarize only the test chat.
```

## 5. Enable writes only for a test chat

Do this only after read/search works. Update the private config with:

```dotenv
TELEGRAM_ALLOW_WRITES=true
TELEGRAM_WRITE_CHAT_ALLOWLIST=<one-numeric-test-chat-id>
```

Restart Codex. Ask for a draft first, verify the recipient and exact final text,
then approve one harmless send. Empty allowlists never mean all chats. Product
approval and `confirm=true` remain mandatory even after writes are enabled.

## Update a developer-alpha checkout

Update the Python package, refresh the marketplace, and reinstall the cached
plugin copy:

```text
pipx upgrade telegram-for-codex
codex plugin marketplace upgrade telegram-for-codex
codex plugin add telegram-for-codex@telegram-for-codex
```

For editable development environments, reinstall/update the checkout instead
of the `pipx` command. Restart Codex and use a new task after every plugin
manifest/skill/MCP change.

### Migrating from a `0.2.x` local checkout

`0.3.0` moves the plugin bundle from the repository root into the standard
`plugins/telegram-for-codex/` marketplace layout. If an older checkout was
added as a marketplace, remove that cached installation first, update the
checkout, then add the repository marketplace and plugin again with the
commands above. Your Python config and Telegram session are not stored in the
plugin cache and should not be copied into it.

## Diagnose and remove

Run `telegram-codex-doctor` before opening a support issue. It reports named
checks without printing credentials. Follow [UNINSTALL.md](UNINSTALL.md) to
remove the plugin, revoke Telegram access, and delete only the confirmed local
credential files.
