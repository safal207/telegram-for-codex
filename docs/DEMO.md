# Honest 60-second demo runbook

Record this only against a dedicated test chat with synthetic messages. Never
show API credentials, phone numbers, login codes, session paths, private chat
names, real message text, or the contents of `config.env`.

## Preconditions

- `telegram-codex-doctor` has no FAIL results;
- the plugin is installed in a new Codex task;
- one synthetic test chat contains harmless unread messages;
- before recording, writes are enabled only for that synthetic test chat and
  Codex has been restarted; tool approval and `confirm=true` still apply.

## Storyboard

### 0–10 seconds — promise

Show the plugin card and title:

> Private Telegram inbox for Codex. Reads and writes stay reviewable.

### 10–28 seconds — unread triage

Prompt:

> Show my unread Telegram chats and summarize only the test chat.

Approve the private read. Show a short summary with no unrelated chats.

### 28–43 seconds — find context

Prompt:

> Find the synthetic message about Project Aurora and quote only the relevant sentence.

Approve search. Show the correct synthetic result.

### 43–60 seconds — safe reply

Prompt:

> Draft a reply saying the Aurora review is tomorrow. Do not send it.

Show that drafting causes no write. Then explicitly ask to send, show the exact
recipient/text approval, approve it, and show the successful tool result plus a
metadata-only audit record.

## Publish only when

- the flow was captured from the real product rather than mocked UI;
- no secret or personal data appears in frames, captions, terminal history, or
  metadata;
- the README statements match the recorded build;
- PASS-AUTH/PASS-CONNECT/PASS-READ are recorded for the same release candidate.
