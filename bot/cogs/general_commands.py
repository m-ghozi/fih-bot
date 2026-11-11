from __future__ import annotations

import math
import platform
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from .. import __version__
from ..ui import truncate
from ..wiki import WikiError

if TYPE_CHECKING:
    from ..client import FischBot

COLOR = discord.Color.from_str("#3ba7d8")
FOOTER = "Source: Official Fisch Wiki • CC BY-NC-SA 4.0"

DEVELOPER_NAME = "m-ghozi"
DEVELOPER_URL = "https://github.com/m-ghozi"
REPOSITORY_URL = "https://github.com/m-ghozi/fih-bot"
WIKI_URL = "https://fischipedia.org/wiki/Fisch_Wiki"

# Short usage strings for the help command.
USAGE: dict[str, str] = {
    "wiki": "{p}wiki <query>",
    "page": "{p}page <title>",
    "fish": "{p}fish <name>",
    "codes": "{p}codes [active|inactive|all]",
    "rod": "{p}rod <name>",
    "enchant": "{p}enchant <name>",
    "status": "{p}status",
    "info": "{p}info",
    "help": "{p}help [command]",
}

COG_LABELS: dict[str, str] = {
    "WikiCommands": "📚 Wiki",
    "RodCommands": "🎣 Rods",
    "GeneralCommands": "⚙️ General",
}


def _format_duration(seconds: float) -> str:
    total = int(max(seconds, 0))
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def _latency_color(latency_ms: float) -> discord.Color:
    if latency_ms < 150:
        return discord.Color.from_str("#2ecc71")
    if latency_ms < 300:
        return discord.Color.from_str("#f1c40f")
    return discord.Color.from_str("#e74c3c")


