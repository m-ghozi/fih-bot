from __future__ import annotations

import html as html_module
import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..parsing import parse_codes, parse_infobox
from ..ui import Paginator, truncate
from ..wiki import PageNotFoundError, WikiError

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


_DISAMBIGUATION_FISH = re.compile(
    r'<span class="item-name[^"]*"[^>]*>\s*<a [^>]*title="([^"]+)"', re.S
)

MAX_CHOICES = 25


class FishSelect(discord.ui.Select):
    def __init__(self, cog: "WikiCommands", titles: list[str]) -> None:
        self.cog = cog
        self.titles = titles
        self.page = 0
        super().__init__(placeholder="Choose a fish…", options=self._page_options())
        self._update_placeholder()

    def _page_options(self) -> list[discord.SelectOption]:
        start = self.page * MAX_CHOICES
        chunk = self.titles[start : start + MAX_CHOICES]
        return [
            discord.SelectOption(label=truncate(title, 100), value=title)
            for title in chunk
        ]

    def _update_placeholder(self) -> None:
        if len(self.titles) <= MAX_CHOICES:
            self.placeholder = "Choose a fish…"
            return
        start = self.page * MAX_CHOICES
        end = min(start + MAX_CHOICES, len(self.titles))
        self.placeholder = (
            f"Choose a fish… ({start + 1}-{end} of {len(self.titles)})"
        )

    def show_page(self, page: int) -> None:
        self.page = page
        self.options = self._page_options()
        self._update_placeholder()

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        embed = await self.cog._fish_embed(self.values[0])
        if embed is None:
            await interaction.edit_original_response(
                content=f"Could not load **{self.values[0]}**.",
                embed=None,
                view=None,
            )
            return
        await interaction.edit_original_response(embed=embed, view=None)


