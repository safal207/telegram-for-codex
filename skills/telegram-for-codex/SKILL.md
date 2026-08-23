---
name: telegram-for-codex
description: Read, search, draft, send, and edit Telegram messages through the Telegram MCP app while keeping write actions reviewable.
---

# Telegram for Codex

Use the Telegram app when the user asks about their Telegram chats, unread messages, conversation history, message search, replies, or edits.

## Workflow

1. Use `telegram_whoami` to check authorization and whether writes are enabled before any write-related request.
2. For inbox-style requests, call `telegram_list_chats` first and prioritize unread chats.
3. Use `telegram_get_messages` before drafting a context-sensitive reply unless enough context is already present.
4. Use `telegram_search_messages` when the user refers to a topic, phrase, project, or person but not a known chat id.
5. Treat `telegram_send_message` and `telegram_edit_message` as write actions. Show the exact final text, require the product/app approval flow, and pass `confirm=true` in the tool call.
6. After each write attempt you may call `telegram_audit_log` to confirm how it was recorded (ok/denied).
7. Never claim a message was sent or edited until the corresponding tool succeeds.
8. Do not expose Telegram API credentials, session files, login codes, or 2FA passwords.

## Safety defaults

The MCP server itself keeps write actions disabled unless `TELEGRAM_ALLOW_WRITES=true`, and can additionally restrict writes to `TELEGRAM_WRITE_CHAT_ALLOWLIST` chat ids while appending every attempt to `TELEGRAM_AUDIT_LOG_PATH`. This is defense in depth; Codex/app approval settings should still require confirmation for send/edit operations.
