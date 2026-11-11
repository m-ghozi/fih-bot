from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

import discord
from discord import app_commands
from discord.ext import commands

from ..parsing import (
    extract_section,
    extract_template_version,
    parse_infobox,
)
from ..ui import truncate
from ..wiki import WikiError

if TYPE_CHECKING:
    from ..client import FischBot

log = logging.getLogger(__name__)

COLOR = discord.Color.from_str("#3ba7d8")
FOOTER = "Source: Official Fisch Wiki • CC BY-NC-SA 4.0"

# (embed label, RodInfobox parameter, formatter)
def _format_price(value: str) -> str:
    raw = value.replace(",", "").strip()
    return f"C${int(raw):,}" if raw.isdigit() else value


def _format_weight(value: str) -> str:
    if value.strip().lower() in {"inf", "infinite", "∞"}:
        return "Infinite"
    return f"{value}kg"


ROD_STATS: list[tuple[str, str, Callable[[str], str]]] = [
    ("Stage", "stage", lambda v: f"Stage {v}"),
    ("Source", "source", str),
    ("Price", "price", _format_price),
    ("Journal", "journal", str),
    ("Entry XP", "entryxp", str),
    ("Lure Speed", "lure", lambda v: f"{v}%"),
    ("Luck", "luck", lambda v: f"{v}%"),
    ("Control", "control", str),
    ("Resilience", "resilience", lambda v: f"{v}%"),
    ("Max Kg", "max_weight", _format_weight),
    ("Line Distance", "line_dist", str),
    ("Disturbance", "disturbance", lambda v: v if v.startswith("+") else f"+{v}"),
    ("Tags", "tags", str),
]

# (Enchanting parameter prefix, embed field label)
ENCHANT_GROUPS: list[tuple[str, str]] = [
    ("keeper", "For Keeperbound"),
    ("optimal", "For Optimal Grinding"),
    ("misc", "Other options"),
]


def _ability_lines(section: str) -> list[str]:
    box = parse_infobox(section, "Ability")
    if not box:
        return []
    return [value for value in box.values() if value]


def _enchant_groups(box: dict[str, str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {prefix: [] for prefix, _ in ENCHANT_GROUPS}
    for prefix, _ in ENCHANT_GROUPS:
        for index in range(1, 6):
            value = box.get(f"{prefix}{index}", "").strip()
            note = box.get(f"{prefix}note{index}", "").strip()
            if value:
                line = f"• {value}"
                if note:
                    line += f"\n  ↳ {note}"
                groups[prefix].append(line)
            elif note:
                groups[prefix].append(f"• ↳ {note}")
    return groups


def _add_lines_field(embed: discord.Embed, name: str, lines: list[str]) -> None:
    """Add lines as one or more embed fields, respecting the 1024 char limit."""
    if not lines:
        return

    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) > 1000 and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)

    for index, chunk in enumerate(chunks, start=1):
        label = name if len(chunks) == 1 else f"{name} ({index}/{len(chunks)})"
        embed.add_field(name=label, value=chunk, inline=False)


class RodCommands(commands.Cog):
    def __init__(self, bot: "FischBot") -> None:
        self.bot = bot
        self.wiki = bot.wiki

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _not_rod_embed(title: str, command: str) -> discord.Embed:
        return discord.Embed(
            title="Not a fishing rod page",
            description=(
                f"**{title}** has no rod infobox. "
                f"Try `!{command} <rod name>` with a valid rod, e.g. `Trident Rod`."
            ),
            color=discord.Color.orange(),
        )

    async def _send(self, ctx: commands.Context, embed: discord.Embed) -> None:
        await ctx.send(embed=embed)

    async def _rod_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            names = await self.wiki.category_members("Fishing Rods")
        except WikiError:
            return []
        current_lower = current.lower()
        matches = [name for name in names if current_lower in name.lower()]
        return [
            app_commands.Choice(name=name[:100], value=name[:100])
            for name in matches[:25]
        ]

    # ----------------------------------------------------------- commands

    @commands.hybrid_command(
        name="rod", description="Show stats and ability of a fishing rod"
    )
    @app_commands.describe(name="Rod name, e.g. 'Trident Rod'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def rod(self, ctx: commands.Context, *, name: str) -> None:
        await ctx.defer()
        title, wikitext = await self.wiki.wikitext(name)
        box = parse_infobox(wikitext, "RodInfobox")
        if box is None:
            await self._send(ctx, self._not_rod_embed(title, "rod"))
            return

        info = await self.wiki.page(title)
        embed = discord.Embed(
            title=box.get("name") or title,
            url=self.wiki.page_url(title),
            description=truncate(info.extract, 500) if info.extract else None,
            color=COLOR,
        )
        if info.thumbnail:
            embed.set_thumbnail(url=info.thumbnail)

        for label, key, formatter in ROD_STATS:
            value = box.get(key)
            if not value:
                continue
            embed.add_field(
                name=label, value=truncate(formatter(value), 200), inline=True
            )

        abilities = _ability_lines(extract_section(wikitext, "Ability"))
        _add_lines_field(embed, "Ability", abilities)

        embed.set_footer(text=FOOTER)
        await self._send(ctx, embed)

    @rod.autocomplete("name")
    async def rod_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._rod_autocomplete(interaction, current)

    @commands.hybrid_command(
        name="enchant",
        description="Show recommended enchantments for a fishing rod",
    )
    @app_commands.describe(name="Rod name, e.g. 'Trident Rod'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def enchant(self, ctx: commands.Context, *, name: str) -> None:
        await ctx.defer()
        title, wikitext = await self.wiki.wikitext(name)
        section = extract_section(wikitext, "Enchanting")

        if not section or parse_infobox(section, "Enchanting") is None:
            await ctx.send(
                embed=discord.Embed(
                    title="No enchantment recommendations",
                    description=(
                        f"The wiki does not list recommended enchantments for **{title}**."
                    ),
                    color=discord.Color.orange(),
                )
            )
            return

        box = parse_infobox(section, "Enchanting") or {}
        groups = _enchant_groups(box)
        if not any(groups.values()):
            await ctx.send(
                embed=discord.Embed(
                    title="No enchantment recommendations",
                    description=(
                        f"The wiki does not list recommended enchantments for **{title}**."
                    ),
                    color=discord.Color.orange(),
                )
            )
            return

        version = extract_template_version(section)
        embed = discord.Embed(
            title=f"Recommended Enchantments — {title}",
            url=self.wiki.page_url(title),
            color=COLOR,
        )
        thumbnail = await self.wiki.thumbnail(title)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        for prefix, label in ENCHANT_GROUPS:
            _add_lines_field(embed, label, groups[prefix])

        footer = FOOTER + (f" • for v{version}" if version else "")
        embed.set_footer(text=footer)
        await self._send(ctx, embed)

    @enchant.autocomplete("name")
    async def enchant_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._rod_autocomplete(interaction, current)