class FishChooser(discord.ui.View):
    def __init__(self, cog: "WikiCommands", titles: list[str], author_id: int) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id
        self.titles = titles
        self.message: discord.Message | None = None
        self.select = FishSelect(cog, titles)
        self.add_item(self.select)

        self.previous: discord.ui.Button | None = None
        self.next: discord.ui.Button | None = None
        if len(titles) > MAX_CHOICES:
            self.previous = discord.ui.Button(
                label="Previous", style=discord.ButtonStyle.secondary
            )
            self.previous.callback = self._previous_page
            self.next = discord.ui.Button(
                label="Next", style=discord.ButtonStyle.secondary
            )
            self.next.callback = self._next_page
            self.add_item(self.previous)
            self.add_item(self.next)
            self._sync_buttons()

    def _sync_buttons(self) -> None:
        if self.previous is None or self.next is None:
            return
        pages = (len(self.titles) + MAX_CHOICES - 1) // MAX_CHOICES
        self.previous.disabled = self.select.page == 0
        self.next.disabled = self.select.page >= pages - 1

    async def _change_page(
        self, interaction: discord.Interaction, delta: int
    ) -> None:
        pages = (len(self.titles) + MAX_CHOICES - 1) // MAX_CHOICES
        page = min(max(self.select.page + delta, 0), pages - 1)
        self.select.show_page(page)
        self._sync_buttons()
        await interaction.response.edit_message(view=self)

    async def _previous_page(self, interaction: discord.Interaction) -> None:
        await self._change_page(interaction, -1)

    async def _next_page(self, interaction: discord.Interaction) -> None:
        await self._change_page(interaction, 1)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This menu belongs to someone else. Run the command yourself to pick a fish.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


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

    async def _disambiguation_fish(self, title: str) -> list[str]:
        """Return the fish listed on a ``(Disambiguation)`` page."""
        try:
            _, page = await self.wiki.parsed_html(title)
        except WikiError:
            return []
        names: list[str] = []
        for match in _DISAMBIGUATION_FISH.finditer(page):
            name = html_module.unescape(match.group(1))
            if name not in names:
                names.append(name)
        return names

    async def _find_fish(self, name: str) -> list[str]:
        """Find every fish page that could match ``name``.

        Wiki titles are case-sensitive after the first letter, so ``whale
        shark`` does not exist while ``Whale Shark`` does. Exact and
        case-insensitive matches are returned immediately; otherwise search
        results and ``(Disambiguation)`` pages are used, and the caller offers
        a picker when more than one fish matches.
        """
        try:
            title, text = await self.wiki.wikitext(name)
        except PageNotFoundError:
            title, text = "", ""
        if text and parse_infobox(text, "FishInfobox") is not None:
            return [title]

        needle = name.strip().lower()
        results = await self.wiki.search(name, limit=10)
        # Prefer a case-insensitive title match over the search ranking.
        results.sort(key=lambda result: result.title.lower() != needle)

        found: list[str] = []
        for result in results:
            if result.title.lower() == needle:
                try:
                    candidate_title, candidate_text = await self.wiki.wikitext(
                        result.title
                    )
                except PageNotFoundError:
                    continue
                if parse_infobox(candidate_text, "FishInfobox") is not None:
                    return [candidate_title]

            if result.title.lower().endswith("(disambiguation)"):
                names = await self._disambiguation_fish(result.title)
                if names:
                    return names
                continue

            if result.title in found:
                continue
            try:
                candidate_title, candidate_text = await self.wiki.wikitext(
                    result.title
                )
            except PageNotFoundError:
                continue
            if (
                parse_infobox(candidate_text, "FishInfobox") is not None
                and candidate_title not in found
            ):
                found.append(candidate_title)
        return found

    async def _fish_embed(self, title: str) -> discord.Embed | None:
        """Build the fish infobox embed for ``title``, or ``None`` if not a fish."""
        try:
            resolved_title, wikitext = await self.wiki.wikitext(title)
        except PageNotFoundError:
            return None
        box = parse_infobox(wikitext, "FishInfobox")
        if box is None:
            return None

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
        return embed

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
            # Wiki titles are case-sensitive after the first letter. Retry
            # with a case-insensitive exact match, then suggest alternatives.
            results = await self.wiki.search(title, limit=5)
            needle = title.strip().lower()
            exact = next(
                (result for result in results if result.title.lower() == needle),
                None,
            )
            if exact is not None:
                info = await self.wiki.page(exact.title)
            elif results:
                listing = "\n".join(
                    f"• [{result.title}]({result.url})"
                    for result in results
                )
                await ctx.send(
                    embed=discord.Embed(
                        title="Page not found",
                        description=(
                            f"No page named **{title}**. Did you mean:\n\n{listing}"
                        ),
                        color=discord.Color.orange(),
                    )
                )
                return
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
    @app_commands.describe(name="Fish name, e.g. 'Salmon', 'Whale Shark', or 'Megalodon'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def fish(self, ctx: commands.Context, *, name: str) -> None:
        await ctx.defer()
        titles = await self._find_fish(name)
        if not titles:
            await ctx.send(
                embed=discord.Embed(
                    title="Fish not found",
                    description=(
                        f"No fish page matches **{name}**. "
                        f"Try `!wiki {name}` to search the wiki."
                    ),
                    color=discord.Color.orange(),
                )
            )
            return

        if len(titles) == 1:
            embed = await self._fish_embed(titles[0])
            if embed is None:
                await ctx.send(
                    embed=discord.Embed(
                        title="Not a fish page",
                        description=(
                            f"**{titles[0]}** has no fish infobox. "
                            f"Try `!page {titles[0]}` to read its content."
                        ),
                        color=discord.Color.orange(),
                    )
                )
                return
            await ctx.send(embed=embed)
            return

        view = FishChooser(self, titles, author_id=ctx.author.id)
        message = await ctx.send(
            embed=discord.Embed(
                title=f"🐟 {len(titles)} fish match **{truncate(name, 60)}**",
                description=(
                    "Pick the fish you want from the menu below."
                    + (
                        " Use **Previous** / **Next** to browse all matches."
                        if len(titles) > MAX_CHOICES
                        else ""
                    )
                ),
                color=COLOR,
            ),
            view=view,
        )
        view.message = message

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
