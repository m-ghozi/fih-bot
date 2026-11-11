from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .cogs.wiki_commands import WikiCommands
from .config import Settings
from .wiki import WikiClient

log = logging.getLogger(__name__)


class FischBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            help_command=None,
        )
        self.settings = settings
        self.wiki = WikiClient(
            settings.api_url,
            settings.user_agent,
            base_url=settings.base_url,
        )

    async def setup_hook(self) -> None:
        await self.add_cog(WikiCommands(self))

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Sinkron %d command ke guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Sinkron %d command global", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Login sebagai %s (id: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Fisch Wiki",
            )
        )

    async def close(self) -> None:
        await self.wiki.close()
        await super().close()
