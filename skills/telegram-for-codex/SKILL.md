---
name: telegram-for-codex
description: Read, search, draft, send, and edit Telegram messages through the Telegram MCP app while keeping write actions reviewable.
---

# Telegram for Codex

Use the Telegram app when the user asks about their Telegram chats, unread messages, conversation history, message search, replies, or edits.

## Workflow

1. For inbox-style requests, call `telegram_list_chats` first and prioritize unread chats.
2. Use `telegram_get_messages` before drafting a context-sensitive reply unless enough context is already present.
3. Use `telegram_search_messages` when the user refers to a topic, phrase, project, or person but not a known chat id.
4. Treat `telegram_send_message` and `telegram_edit_message` as write actions. Show the exact final text and require the product/app approval flow before invoking them.
5. Never claim a message was sent or edited until the corresponding tool succeeds.
6. Do not expose Telegram API credentials, session files, login codes, or 2FA passwords.

## Safety defaults

The MCP server itself keeps write actions disabled unless `TELEGRAM_ALLOW_WRITES=true`. This is defense in depth; Codex/app approval settings should still require confirmation for send/edit operations.
