from __future__ import annotations

import json
from pathlib import Path

from telegram_codex import __version__


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "telegram-for-codex"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_repository_marketplace_points_to_packaged_plugin() -> None:
    marketplace = _json(ROOT / ".agents" / "plugins" / "marketplace.json")

    assert marketplace["name"] == "telegram-for-codex"
    assert marketplace["interface"]["displayName"] == "Telegram for Codex"
    assert marketplace["plugins"] == [
        {
            "name": "telegram-for-codex",
            "source": {
                "source": "local",
                "path": "./plugins/telegram-for-codex",
            },
            "policy": {
                "installation": "AVAILABLE",
                "authentication": "ON_INSTALL",
            },
            "category": "Productivity",
        }
    ]
    assert (PLUGIN / ".codex-plugin" / "plugin.json").is_file()
    assert not (ROOT / ".codex-plugin" / "plugin.json").exists()


def test_plugin_manifest_is_release_and_trust_ready() -> None:
    manifest = _json(PLUGIN / ".codex-plugin" / "plugin.json")
    interface = manifest["interface"]

    assert manifest["name"] == "telegram-for-codex"
    assert manifest["version"] == __version__
    assert manifest["mcpServers"] == "./.mcp.json"
    assert manifest["skills"] == "./skills/"
    assert "apps" not in manifest
    assert interface["displayName"] == "Telegram for Codex"
    assert interface["privacyPolicyURL"].startswith("https://")
    assert interface["termsOfServiceURL"].startswith("https://")
    assert (ROOT / "PRIVACY.md").is_file()
    assert (ROOT / "TERMS.md").is_file()
    prompts = interface["defaultPrompt"]
    assert 1 <= len(prompts) <= 3
    assert all(0 < len(prompt) <= 128 for prompt in prompts)


def test_private_reads_and_external_writes_remain_reviewable() -> None:
    mcp = _json(PLUGIN / ".mcp.json")
    server = mcp["mcpServers"]["telegram"]
    tools = server["tools"]

    assert server["command"] == "telegram-codex"
    assert server["default_tools_approval_mode"] == "prompt"
    assert "TELEGRAM_CODEX_CONFIG_FILE" in server["env_vars"]
    assert tools["telegram_whoami"]["approval_mode"] == "auto"
    assert tools["telegram_audit_log"]["approval_mode"] == "prompt"
    for name in (
        "telegram_list_chats",
        "telegram_get_messages",
        "telegram_search_messages",
        "telegram_send_message",
        "telegram_edit_message",
    ):
        assert tools[name]["approval_mode"] == "prompt"
