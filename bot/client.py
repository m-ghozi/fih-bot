from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .cogs.rod_commands import RodCommands
from .cogs.wiki_commands import WikiCommands
from .config import Settings
from .wiki import WikiClient

log = logging.getLogger(__name__)


class FischBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        # Required for prefix (message) commands; enable it in the Developer Portal.
        intents.message_content = True
        super().__init__(
            command_prefix="!",
            intents=intents,
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
        await self.add_cog(RodCommands(self))

        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d commands to guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global commands", len(synced))

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (id: %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Fisch Wiki",
            )
        )

    async def close(self) -> None:
        await self.wiki.close()
        await super().close()
