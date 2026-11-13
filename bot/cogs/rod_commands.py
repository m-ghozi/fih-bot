from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import discord
from discord import app_commands
from discord.ext import commands

from ..catalogs import Enchantment, load_enchantments
from ..mastery import load_mastery, load_mastery_rods
from ..parsing import (
    extract_section,
    extract_template_version,
    parse_infobox,
)
from ..ui import Paginator, Picker, truncate
from ..wiki import PageNotFoundError, WikiError

if TYPE_CHECKING:
    from ..client import FischBot

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
    def _not_found_embed(query: str) -> discord.Embed:
        return discord.Embed(
            title="Page not found",
            description=(
                f"No wiki page matches **{query}**. "
                f"Check the spelling or try `!wiki {query}`."
            ),
            color=discord.Color.orange(),
        )

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

    async def _find_rods(self, name: str) -> list[str]:
        needle = name.strip().lower()
        try:
            members = await self.wiki.category_members("Fishing Rods")
        except WikiError:
            members = []

        exact = next((member for member in members if member.lower() == needle), None)
        if exact is not None:
            return [exact]

        matches = [member for member in members if needle in member.lower()]
        if matches:
            return matches

        # Fall back to a wiki search for rods outside the category listing.
        found: list[str] = []
        for result in await self.wiki.search(name, limit=10):
            try:
                title, wikitext = await self.wiki.wikitext(result.title)
            except PageNotFoundError:
                continue
            if (
                parse_infobox(wikitext, "RodInfobox") is not None
                and title not in found
            ):
                found.append(title)
        return found

    async def _rod_embed(self, title: str) -> discord.Embed | None:
        try:
            resolved_title, wikitext = await self.wiki.wikitext(title)
        except PageNotFoundError:
            return None
        box = parse_infobox(wikitext, "RodInfobox")
        if box is None:
            return None

        info = await self.wiki.page(resolved_title)
        embed = discord.Embed(
            title=box.get("name") or resolved_title,
            url=self.wiki.page_url(resolved_title),
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
        return embed

    @staticmethod
    def _mastery_list_pages(
        wiki_url: Callable[[str], str], members: list[str]
    ) -> list[discord.Embed]:
        per_page = 15
        total_pages = max(1, (len(members) + per_page - 1) // per_page)
        pages: list[discord.Embed] = []
        for index in range(total_pages):
            chunk = members[index * per_page : (index + 1) * per_page]
            lines = "\n".join(f"[{name}]({wiki_url(name)})" for name in chunk)
            description = lines
            if index == 0:
                description = (
                    "Rod Mastery adds quests to specific rods. Rewards include "
                    "skins, boats, bobbers, lanterns, titles, and permanent "
                    "enhancements. Pick a rod to see its quests.\n\n" + lines
                )
            embed = discord.Embed(
                title="Rod Mastery", description=description, color=COLOR
            )
            embed.set_footer(
                text=(
                    f"{FOOTER} • {len(members)} rods • "
                    f"page {index + 1}/{total_pages}"
                )
            )
            pages.append(embed)
        return pages

    @staticmethod
    def _enchantment_embed(enchantment: Enchantment) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔮 {enchantment.name}",
            url=enchantment.url,
            description=f"**{enchantment.category}** enchantment",
            color=COLOR,
        )
        if enchantment.effects:
            _add_lines_field(
                embed, "Effect", [f"• {line}" for line in enchantment.effects]
            )
        embed.set_footer(text=FOOTER)
        return embed

    @staticmethod
    def _enchantment_list_pages(
        enchantments: list[Enchantment],
    ) -> list[discord.Embed]:
        per_page = 8
        chunks = [
            enchantments[index : index + per_page]
            for index in range(0, len(enchantments), per_page)
        ]
        pages: list[discord.Embed] = []
        for index, chunk in enumerate(chunks, start=1):
            lines = []
            for enchantment in chunk:
                effect = " · ".join(enchantment.effects[:2]) or "—"
                lines.append(
                    f"**[{enchantment.name}]({enchantment.url})** — "
                    f"{enchantment.category}\n{truncate(effect, 160)}"
                )
            embed = discord.Embed(
                title="🔮 Enchantments",
                description="\n\n".join(lines),
                color=COLOR,
            )
            embed.set_footer(
                text=(
                    f"{FOOTER} • {len(enchantments)} enchantments • "
                    f"page {index}/{len(chunks)}"
                )
            )
            pages.append(embed)
        return pages

    async def _mastery_embed(self, title: str) -> discord.Embed | None:
        data = await load_mastery(self.wiki, title)
        if data is None or not data.quests:
            return None

        description_parts: list[str] = []
        if data.level:
            description_parts.append(f"Starting level requirement: **{data.level}**")
        if data.grand_reward:
            description_parts.append(f"Grand reward: **{data.grand_reward}**")
        embed = discord.Embed(
            title=f"Rod Mastery — {data.title}",
            url=data.url,
            description="\n".join(description_parts) or None,
            color=COLOR,
        )
        thumbnail = await self.wiki.thumbnail(data.title)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        for index, quest in enumerate(data.quests, start=1):
            value = quest.description or "No description."
            if quest.reward:
                value += f"\n**Reward:** {quest.reward}"
            if quest.note:
                value += f"\n*{quest.note}*"
            embed.add_field(
                name=truncate(f"{index}. {quest.name}", 256),
                value=truncate(value, 1024),
                inline=False,
            )

        embed.set_footer(text=FOOTER)
        return embed

    # ----------------------------------------------------------- commands

    @commands.hybrid_command(
        name="rod", description="Show stats and ability of a fishing rod"
    )
    @app_commands.describe(name="Rod name, e.g. 'Trident Rod'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def rod(self, ctx: commands.Context, *, name: str) -> None:
        await ctx.defer()
        titles = await self._find_rods(name)
        if not titles:
            await self._send(ctx, self._not_found_embed(name))
            return

        if len(titles) == 1:
            embed = await self._rod_embed(titles[0])
            if embed is None:
                await self._send(ctx, self._not_rod_embed(titles[0], "rod"))
                return
            await self._send(ctx, embed)
            return

        view = Picker(
            [(title, title) for title in titles],
            author_id=ctx.author.id,
            on_pick=self._rod_embed,
            placeholder="Choose a rod…",
        )
        message = await ctx.send(
            embed=discord.Embed(
                title=f"🎣 {len(titles)} rods match **{truncate(name, 60)}**",
                description="Pick the rod you want from the menu below.",
                color=COLOR,
            ),
            view=view,
        )
        view.message = message

    @rod.autocomplete("name")
    async def rod_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._rod_autocomplete(interaction, current)

    @commands.hybrid_command(
        name="relic",
        description="Show an enchantment's effects and category",
    )
    @app_commands.describe(name="Enchantment name, e.g. 'Sea King'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def relic(self, ctx: commands.Context, *, name: str | None = None) -> None:
        await ctx.defer()
        enchantments = await load_enchantments(self.wiki)

        if not enchantments:
            await ctx.send(
                embed=discord.Embed(
                    title="Enchantments unavailable",
                    description="Could not read the Enchanting page right now.",
                    color=discord.Color.orange(),
                )
            )
            return

        if name is None:
            pages = self._enchantment_list_pages(enchantments)
            if len(pages) > 1:
                view = Paginator(pages, author_id=ctx.author.id)
                await ctx.send(embed=pages[0], view=view)
            else:
                await ctx.send(embed=pages[0])
            return

        needle = name.strip().lower()
        # Allow "!relic Tropical Relic" as well as "!relic Tropical".
        if needle.endswith(" relic"):
            needle = needle[: -len(" relic")].strip()
        exact = next(
            (item for item in enchantments if item.name.lower() == needle), None
        )
        if exact is not None:
            await ctx.send(embed=self._enchantment_embed(exact))
            return

        matches = [
            item for item in enchantments if needle in item.name.lower()
        ]
        if len(matches) == 1:
            await ctx.send(embed=self._enchantment_embed(matches[0]))
            return
        if not matches:
            await ctx.send(
                embed=discord.Embed(
                    title="Enchantment not found",
                    description=(
                        f"No enchantment matches **{name}**. "
                        f"Use `!relic` to list every enchantment."
                    ),
                    color=discord.Color.orange(),
                )
            )
            return

        by_name = {item.name: item for item in matches}
        view = Picker(
            [(item.name, item.name) for item in matches],
            author_id=ctx.author.id,
            on_pick=lambda value: self._pick_enchantment(by_name, value),
            placeholder="Choose an enchantment…",
        )
        message = await ctx.send(
            embed=discord.Embed(
                title=f"🔮 {len(matches)} enchantments match **{truncate(name, 60)}**",
                description="Pick one from the menu below.",
                color=COLOR,
            ),
            view=view,
        )
        view.message = message

    async def _pick_enchantment(
        self, by_name: dict[str, Enchantment], value: str
    ) -> discord.Embed | None:
        enchantment = by_name.get(value)
        return self._enchantment_embed(enchantment) if enchantment else None

    @relic.autocomplete("name")
    async def relic_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            enchantments = await load_enchantments(self.wiki)
        except WikiError:
            return []
        current_lower = current.lower()
        return [
            app_commands.Choice(name=item.name[:100], value=item.name[:100])
            for item in enchantments
            if current_lower in item.name.lower()
        ][:25]

    @commands.hybrid_command(
        name="enchant",
        description="Show recommended enchantments for a fishing rod",
    )
    @app_commands.describe(name="Rod name, e.g. 'Trident Rod'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def enchant(self, ctx: commands.Context, *, name: str) -> None:
        await ctx.defer()
        resolved = await self.wiki.resolve_page(name, suffix="Rod")
        if resolved is None:
            await self._send(ctx, self._not_found_embed(name))
            return
        title, wikitext = resolved
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

    # ------------------------------------------------------------ mastery

    @commands.hybrid_command(
        name="mastery",
        description="Show Rod Mastery quests, rewards, and level requirements",
    )
    @app_commands.describe(name="Rod name, e.g. 'Trident Rod'")
    @commands.cooldown(2, 8.0, commands.BucketType.user)
    async def mastery(
        self, ctx: commands.Context, *, name: str | None = None
    ) -> None:
        await ctx.defer()
        members = await load_mastery_rods(self.wiki)

        if name is None:
            pages = self._mastery_list_pages(self.wiki.page_url, members)
            if len(pages) > 1:
                view = Paginator(pages, author_id=ctx.author.id)
                await ctx.send(embed=pages[0], view=view)
            else:
                await ctx.send(embed=pages[0])
            return

        needle = name.strip().lower()
        exact = next((member for member in members if member.lower() == needle), None)
        if exact is not None:
            title = exact
        else:
            matches = [member for member in members if needle in member.lower()]
            if len(matches) == 1:
                title = matches[0]
            elif matches:
                view = Picker(
                    [(member, member) for member in matches],
                    author_id=ctx.author.id,
                    on_pick=self._mastery_embed,
                    placeholder="Choose a rod…",
                )
                message = await ctx.send(
                    embed=discord.Embed(
                        title=f"🏆 {len(matches)} rods with mastery match **{truncate(name, 60)}**",
                        description="Pick a rod from the menu below.",
                        color=COLOR,
                    ),
                    view=view,
                )
                view.message = message
                return
            else:
                await ctx.send(
                    embed=discord.Embed(
                        title="No Rod Mastery found",
                        description=(
                            f"No rod with mastery matches **{name}**. "
                            "Use `!mastery` to list every rod that has one."
                        ),
                        color=discord.Color.orange(),
                    )
                )
                return

        embed = await self._mastery_embed(title)
        if embed is None:
            await ctx.send(
                embed=discord.Embed(
                    title="No Rod Mastery",
                    description=f"The wiki does not list mastery quests for **{title}**.",
                    color=discord.Color.orange(),
                )
            )
            return
        await self._send(ctx, embed)

    @mastery.autocomplete("name")
    async def mastery_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            members = await load_mastery_rods(self.wiki)
        except WikiError:
            return []
        current_lower = current.lower()
        return [
            app_commands.Choice(name=member[:100], value=member[:100])
            for member in members
            if current_lower in member.lower()
        ][:25]
