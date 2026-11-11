from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..parsing import parse_codes, parse_infobox
from ..ui import Paginator, truncate

if TYPE_CHECKING:
    from ..client import FischBot

COLOR = discord.Color.from_str("#3ba7d8")
FOOTER = "Source: Official Fisch Wiki • CC BY-NC-SA 4.0"

STATUS_CHOICES = [
    app_commands.Choice(name="Active", value="active"),
    app_commands.Choice(name="Inactive", value="inactive"),
    app_commands.Choice(name="All", value="all"),
]


def _search_pages(query: str, results: list, per_page: int = 6) -> list[discord.Embed]:
    chunks = [results[i : i + per_page] for i in range(0, len(results), per_page)]
    pages: list[discord.Embed] = []
    for index, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"🔎 Search results: {query}",
            color=COLOR,
            description=f"Found **{len(results)}** matching pages.",
        )
        for result in chunk:
            embed.add_field(
                name=truncate(result.title, 250),
                value=f"{truncate(result.snippet, 240)}\n[View page]({result.url})",
                inline=False,
            )
        embed.set_footer(text=f"{FOOTER} • page {index}/{len(chunks)}")
        pages.append(embed)
    return pages


def _code_block(code: dict[str, str]) -> str:
    lines = [f"**{code['code']}**  ·  Level `{code['level'] or 'N/A'}`"]
    if code["added"]:
        lines.append(f"Added: {code['added']}")
    if code["expires"]:
        lines.append(f"Expires: {code['expires']}")
    if code["rewards"]:
        lines.append(f"Rewards: {truncate(code['rewards'], 280)}")
    return "\n".join(lines)


def _code_pages(
    codes: list[dict[str, str]], status_label: str, per_page: int = 5
) -> list[discord.Embed]:
    chunks = [codes[i : i + per_page] for i in range(0, len(codes), per_page)]
    pages: list[discord.Embed] = []
    for index, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"🎁 {status_label} Codes",
            color=COLOR,
            description="\n\n".join(_code_block(code) for code in chunk),
        )
        embed.set_footer(text=f"{FOOTER} • {len(codes)} codes • page {index}/{len(chunks)}")
        pages.append(embed)
    return pages


class WikiCommands(commands.Cog):
    def __init__(self, bot: "FischBot") -> None:
        self.bot = bot
        self.wiki = bot.wiki

    # --------------------------------------------------------------- helpers

    async def _send_pages(
        self, ctx: commands.Context, pages: list[discord.Embed]
    ) -> None:
        """Send the first page, attaching a paginator only when needed."""
        if len(pages) > 1:
            view = Paginator(pages, author_id=ctx.author.id)
            await ctx.send(embed=pages[0], view=view)
        else:
            await ctx.send(embed=pages[0])

    # ----------------------------------------------------------- commands

    @commands.hybrid_command(name="wiki", description="Search pages on the Official Fisch Wiki")
    @app_commands.describe(query="Search keywords, e.g. 'salmon' or 'fishing rod'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def wiki_search(self, ctx: commands.Context, *, query: str) -> None:
        await ctx.defer()
        results = await self.wiki.search(query, limit=12)
        if not results:
            await ctx.send(
                embed=discord.Embed(
                    title="No results",
                    description=f"No pages match **{query}**.",
                    color=discord.Color.orange(),
                )
            )
            return

        await self._send_pages(ctx, _search_pages(query, results))

    @commands.hybrid_command(name="page", description="Show a summary of a wiki page")
    @app_commands.describe(title="Page title, e.g. 'Fisch', 'Codes', or 'Fishing Rods'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def page(self, ctx: commands.Context, *, title: str) -> None:
        await ctx.defer()
        info = await self.wiki.page(title)
        if info.missing:
            await ctx.send(
                embed=discord.Embed(
                    title="Page not found",
                    description=(
                        f"**{title}** does not exist on the wiki. "
                        f"Try `!wiki {title}` to search for it."
                    ),
                    color=discord.Color.orange(),
                )
            )
            return

        embed = discord.Embed(
            title=info.title,
            url=info.url,
            description=truncate(info.extract or "This page has no summary yet.", 3900),
            color=COLOR,
        )
        if info.thumbnail:
            embed.set_thumbnail(url=info.thumbnail)
        embed.set_footer(text=FOOTER)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="fish", description="Show fish data from the wiki infobox")
    @app_commands.describe(name="Fish name, e.g. 'Salmon' or 'Megalodon'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def fish(self, ctx: commands.Context, *, name: str) -> None:
        await ctx.defer()
        resolved_title, wikitext = await self.wiki.wikitext(name)
        box = parse_infobox(wikitext, "FishInfobox")
        if box is None:
            await ctx.send(
                embed=discord.Embed(
                    title="Not a fish page",
                    description=(
                        f"**{resolved_title}** has no fish infobox. "
                        f"Try `!page {resolved_title}` to read its content."
                    ),
                    color=discord.Color.orange(),
                )
            )
            return

        url = self.wiki.page_url(resolved_title)
        embed = discord.Embed(title=box.get("name") or resolved_title, url=url, color=COLOR)

        fields = [
            ("Rarity", box.get("rarity")),
            ("Bestiary", box.get("bestiary")),
            ("Location", box.get("location")),
            ("Source", box.get("source")),
            ("Weather", box.get("weather")),
            ("Season", box.get("season")),
            ("Bait", box.get("bait")),
            ("XP", box.get("xp")),
            ("Base value", box.get("base_value")),
            ("Base weight", box.get("base_weight")),
            ("Weight range", box.get("weight_range")),
            ("Catch chance", box.get("base_chance")),
            ("Resilience", box.get("base_resil")),
            ("Radar", box.get("radar")),
        ]
        for label, value in fields:
            if not value:
                continue
            embed.add_field(name=label, value=truncate(value.replace(";", ", "), 200), inline=True)

        thumbnail = await self.wiki.thumbnail(resolved_title)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.set_footer(text=FOOTER)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="codes", description="Show Fisch redeem codes")
    @app_commands.describe(status="Choose active, inactive, or all codes")
    @app_commands.choices(status=STATUS_CHOICES)
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def codes(
        self,
        ctx: commands.Context,
        status: str | None = None,
    ) -> None:
        await ctx.defer()
        selected = (status or "active").lower()
        if selected not in {"active", "inactive", "all"}:
            selected = "active"
        _, wikitext = await self.wiki.wikitext("Codes")
        all_codes = parse_codes(wikitext)

        if selected != "all":
            all_codes = [code for code in all_codes if code["status"] == selected]

        if not all_codes:
            await ctx.send(
                embed=discord.Embed(
                    title="No codes",
                    description="No codes found for the selected category.",
                    color=discord.Color.orange(),
                )
            )
            return

        labels = {"active": "Active", "inactive": "Inactive", "all": "All"}
        await self._send_pages(ctx, _code_pages(all_codes, labels[selected]))
