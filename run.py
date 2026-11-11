#!/usr/bin/env python3
"""Entry point for the Fisch Wiki Discord bot."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import discord

from bot.client import FischBot
from bot.config import Settings


async def run_bot(settings: Settings) -> None:
    bot = FischBot(settings)
    try:
        await bot.start(settings.token)
    finally:
        await bot.wiki.close()


def configure_logging() -> None:
    """Log to stdout (journald) and optionally to a rotating file."""
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    log_file = os.getenv("LOG_FILE", "").strip()
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def main() -> int:
    configure_logging()

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
