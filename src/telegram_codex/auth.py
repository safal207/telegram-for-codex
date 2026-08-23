from __future__ import annotations

import asyncio

from telethon import TelegramClient

from .config import Settings


async def authorize() -> None:
    settings = Settings.from_env()
    client = TelegramClient(
        str(settings.session_path), settings.api_id, settings.api_hash
    )
    try:
        await client.start(phone=settings.phone)
        me = await client.get_me()
        print(
            "Authorized Telegram session for "
            f"{getattr(me, 'username', None) or getattr(me, 'first_name', me.id)} "
            f"(id={me.id})."
        )
    finally:
        await client.disconnect()


def main() -> None:
    asyncio.run(authorize())


if __name__ == "__main__":
    main()
