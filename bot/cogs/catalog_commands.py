from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Iterable, Sequence

import discord
from discord import app_commands
from discord.ext import commands

from .. import __version__
from ..catalogs import (
    Bait,
    Harpoon,
    Mutation,
    Spear,
    format_weight,
    load_baits,
    load_harpoons,
    load_mutations,
    load_obtainment,
    load_spears,
)
from ..ui import Paginator, Picker, truncate
from ..wiki import WikiError

if TYPE_CHECKING:
    from ..client import FischBot

COLOR = discord.Color.from_str("#3ba7d8")
FOOTER = "Source: Official Fisch Wiki • CC BY-NC-SA 4.0"

RARITY_COLORS = {
    "trash": "#8a8a8a",
    "common": "#95a5a6",
    "uncommon": "#2ecc71",
    "unusual": "#1abc9c",
    "rare": "#3498db",
    "legendary": "#f1c40f",
    "mythical": "#9b59b6",
    "limited": "#ff69b4",
    "event": "#e67e22",
    "secret": "#7b1fa2",
    "exotic": "#ff9800",
}

MUTATION_TYPES = [
    app_commands.Choice(name="All types", value="all"),
    app_commands.Choice(name="Mutations", value="mutations"),
    app_commands.Choice(name="Attributes", value="attributes"),
    app_commands.Choice(name="Event", value="event"),
    app_commands.Choice(name="Limited", value="limited"),
    app_commands.Choice(name="Exclusive", value="exclusive"),
    app_commands.Choice(name="Admin", value="admin"),
    app_commands.Choice(name="Unobtainable", value="unobtainable"),
]

_TYPE_MAP = {
    "mutations": "Mutations",
    "attributes": "Attributes",
    "event": "Event Mutations",
    "limited": "Limited Mutations",
    "exclusive": "Exclusive Mutations",
    "admin": "Admin Mutations",
    "unobtainable": "Mutations (Unobtainable)",
}


def _rarity_color(rarity: str) -> discord.Color:
    hex_color = RARITY_COLORS.get(rarity.strip().lower())
    return discord.Color.from_str(hex_color) if hex_color else COLOR


def _matches(values: Iterable[str | None], query: str | None) -> bool:
    if not query:
        return True
    needle = query.strip().lower()
    return any(needle in (value or "").lower() for value in values)


def _chunks(items: Sequence, size: int) -> list[Sequence]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _resolve(results: Sequence, query: str | None):
    """Return the item to show in detail, if the search is unambiguous."""
    if not query:
        return None
    needle = query.strip().lower()
    for item in results:
        if item.name.lower() == needle:
            return item
    if len(results) == 1:
        return results[0]
    return None