class GeneralCommands(commands.Cog):
    """Utility commands about the bot itself."""

    def __init__(self, bot: "FischBot") -> None:
        self.bot = bot

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _command_line(command: commands.Command, prefix: str) -> str:
        usage = USAGE.get(command.name, f"{prefix}{command.name}")
        usage = usage.format(p=prefix)
        description = command.description or command.short_doc or "No description."
        return f"`{usage}`\n{truncate(description, 160)}"

    def _help_pages(self, prefix: str) -> list[discord.Embed]:
        groups: dict[str, list[commands.Command]] = {}
        for command in self.bot.commands:
            cog_name = command.cog.__class__.__name__ if command.cog else "GeneralCommands"
            groups.setdefault(cog_name, []).append(command)

        embed = discord.Embed(
            title="📖 Fisch Wiki Bot — Help",
            description=(
                f"All commands work as prefix (`{prefix}`) or slash (`/`).\n"
                f"Use `{prefix}help <command>` or `/help command:<name>` "
                "for details about one command."
            ),
            color=COLOR,
        )
        for cog_name, label in COG_LABELS.items():
            commands_in_cog = sorted(groups.pop(cog_name, []), key=lambda c: c.name)
            if not commands_in_cog:
                continue
            value = "\n\n".join(
                self._command_line(command, prefix) for command in commands_in_cog
            )
            embed.add_field(name=label, value=value, inline=False)
        for cog_name, remaining in groups.items():
            value = "\n\n".join(
                self._command_line(command, prefix)
                for command in sorted(remaining, key=lambda c: c.name)
            )
            embed.add_field(name=cog_name, value=value, inline=False)

        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • {len(self.bot.commands)} commands")
        return [embed]

    @staticmethod
    def _command_detail(command: commands.Command, prefix: str) -> discord.Embed:
        usage = USAGE.get(command.name, f"{prefix}{command.name}").format(p=prefix)
        embed = discord.Embed(
            title=f"📖 {prefix}{command.name} / /{command.name}",
            description=command.description or command.short_doc or "No description.",
            color=COLOR,
        )
        embed.add_field(name="Usage", value=f"`{usage}`", inline=False)
        parameters = list(command.clean_params.values())
        if parameters:
            lines = []
            for parameter in parameters:
                if parameter.default is parameter.empty:
                    requirement = "required"
                else:
                    requirement = "optional"
                    if parameter.default not in (None, ""):
                        requirement += f", default `{parameter.default}`"
                lines.append(f"`{parameter.name}` — {requirement}")
            embed.add_field(name="Parameters", value="\n".join(lines), inline=False)
        embed.add_field(
            name="Slash version",
            value=f"`/{command.name}` with autocomplete where available.",
            inline=False,
        )
        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • {FOOTER}")
        return embed

    # ----------------------------------------------------------- commands

    @commands.hybrid_command(
        name="status", description="Show bot health, latency, and server information"
    )
    async def status(self, ctx: commands.Context) -> None:
        await ctx.defer()
        now = datetime.now(timezone.utc)
        latency = self.bot.latency
        if latency is None or math.isnan(latency):
            websocket_ms = None
            embed_color = COLOR
        else:
            websocket_ms = latency * 1000
            embed_color = _latency_color(websocket_ms)

        try:
            wiki_ms = await self.bot.wiki.ping()
            wiki_value = f"{wiki_ms:.0f} ms"
            health = "🟢 Operational"
        except WikiError:
            wiki_value = "unreachable"
            health = "🟡 Wiki API issue"

        uptime = now - self.bot.started_at
        users = sum(guild.member_count or 0 for guild in self.bot.guilds)

        embed = discord.Embed(
            title="📊 Bot Status",
            color=embed_color,
            timestamp=now,
        )
        embed.add_field(name="Health", value=health, inline=True)
        websocket_value = (
            f"{websocket_ms:.0f} ms" if websocket_ms is not None else "not connected"
        )
        embed.add_field(
            name="Latency",
            value=f"WebSocket: **{websocket_value}**\nWiki API: **{wiki_value}**",
            inline=True,
        )
        embed.add_field(name="Uptime", value=_format_duration(uptime.total_seconds()), inline=True)
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(name="Users", value=f"{users:,}", inline=True)
        embed.add_field(name="Commands", value=f"{len(self.bot.commands):,}", inline=True)

        guild = ctx.guild
        if guild is not None:
            details = [
                f"**{guild.name}**",
                f"ID: `{guild.id}`",
                f"Members: {guild.member_count or 'unknown'}",
                f"Boost level: {guild.premium_tier}",
            ]
            embed.add_field(name="This server", value="\n".join(details), inline=False)

        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • {FOOTER}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="info", description="Show developer and project information"
    )
    async def info(self, ctx: commands.Context) -> None:
        bot_user = self.bot.user
        name = bot_user.name if bot_user else "Fisch Wiki Bot"
        embed = discord.Embed(
            title=f"ℹ️ About {name}",
            description=(
                "A Discord bot that fetches live data from the "
                f"[Official Fisch Wiki]({WIKI_URL}) through the MediaWiki API."
            ),
            color=COLOR,
        )
        embed.add_field(
            name="Developer",
            value=f"[{DEVELOPER_NAME}]({DEVELOPER_URL})",
            inline=True,
        )
        embed.add_field(
            name="Source code",
            value=f"[GitHub repository]({REPOSITORY_URL})",
            inline=True,
        )
        embed.add_field(
            name="Feedback",
            value=f"[Open an issue]({REPOSITORY_URL}/issues)",
            inline=True,
        )
        embed.add_field(
            name="Built with",
            value=(
                f"Python {platform.python_version()}\n"
                f"discord.py {discord.__version__}"
            ),
            inline=True,
        )
        embed.add_field(name="Version", value=f"v{__version__}", inline=True)
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(
            name="Data source",
            value=(
                f"[Official Fisch Wiki]({WIKI_URL})\n"
                "Content licensed under CC BY-NC-SA 4.0."
            ),
            inline=False,
        )
        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • Made with discord.py")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="help", description="List every command or show details for one"
    )
    @app_commands.describe(command="Optional: show detailed help for this command")
    async def help(
        self, ctx: commands.Context, *, command: str | None = None
    ) -> None:
        prefix = ctx.prefix or "!"
        if command:
            target = self.bot.get_command(command.strip().lstrip("!/"))
            if target is None or target.hidden:
                await ctx.send(
                    embed=discord.Embed(
                        title="Command not found",
                        description=(
                            f"No command named **{command}**. "
                            f"Run `{prefix}help` to list every command."
                        ),
                        color=discord.Color.orange(),
                    )
                )
                return
            await ctx.send(embed=self._command_detail(target, prefix))
            return

        await ctx.send(embed=self._help_pages(prefix)[0])

    @help.autocomplete("command")
    async def help_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        query = current.strip().lstrip("!/").lower()
        names = sorted(command.name for command in self.bot.commands)
        return [
            app_commands.Choice(name=name, value=name)
            for name in names
            if query in name.lower()
        ][:25]
