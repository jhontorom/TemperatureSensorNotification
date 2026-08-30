"""Print chat IDs from recent bot updates without printing the bot token."""

from __future__ import annotations

import asyncio
import os
import sys

from telegram import Bot
from telegram.error import TelegramError

from room_monitor.telegram_bot import build_ipv4_request


async def find_chat_ids() -> int:
    token = os.getenv("ROOM_MONITOR_TELEGRAM_BOT_TOKEN")
    if not token:
        print("ROOM_MONITOR_TELEGRAM_BOT_TOKEN is not set.", file=sys.stderr)
        return 2

    try:
        async with Bot(
            token,
            request=build_ipv4_request(),
            get_updates_request=build_ipv4_request(),
        ) as bot:
            updates = await bot.get_updates(timeout=10)
    except TelegramError as exc:
        print(f"Unable to retrieve Telegram updates: {type(exc).__name__}", file=sys.stderr)
        return 1

    chats = {
        (update.effective_chat.id, update.effective_chat.type)
        for update in updates
        if update.effective_chat is not None
    }
    if not chats:
        print("No recent chats found. Send the bot a message, then run this command again.")
        return 1

    for chat_id, chat_type in sorted(chats):
        print(f"Chat ID: {chat_id} (type: {chat_type})")
    return 0


def main() -> int:
    return asyncio.run(find_chat_ids())


if __name__ == "__main__":
    sys.exit(main())