class CatalogCommands(commands.Cog):
    """Reference commands for mutations, bait, harpoon guns, and spears."""

    def __init__(self, bot: "FischBot") -> None:
        self.bot = bot

    # --------------------------------------------------------------- helpers

    async def _send(
        self,
        ctx: commands.Context,
        pages: list[discord.Embed],
        *,
        empty: str | None = None,
    ) -> None:
        if not pages:
            await ctx.send(
                embed=discord.Embed(
                    title="Nothing found",
                    description=empty or "No entries match your search.",
                    color=discord.Color.orange(),
                )
            )
            return
        if len(pages) > 1:
            view = Paginator(pages, author_id=ctx.author.id)
            await ctx.send(embed=pages[0], view=view)
        else:
            await ctx.send(embed=pages[0])

    async def _send_picker(
        self,
        ctx: commands.Context,
        results: Sequence,
        detail: Callable[[Any], discord.Embed],
        *,
        title: str,
        placeholder: str,
    ) -> None:
        by_name = {item.name: item for item in results}

        async def on_pick(value: str) -> discord.Embed | None:
            item = by_name.get(value)
            return detail(item) if item is not None else None

        view = Picker(
            [(item.name, item.name) for item in results],
            author_id=ctx.author.id,
            on_pick=on_pick,
            placeholder=placeholder,
        )
        message = await ctx.send(
            embed=discord.Embed(
                title=title,
                description="Pick the entry you want from the menu below.",
                color=COLOR,
            ),
            view=view,
        )
        view.message = message

    def _list_pages(
        self,
        title: str,
        items: Sequence,
        render: Callable[[Any], str],
        *,
        per_page: int,
        color: discord.Color = COLOR,
        summary: str | None = None,
    ) -> list[discord.Embed]:
        pages: list[discord.Embed] = []
        chunks = _chunks(items, per_page)
        for index, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=title,
                description="\n\n".join(render(item) for item in chunk),
                color=color,
            )
            if index == 1 and summary:
                embed.description = f"{summary}\n\n{embed.description}"
            embed.set_footer(
                text=f"{FOOTER} • {len(items)} entries • page {index}/{len(chunks)}"
            )
            pages.append(embed)
        return pages

    @staticmethod
    def _detail_footer(embed: discord.Embed) -> discord.Embed:
        embed.set_footer(text=f"Fisch Wiki Bot v{__version__} • {FOOTER}")
        return embed

    # ----------------------------------------------------------- mutations

    @commands.hybrid_command(
        name="mutations",
        description="List fish mutations, their value multipliers, and sources",
    )
    @app_commands.describe(
        query="Search by mutation name, type, or source",
        type="Filter by mutation type",
    )
    @app_commands.choices(type=MUTATION_TYPES)
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def mutations(
        self,
        ctx: commands.Context,
        query: str | None = None,
        type: str | None = None,
    ) -> None:
        await ctx.defer()
        mutations = await load_mutations(self.bot.wiki)

        wanted_type = _TYPE_MAP.get((type or "all").lower())
        results = [
            mutation
            for mutation in mutations
            if (wanted_type is None or mutation.type == wanted_type)
            and _matches(
                (mutation.name, mutation.type, mutation.source), query
            )
        ]

        match = _resolve(results, query)
        if match is not None:
            await self._send(ctx, [await self._mutation_detail(match)])
            return

        filters = ""
        if wanted_type:
            filters += f" · type **{wanted_type}**"
        if query:
            filters += f" · search **{truncate(query, 40)}**"
        summary = f"Sorted by value multiplier{filters}."

        pages = self._list_pages(
            "🧬 Mutations",
            results,
            self._mutation_line,
            per_page=8,
            summary=summary,
        )
        await self._send(ctx, pages, empty=f"No mutations match **{query or type}**.")

    @staticmethod
    def _mutation_line(mutation: Mutation) -> str:
        chance = ""
        if mutation.appraisable.lower() == "yes" and mutation.chance:
            chance = f" · Appraisable {mutation.chance}"
        elif mutation.appraisable.lower().startswith("temp") and mutation.chance:
            chance = f" · Temporarily {mutation.chance}"
        return (
            f"**[{mutation.name}]({mutation.url})** — **{mutation.value}**\n"
            f"{mutation.type} · Priority {mutation.priority}{chance}\n"
            f"Source: {truncate(mutation.source, 110)}"
        )

    async def _mutation_detail(self, mutation: Mutation) -> discord.Embed:
        embed = discord.Embed(
            title=f"🧬 {mutation.name}",
            url=mutation.url,
            description=f"**{mutation.type}** mutation",
            color=COLOR,
        )
        embed.add_field(name="Multiplier", value=f"**{mutation.value}**", inline=True)
        embed.add_field(name="Priority", value=mutation.priority, inline=True)
        appraisable = mutation.appraisable
        if mutation.chance and mutation.chance not in {"✗", "—"}:
            appraisable += f" ({mutation.chance})"
        embed.add_field(name="Appraisable", value=appraisable, inline=True)
        embed.add_field(name="Source", value=truncate(mutation.source, 1000), inline=False)

        obtainment = await load_obtainment(self.bot.wiki, mutation.name)
        if obtainment:
            embed.add_field(
                name="How to obtain",
                value=truncate(obtainment, 1000),
                inline=False,
            )
        if mutation.randomized and mutation.randomized != "—":
            embed.add_field(name="Randomized attribute", value=mutation.randomized, inline=True)
        return self._detail_footer(embed)

    @mutations.autocomplete("query")
    async def mutations_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            mutations = await load_mutations(self.bot.wiki)
        except WikiError:
            return []
        return [
            app_commands.Choice(name=mutation.name, value=mutation.name)
            for mutation in mutations
            if current.lower() in mutation.name.lower()
        ][:25]

    # ---------------------------------------------------------------- bait

    @commands.hybrid_command(
        name="bait", description="List bait stats, rarity, and abilities"
    )
    @app_commands.describe(query="Search by bait name or rarity")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def bait(self, ctx: commands.Context, query: str | None = None) -> None:
        await ctx.defer()
        baits = await load_baits(self.bot.wiki)

        results = [
            bait
            for bait in baits
            if _matches((bait.name, bait.rarity), query)
        ]

        match = _resolve(results, query)
        if match is not None:
            await self._send(ctx, [self._bait_detail(match)])
            return
        if query and len(results) > 1:
            await self._send_picker(
                ctx,
                results,
                self._bait_detail,
                title=f"🪱 {len(results)} bait match **{truncate(query, 60)}**",
                placeholder="Choose bait…",
            )
            return

        pages = self._list_pages(
            "🪱 Bait",
            results,
            self._bait_line,
            per_page=7,
            summary="Preferred luck, universal luck, resilience, and lure speed.",
        )
        await self._send(ctx, pages, empty=f"No bait matches **{query}**.")

    @staticmethod
    def _bait_line(bait: Bait) -> str:
        return (
            f"**[{bait.name}]({bait.url})** — {bait.rarity}\n"
            f"Pref. Luck {bait.pref_luck} · Univ. Luck {bait.univ_luck} · "
            f"Resil. {bait.resilience} · Lure {bait.lure} · {bait.favoring} fish"
            + (f"\nAbility: {truncate(bait.ability, 100)}" if bait.ability != "—" else "")
        )

    def _bait_detail(self, bait: Bait) -> discord.Embed:
        embed = discord.Embed(
            title=f"🪱 {bait.name}",
            url=bait.url,
            description=f"**{bait.rarity}** bait",
            color=_rarity_color(bait.rarity),
        )
        embed.add_field(name="Pref. Luck", value=bait.pref_luck, inline=True)
        embed.add_field(name="Universal Luck", value=bait.univ_luck, inline=True)
        embed.add_field(name="Resilience", value=bait.resilience, inline=True)
        embed.add_field(name="Lure Speed", value=bait.lure, inline=True)
        favoring = (
            f"{bait.favoring} fish" if bait.favoring.isdigit() else bait.favoring
        )
        embed.add_field(name="Favoring Fish", value=favoring, inline=True)
        if bait.ability and bait.ability != "—":
            embed.add_field(name="Ability", value=truncate(bait.ability, 1000), inline=False)
        embed.add_field(
            name="Obtainment", value=truncate(bait.obtainment, 1000), inline=False
        )
        return self._detail_footer(embed)

    @bait.autocomplete("query")
    async def bait_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            baits = await load_baits(self.bot.wiki)
        except WikiError:
            return []
        return [
            app_commands.Choice(name=bait.name, value=bait.name)
            for bait in baits
            if current.lower() in bait.name.lower()
        ][:25]

    # ------------------------------------------------------------- harpoons

    @commands.hybrid_command(
        name="harpoon", description="List harpoon gun stats, sources, and abilities"
    )
    @app_commands.describe(query="Search by harpoon gun name, location, or source")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def harpoon(self, ctx: commands.Context, query: str | None = None) -> None:
        await ctx.defer()
        harpoons = await load_harpoons(self.bot.wiki)

        results = [
            harpoon
            for harpoon in harpoons
            if _matches(
                (harpoon.name, harpoon.location, harpoon.source), query
            )
        ]

        match = _resolve(results, query)
        if match is not None:
            await self._send(ctx, [self._harpoon_detail(match)])
            return
        if query and len(results) > 1:
            await self._send_picker(
                ctx,
                results,
                self._harpoon_detail,
                title=f"🎯 {len(results)} harpoon guns match **{truncate(query, 60)}**",
                placeholder="Choose a harpoon gun…",
            )
            return

        pages = self._list_pages(
            "🎯 Harpoon Guns",
            results,
            self._harpoon_line,
            per_page=5,
            summary="Power, range, reload, velocity, resilience, and accuracy.",
        )
        await self._send(ctx, pages, empty=f"No harpoon gun matches **{query}**.")

    @staticmethod
    def _harpoon_line(harpoon: Harpoon) -> str:
        return (
            f"**[{harpoon.name}]({harpoon.url})** — Stage {harpoon.stage}\n"
            f"{harpoon.location} · {truncate(harpoon.source, 70)}\n"
            f"Power {harpoon.power} · Range {harpoon.range} · Reload {harpoon.reload} · "
            f"Velocity {harpoon.velocity}\n"
            f"Resilience {harpoon.resilience} · Accuracy {harpoon.accuracy} · "
            f"Max {format_weight(harpoon.max_kg)} · Obtainable: {harpoon.obtainable}"
        )

    def _harpoon_detail(self, harpoon: Harpoon) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎯 {harpoon.name}",
            url=harpoon.url,
            description=f"Stage {harpoon.stage} harpoon gun",
            color=COLOR,
        )
        embed.add_field(name="Location", value=truncate(harpoon.location, 200), inline=True)
        embed.add_field(name="Obtainable", value=harpoon.obtainable, inline=True)
        embed.add_field(name="Power", value=harpoon.power, inline=True)
        embed.add_field(name="Range", value=harpoon.range, inline=True)
        embed.add_field(name="Reload", value=harpoon.reload, inline=True)
        embed.add_field(name="Velocity", value=harpoon.velocity, inline=True)
        embed.add_field(name="Resilience", value=harpoon.resilience, inline=True)
        embed.add_field(name="Accuracy", value=harpoon.accuracy, inline=True)
        embed.add_field(name="Max Kg", value=format_weight(harpoon.max_kg), inline=True)
        embed.add_field(name="Source", value=truncate(harpoon.source, 1000), inline=False)
        return self._detail_footer(embed)

    @harpoon.autocomplete("query")
    async def harpoon_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            harpoons = await load_harpoons(self.bot.wiki)
        except WikiError:
            return []
        return [
            app_commands.Choice(name=harpoon.name, value=harpoon.name)
            for harpoon in harpoons
            if current.lower() in harpoon.name.lower()
        ][:25]

    # --------------------------------------------------------------- spears

    @commands.hybrid_command(
        name="spear", description="List spear stats, sources, and locations"
    )
    @app_commands.describe(query="Search by spear name, location, or source")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def spear(self, ctx: commands.Context, query: str | None = None) -> None:
        await ctx.defer()
        spears = await load_spears(self.bot.wiki)

        results = [
            spear
            for spear in spears
            if _matches((spear.name, spear.location, spear.source), query)
        ]

        match = _resolve(results, query)
        if match is not None:
            await self._send(ctx, [self._spear_detail(match)])
            return
        if query and len(results) > 1:
            await self._send_picker(
                ctx,
                results,
                self._spear_detail,
                title=f"🔱 {len(results)} spears match **{truncate(query, 60)}**",
                placeholder="Choose a spear…",
            )
            return

        pages = self._list_pages(
            "🔱 Spears",
            results,
            self._spear_line,
            per_page=6,
            summary="Power, handling, and piercing stats.",
        )
        await self._send(ctx, pages, empty=f"No spear matches **{query}**.")

    @staticmethod
    def _spear_line(spear: Spear) -> str:
        return (
            f"**[{spear.name}]({spear.url})** — Stage {spear.stage}\n"
            f"{spear.location} · {truncate(spear.source, 80)}\n"
            f"Power {spear.power} · Handling {spear.handling} · "
            f"Piercing {spear.piercing} · Obtainable: {spear.obtainable}"
        )

    def _spear_detail(self, spear: Spear) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔱 {spear.name}",
            url=spear.url,
            description=f"Stage {spear.stage} spear",
            color=COLOR,
        )
        embed.add_field(name="Location", value=truncate(spear.location, 200), inline=True)
        embed.add_field(name="Obtainable", value=spear.obtainable, inline=True)
        embed.add_field(name="Power", value=spear.power, inline=True)
        embed.add_field(name="Handling", value=spear.handling, inline=True)
        embed.add_field(name="Piercing", value=spear.piercing, inline=True)
        embed.add_field(name="Source", value=truncate(spear.source, 1000), inline=False)
        return self._detail_footer(embed)

    @spear.autocomplete("query")
    async def spear_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            spears = await load_spears(self.bot.wiki)
        except WikiError:
            return []
        return [
            app_commands.Choice(name=spear.name, value=spear.name)
            for spear in spears
            if current.lower() in spear.name.lower()
        ][:25]
