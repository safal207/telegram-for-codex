from __future__ import annotations

import asyncio
import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import Settings


async def authorize_string() -> None:
    settings = Settings.from_env()
    client = TelegramClient(StringSession(), settings.api_id, settings.api_hash)
    try:
        await client.start(phone=settings.phone)
        me = await client.get_me()
        session_string = client.session.save()
        print(
            "WARNING: the next line is a Telegram session secret with account access. "
            "Store it only in your hosting secret manager; never commit it or paste it into ChatGPT.",
            file=sys.stderr,
        )
        print(
            f"Authorized {getattr(me, 'username', None) or getattr(me, 'first_name', me.id)} "
            f"(id={me.id}). TELEGRAM_SESSION_STRING:",
            file=sys.stderr,
        )
        print(session_string)
    finally:
        await client.disconnect()


def main() -> None:
    asyncio.run(authorize_string())


if __name__ == "__main__":
    main()
