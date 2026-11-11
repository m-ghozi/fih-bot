from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from .. import __version__
from ..schedule import (
    SPAWNS,
    format_duration,
    next_occurrence,
    season_schedule,
    seconds_until,
)
from ..ui import truncate

if TYPE_CHECKING:
    from ..client import FischBot

COLOR = discord.Color.from_str("#3ba7d8")
FOOTER = "Source: Official Fisch Wiki • CC BY-NC-SA 4.0"

SEASON_EMOJI = {
    "Spring": "🌸",
    "Summer": "☀️",
    "Autumn": "🍂",
    "Winter": "❄️",
}

SEASON_COLOR = {
    "Spring": discord.Color.from_str("#7ed957"),
    "Summer": discord.Color.from_str("#facc15"),
    "Autumn": discord.Color.from_str("#fb923c"),
    "Winter": discord.Color.from_str("#3b82f6"),
}


def _timestamp(moment, style: str = "F") -> str:
    return f"<t:{int(moment.timestamp())}:{style}>"


class ScheduleCommands(commands.Cog):
    """Season and spawn schedules computed locally from fixed wiki data."""

    def __init__(self, bot: "FischBot") -> None:
        self.bot = bot

    # ----------------------------------------------------------- commands

    @commands.hybrid_command(
        name="seasons", description="Show the current and upcoming Fisch seasons"
    )
    async def seasons(self, ctx: commands.Context) -> None:
        schedule = season_schedule()
        current = next(season for season in schedule if season.current)

        lines: list[str] = []
        for season in schedule:
            emoji = SEASON_EMOJI[season.name]
            if season.current:
                ends_in = format_duration(seconds_until(season.end))
                lines.append(
                    f"{emoji} **{season.name}** — current, ends {_timestamp(season.end, 'R')}"
                    f" ({ends_in})"
                )
            else:
                starts_in = format_duration(seconds_until(season.start))
                lines.append(
                    f"{emoji} **{season.name}** — starts {_timestamp(season.start, 'R')}"
                    f" ({starts_in})"
                )

        embed = discord.Embed(
            title="🌍 Season Schedule",
            description=(
                "Seasons are universal across all servers. "
                "Each season lasts **9.6 hours** (576 minutes)."
            ),
            color=SEASON_COLOR[current.name],
            timestamp=current.start,
        )
        embed.add_field(
            name=f"{SEASON_EMOJI[current.name]} Current season",
            value=f"**{current.name}**",
            inline=True,
        )
        embed.add_field(
            name="Ends in",
            value=f"{format_duration(seconds_until(current.end))} "
            f"({_timestamp(current.end, 'f')})",
            inline=True,
        )
        embed.add_field(name="Rotation", value="Spring → Summer → Autumn → Winter", inline=True)
        embed.add_field(name="Schedule", value="\n".join(lines), inline=False)
        embed.add_field(
            name="Season effects",
            value=(
                "• **+25%** spawn rate for fish that prefer the current season\n"
                "• **-15%** spawn rate for other fish\n"
                "• The Seasons Rod adds **+40%** for seasonal fish"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • {FOOTER}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="spawn", description="Show upcoming global spawns and reset timers"
    )
    async def spawn(self, ctx: commands.Context) -> None:
        soonest = None
        for spawn in SPAWNS:
            moment = next_occurrence(spawn.period)
            if soonest is None or moment < soonest:
                soonest = moment

        embed = discord.Embed(
            title="🌊 Spawn Schedule",
            description=(
                "Recurring global spawns and resets. All timers are universal "
                "and follow the wiki's **Upcoming** schedule; times are shown "
                "in your own timezone."
            ),
            color=COLOR,
            timestamp=soonest,
        )
        for spawn in SPAWNS:
            moment = next_occurrence(spawn.period)
            embed.add_field(
                name=f"{spawn.emoji} {spawn.detail}",
                value=(
                    f"Next: {_timestamp(moment, 'R')}\n"
                    f"{_timestamp(moment, 'f')}\n"
                    f"Every {format_duration(spawn.period)}"
                ),
                inline=True,
            )
        embed.add_field(
            name="Note",
            value=truncate(
                "These timers count down to the next spawn or reset. "
                "Spawning is handled by the game, so a short delay is possible.",
                200,
            ),
            inline=False,
        )
        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • {FOOTER}")
        await ctx.send(embed=embed)
