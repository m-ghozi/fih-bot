#!/usr/bin/env python3
"""Entry point bot Discord Fisch Wiki."""

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
            "DISCORD_TOKEN belum diisi.\n"
            "Salin .env.example menjadi .env lalu isi token bot kamu.",
            file=sys.stderr,
        )
        return 1

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        print("\nBot dihentikan.")
    except discord.LoginFailure:
        print(
            "Token Discord tidak valid. Periksa kembali nilai DISCORD_TOKEN di .env.",
            file=sys.stderr,
        )
        return 1
    except discord.PrivilegedIntentsRequired:
        print(
            "Bot membutuhkan privileged intent yang belum diaktifkan.\n"
            "Buka Discord Developer Portal > Bot > Privileged Gateway Intents.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
