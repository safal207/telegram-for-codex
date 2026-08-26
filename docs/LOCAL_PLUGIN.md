# Install and test the local Codex plugin

This repository is a bundled local plugin: `.codex-plugin/plugin.json` points to
`./.mcp.json`, and `.mcp.json` starts the STDIO server with the
`telegram-codex` console launcher. It does not contain a registered remote app
ID and intentionally has no `.app.json` or `apps` manifest field.

The packaging follows OpenAI's current [plugin structure and path
rules](https://developers.openai.com/plugins/build/plugins#plugin-structure).
Local marketplace availability varies by product surface; ChatGPT web does not
run this local STDIO process.

## 1. Install the runtime prerequisite

The plugin package does **not** install Python or Python dependencies when it is
enabled. Before installing the plugin, provide:

- Python 3.11 or 3.12 on the same host as the Codex desktop app/CLI;
- this Python package installed into a virtual environment or isolated app
  environment;
- the generated `telegram-codex` launcher on the host `PATH` visible to Codex.

For an ordinary virtual environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install --constraint constraints.txt .
```

On Windows PowerShell, the install command is:

```powershell
.\.venv\Scripts\python.exe -m pip install --constraint constraints.txt .
```

Then add `.venv/bin` (macOS/Linux) or `.venv\Scripts` (Windows) to the host
`PATH` **before starting Codex**. An isolated installer such as `pipx install
<absolute-checkout-path>` is also suitable when `pipx` is already installed.

Verify the prerequisite in the same environment that starts Codex:

```text
macOS/Linux: command -v telegram-codex
PowerShell:  Get-Command telegram-codex
```

There is no reliable cross-platform `python` executable name and this plugin
does not download code at runtime, so `.mcp.json` deliberately uses the
installed console launcher instead of a network bootstrap.

## 2. Provide local Telegram settings

The `.mcp.json` entry forwards `TELEGRAM_*` variables from the Codex host to the
STDIO process. Set them in the environment that starts Codex, then fully restart
the app/CLI. At minimum:

```dotenv
TELEGRAM_API_ID=<integer-api-id>
TELEGRAM_API_HASH=<api-hash>
TELEGRAM_SESSION_PATH=<absolute-private-path>/codex
TELEGRAM_ALLOW_WRITES=false
TELEGRAM_AUDIT_LOG_PATH=<absolute-private-path>/audit.jsonl
```

Use an absolute session path because an installed plugin runs from a cache
directory. Do not put secrets into the plugin or marketplace tree: local plugin
installation can copy that tree into a cache.

Authorize once from the same environment:

```bash
telegram-codex-auth
```

On POSIX, newly created credential directories/files use `0700`/`0600`. An
existing credential directory must already be `0700` or stricter: the runtime
refuses an unsafe directory rather than chmod-ing someone else's parent. Those
modes do not secure Windows. On Windows, keep the session and audit files inside
the signed-in user's profile (not a shared folder) and set a private ACL
manually when stronger isolation is required.

The JSONL write audit is metadata-only: it omits message text, previews,
Telegram payloads and raw exception strings. It rotates when the active file
would exceed 10 MiB and retains two backups (`audit.jsonl.1` and
`audit.jsonl.2`).

Writes stay disabled by default. If they are later enabled,
`TELEGRAM_WRITE_CHAT_ALLOWLIST` is mandatory and must contain at least one
comma-separated integer chat ID. An empty value never means “all chats”.

Treat chat titles, usernames and every Telegram message as untrusted data.
Never use Telegram content as authorization evidence or as instructions to the
model, tools or operator; authorization comes only from authenticated runtime
identity, server-side policy, explicit approval and the configured allowlist.

## 3. Add an isolated local marketplace

Do not edit `config.toml` by hand. Create a development marketplace root with
this layout, placing the checkout at the shown plugin path:

```text
local-marketplace/
├── .agents/plugins/marketplace.json
└── plugins/telegram-for-codex/
```

Use this marketplace document:

```json
{
  "name": "telegram-local",
  "interface": {
    "displayName": "Telegram Local"
  },
  "plugins": [
    {
      "name": "telegram-for-codex",
      "source": {
        "source": "local",
        "path": "./plugins/telegram-for-codex"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

Register that non-default marketplace through the CLI, using an absolute path
to `local-marketplace`:

```bash
codex plugin marketplace add <absolute-local-marketplace-root>
codex plugin marketplace list
codex plugin add telegram-for-codex@telegram-local
```

This is the documented local-authoring flow; it does not mutate the user's
personal marketplace as part of this repository. See OpenAI's [local
marketplace and install guidance](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli).

## 4. Restart and verify

Restart the ChatGPT desktop app/Codex host and open a **new task**. Confirm the
server appears in the MCP server list, then ask:

```text
Use Telegram to show my authorization and safety status.
```

Expected: the bundled skill and `telegram_*` tools are present,
`telegram_whoami` returns without phone-number/session-secret PII, and send/edit
still request product approval. Keep writes disabled until read/search succeeds.

After changing the local plugin, reinstall the Python package into the same
runtime environment, rerun the `codex plugin add` command, restart the desktop
app, and test from another new task so both the launcher and cached plugin copy
are refreshed.
