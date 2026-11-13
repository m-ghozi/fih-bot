"""Parsers and caches for the wiki's item and mutation tables.

The wiki builds these tables from its own data buckets, so the data is only
available in the rendered HTML. We parse that HTML through the MediaWiki API
and cache the result for an hour instead of scraping the page repeatedly.
"""

from __future__ import annotations

import asyncio
import html as html_module
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import quote, urljoin

from .wiki import WikiClient, WikiError

__all__ = [
    "Mutation",
    "Enchantment",
    "Bait",
    "Harpoon",
    "Spear",
    "load_mutations",
    "load_obtainment",
    "load_enchantments",
    "load_baits",
    "load_harpoons",
    "load_spears",
    "format_weight",
]

CACHE_TTL = 3600.0

_HIDDEN_SPAN = re.compile(
    r'<span[^>]*style="[^"]*display:\s*none[^"]*"[^>]*>.*?</span>', re.S
)
_SORTKEY = re.compile(r'<span[^>]*class="sortkey"[^>]*>.*?</span>', re.S)
_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<br\s*/?>", re.I)
_EMBEDDED_CODE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING = re.compile(
    r'<h([23])[^>]*\bid="([^"]*)"[^>]*>(.*?)</h\1>', re.S
)
_ROW = re.compile(r'<tr\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</tr>', re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)

_cache: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class Mutation:
    name: str
    type: str
    source: str
    value: str
    value_number: float
    priority: str
    appraisable: str
    chance: str
    randomized: str
    url: str


@dataclass(frozen=True)
class Enchantment:
    name: str
    category: str
    effects: tuple[str, ...]
    optimal: str
    url: str


@dataclass(frozen=True)
class Bait:
    name: str
    rarity: str
    obtainment: str
    pref_luck: str
    univ_luck: str
    resilience: str
    lure: str
    favoring: str
    ability: str
    url: str


@dataclass(frozen=True)
class Harpoon:
    name: str
    location: str
    source: str
    stage: str
    power: str
    range: str
    reload: str
    velocity: str
    resilience: str
    accuracy: str
    max_kg: str
    obtainable: str
    url: str


@dataclass(frozen=True)
class Spear:
    name: str
    location: str
    source: str
    stage: str
    power: str
    handling: str
    piercing: str
    obtainable: str
    url: str


# ------------------------------------------------------------------ helpers


def _strip_tags(fragment: str) -> str:
    fragment = _EMBEDDED_CODE.sub("", fragment)
    fragment = _COMMENT.sub("", fragment)
    fragment = _BREAK.sub(", ", fragment)
    fragment = _TAG.sub(" ", fragment)
    fragment = html_module.unescape(fragment)
    fragment = re.sub(r"\s+", " ", fragment).replace(" ,", ",")
    return fragment.strip(" ,")


def _text(cell: str) -> str:
    cell = _SORTKEY.sub("", cell)
    cell = _HIDDEN_SPAN.sub("", cell)
    return _strip_tags(cell)


def _lines(fragment: str) -> list[str]:
    """Strip HTML while keeping list items and paragraphs on separate lines."""
    fragment = _EMBEDDED_CODE.sub(" ", fragment)
    fragment = _COMMENT.sub(" ", fragment)
    fragment = _HIDDEN_SPAN.sub(" ", fragment)
    fragment = _SORTKEY.sub(" ", fragment)
    fragment = _BREAK.sub("\n", fragment)
    fragment = re.sub(
        r"</(?:p|li|tr|ul|ol|div|h[1-6])>", "\n", fragment, flags=re.I
    )
    fragment = _TAG.sub(" ", fragment)
    fragment = html_module.unescape(fragment)
    lines = [
        re.sub(r"[ \t]+", " ", line).strip(" ,;")
        for line in fragment.splitlines()
    ]
    return [line for line in lines if line]


def _category_label(heading: str) -> str:
    label = _strip_tags(heading).strip()
    for suffix in (
        " Relic Enchants",
        " Enchantments",
        " Enchanting",
        " Enchants",
    ):
        if label.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _hidden_text(cell: str) -> str:
    match = _HIDDEN_SPAN.search(cell)
    return _strip_tags(match.group(0)) if match else ""


def format_weight(value: str) -> str:
    """Format a weight like ``300000kg`` or ``infkg`` for display."""
    text = (value or "").strip()
    lower = text.lower()
    if lower.endswith("kg"):
        number = text[:-2].replace(",", "").strip()
        if number.lower() in {"inf", "infinite", "∞"}:
            return "Infinite"
        if number.isdigit():
            return f"{int(number):,}kg"
        return text
    if lower in {"inf", "infinite", "∞"}:
        return "Infinite"
    return text


