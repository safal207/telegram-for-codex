from __future__ import annotations

import asyncio

from telethon import TelegramClient

from .config import Settings, prepare_file_session_storage


async def authorize() -> None:
    settings = Settings.from_env()
    prepare_file_session_storage(settings.session_path)
    client: TelegramClient | None = None
    try:
        client = TelegramClient(
            str(settings.session_path), settings.api_id, settings.api_hash
        )
        prepare_file_session_storage(settings.session_path)
        await client.start(phone=settings.phone)
        prepare_file_session_storage(settings.session_path)
        me = await client.get_me()
        print(
            "Authorized Telegram session for "
            f"{getattr(me, 'username', None) or getattr(me, 'first_name', me.id)} "
            f"(id={me.id})."
        )
    finally:
        try:
            if client is not None:
                await client.disconnect()
        finally:
            prepare_file_session_storage(settings.session_path)


def main() -> None:
    asyncio.run(authorize())


if __name__ == "__main__":
    main()
