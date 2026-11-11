#!/usr/bin/env python3
"""Entry point for the Fisch Wiki Discord bot."""

from __future__ import annotations

import asyncio
import logging
import sys

import discord

from bot.client import FischBot
from bot.config import Settings


async def run_bot(settings: Settings) -> None:
    bot = FischBot(settings)
    try:
        await bot.start(settings.token)
    finally:
        await bot.wiki.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    settings = Settings.load()
    if not settings.token:
        print(
            "DISCORD_TOKEN is not set.\n"
            "Copy .env.example to .env and fill in your bot token.",
            file=sys.stderr,
        )
        return 1

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        print("\nBot stopped.")
    except discord.LoginFailure:
        print(
            "Invalid Discord token. Check the DISCORD_TOKEN value in .env.",
            file=sys.stderr,
        )
        return 1
    except discord.PrivilegedIntentsRequired:
        print(
            "The bot requires a privileged intent that is not enabled.\n"
            "Open Discord Developer Portal > Bot > Privileged Gateway Intents.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