def _attr(cell: str, attribute: str) -> str:
    match = re.search(rf'{attribute}="([^"]*)"', cell, re.S)
    return html_module.unescape(match.group(1)) if match else ""


def _table(html: str, table_id: str) -> str | None:
    marker = f'id="{table_id}"'
    index = html.find(marker)
    if index == -1:
        return None
    start = html.find("<table", index)
    if start == -1:
        return None
    end = html.find("</table>", start)
    if end == -1:
        return None
    return html[start:end]


def _section_text(page_html: str, heading: str) -> str:
    """Return the plain text of one ``<h2>`` section, one item per line."""
    match = re.search(
        rf'<h2[^>]*\bid="{re.escape(heading)}"[^>]*>.*?</h2>', page_html, re.S
    )
    if match is None:
        return ""

    rest = page_html[match.end() :]
    next_heading = re.search(r"<h2\b", rest)
    if next_heading is not None:
        rest = rest[: next_heading.start()]

    rest = re.sub(r'<span class="mw-editsection">.*?</div>', " ", rest, flags=re.S)
    rest = _EMBEDDED_CODE.sub(" ", rest)
    rest = _COMMENT.sub(" ", rest)
    rest = _HIDDEN_SPAN.sub(" ", rest)
    rest = _SORTKEY.sub(" ", rest)
    rest = _BREAK.sub("\n", rest)
    rest = re.sub(
        r"</(?:p|li|tr|ul|ol|table|div|h[1-6])>", "\n", rest, flags=re.I
    )
    rest = _TAG.sub(" ", rest)
    rest = html_module.unescape(rest)

    lines = [re.sub(r"[ \t]+", " ", line).strip(" ,") for line in rest.splitlines()]
    lines = [line for line in lines if line]
    # Drop the generic lead-in ("<X> fish can be obtained through the following:")
    # so the field starts with the actual sources.
    if lines and lines[0].endswith(":"):
        lines.pop(0)
    return "\n".join(lines)


def _data_rows(table_html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if cells:
            rows.append(cells)
    return rows


def _url(cell: str, base_url: str) -> str:
    href = _attr(cell, "href")
    return urljoin(base_url, href) if href else ""


async def _cached(key: str, loader: Callable[[], Awaitable[Any]]) -> Any:
    entry = _cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        entry = _cache.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        value = await loader()
        _cache[key] = (time.monotonic() + CACHE_TTL, value)
        return value


# ------------------------------------------------------------------ loaders


async def load_mutations(wiki: WikiClient) -> list[Mutation]:
    async def loader() -> list[Mutation]:
        _, page = await wiki.parsed_html("Mutations")
        table = _table(page, "mutation-table-1")
        if table is None:
            return []
        mutations: list[Mutation] = []
        for cells in _data_rows(table):
            if len(cells) < 8:
                continue
            name = _text(cells[1])
            if not name:
                continue
            value_text = _text(cells[4])
            number_match = re.search(r"[\d.]+", value_text)
            value_number = float(number_match.group(0)) if number_match else 0.0
            status = _hidden_text(cells[6]) or _attr(cells[6], "title")
            chance = _text(cells[6])
            mutations.append(
                Mutation(
                    name=name,
                    type=_text(cells[2]),
                    source=_text(cells[3]) or "—",
                    value=value_text or "—",
                    value_number=value_number,
                    priority=_text(cells[5]) or "0",
                    appraisable=status or "No",
                    chance=chance,
                    randomized=_text(cells[7]) or "—",
                    url=_url(cells[1], wiki.base_url),
                )
            )
        mutations.sort(key=lambda item: item.value_number, reverse=True)
        return mutations

    return await _cached("mutations", loader)


async def load_obtainment(wiki: WikiClient, name: str) -> str | None:
    """Return the wiki page's ``Obtainment`` section for a mutation."""

    async def loader() -> str | None:
        try:
            _, page = await wiki.parsed_html(name)
        except WikiError:
            return None
        return _section_text(page, "Obtainment") or None

    return await _cached(f"obtainment:{name}", loader)


async def load_enchantments(wiki: WikiClient) -> list[Enchantment]:
    """Return every enchantment listed on the ``Enchanting`` page."""

    async def loader() -> list[Enchantment]:
        _, page = await wiki.parsed_html("Enchanting")
        start = page.find('<h2 id="Enchantments"')
        if start == -1:
            return []
        end = page.find('<h2 id="Badges"', start)
        region = page[start:end] if end != -1 else page[start:]

        headings = list(_HEADING.finditer(region))
        groups: list[tuple[str, str]] = []
        first_h3 = next(
            (index for index, match in enumerate(headings) if match.group(1) == "3"),
            None,
        )
        if first_h3 is None:
            groups.append(("Regular", region))
        else:
            groups.append(("Regular", region[: headings[first_h3].start()]))
            for index in range(first_h3, len(headings)):
                match = headings[index]
                if match.group(1) != "3":
                    continue
                chunk_end = (
                    headings[index + 1].start()
                    if index + 1 < len(headings)
                    else len(region)
                )
                label = _category_label(match.group(3)) or "Other"
                groups.append((label, region[match.end() : chunk_end]))

        enchantments: dict[str, Enchantment] = {}
        for category, chunk in groups:
            for row in _ROW.finditer(chunk):
                cells = _CELL.findall(row.group(2))
                if len(cells) < 2 or 'class="enchantment' not in cells[0]:
                    continue
                name = _text(cells[0])
                if not name:
                    continue
                existing = enchantments.get(name)
                if existing is not None:
                    if category not in existing.category:
                        enchantments[name] = Enchantment(
                            name=existing.name,
                            category=f"{existing.category} · {category}",
                            effects=existing.effects,
                            optimal=existing.optimal,
                            url=existing.url,
                        )
                    continue
                anchor = quote(name.replace(" ", "_"))
                enchantments[name] = Enchantment(
                    name=name,
                    category=category,
                    effects=tuple(_lines(cells[1])),
                    optimal=_text(cells[2]) if len(cells) > 2 else "",
                    url=f"{wiki.base_url}Enchanting#{anchor}",
                )
        return list(enchantments.values())

    return await _cached("enchantments", loader)


async def load_baits(wiki: WikiClient) -> list[Bait]:
    async def loader() -> list[Bait]:
        _, page = await wiki.parsed_html("Bait")
        table = _table(page, "bait-table-1")
        if table is None:
            return []
        baits: list[Bait] = []
        for cells in _data_rows(table):
            if len(cells) < 9:
                continue
            name = _text(cells[0])
            if not name:
                continue
            baits.append(
                Bait(
                    name=name,
                    rarity=_text(cells[1]) or "Unknown",
                    obtainment=_text(cells[2]) or "—",
                    pref_luck=_text(cells[3]) or "—",
                    univ_luck=_text(cells[4]) or "—",
                    resilience=_text(cells[5]) or "—",
                    lure=_text(cells[6]) or "—",
                    favoring=_text(cells[7]) or "—",
                    ability=_text(cells[8]) or "—",
                    url=_url(cells[0], wiki.base_url),
                )
            )
        return baits

    return await _cached("baits", loader)


async def load_harpoons(wiki: WikiClient) -> list[Harpoon]:
    async def loader() -> list[Harpoon]:
        _, page = await wiki.parsed_html("Harpoon Guns")
        table = _table(page, "harpoon-gun-table-1")
        if table is None:
            return []
        harpoons: list[Harpoon] = []
        for cells in _data_rows(table):
            if len(cells) < 12:
                continue
            name = _text(cells[0])
            if not name:
                continue
            harpoons.append(
                Harpoon(
                    name=name,
                    location=_text(cells[1]) or "—",
                    source=_text(cells[2]) or "—",
                    stage=_text(cells[3]) or "—",
                    power=_text(cells[4]) or "—",
                    range=_text(cells[5]) or "—",
                    reload=_text(cells[6]) or "—",
                    velocity=_text(cells[7]) or "—",
                    resilience=_text(cells[8]) or "—",
                    accuracy=_text(cells[9]) or "—",
                    max_kg=_text(cells[10]) or "—",
                    obtainable=_text(cells[11]) or "—",
                    url=_url(cells[0], wiki.base_url),
                )
            )
        return harpoons

    return await _cached("harpoons", loader)


async def load_spears(wiki: WikiClient) -> list[Spear]:
    async def loader() -> list[Spear]:
        _, page = await wiki.parsed_html("Spears")
        table = _table(page, "spear-table-1")
        if table is None:
            return []
        spears: list[Spear] = []
        for cells in _data_rows(table):
            if len(cells) < 8:
                continue
            name = _text(cells[0])
            if not name:
                continue
            spears.append(
                Spear(
                    name=name,
                    location=_text(cells[1]) or "—",
                    source=_text(cells[2]) or "—",
                    stage=_text(cells[3]) or "—",
                    power=_text(cells[4]) or "—",
                    handling=_text(cells[5]) or "—",
                    piercing=_text(cells[6]) or "—",
                    obtainable=_text(cells[7]) or "—",
                    url=_url(cells[0], wiki.base_url),
                )
            )
        return spears

    return await _cached("spears", loader)
