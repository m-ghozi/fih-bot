"""Rod Mastery data parsed from the wiki's rendered mastery panels.

The wiki stores each rod's mastery quests in a ``{{Rod Mastery}}`` template.
The rendered HTML already turns every link, item, and quantity into readable
text, so we parse that instead of re-implementing the template. Results are
cached for an hour, the same way the item catalogs are.
"""

from __future__ import annotations

import asyncio
import html as html_module
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import quote

from .wiki import PageNotFoundError, WikiClient

__all__ = [
    "MasteryQuest",
    "RodMastery",
    "load_mastery",
    "load_mastery_rods",
]

CACHE_TTL = 3600.0
MASTERY_CATEGORY = "Fishing Rods with Mastery"

_STYLE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BREAK = re.compile(r"<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")

_cache: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class MasteryQuest:
    name: str
    description: str
    reward: str
    note: str


@dataclass(frozen=True)
class RodMastery:
    title: str
    level: str
    grand_reward: str
    quests: tuple[MasteryQuest, ...]
    url: str


# ------------------------------------------------------------------ helpers


def _text(fragment: str) -> str:
    """Turn a rendered HTML fragment into a single readable line."""
    fragment = _STYLE.sub("", fragment)
    fragment = _COMMENT.sub("", fragment)
    fragment = _BREAK.sub(", ", fragment)
    fragment = _TAG.sub(" ", fragment)
    fragment = html_module.unescape(fragment)
    fragment = re.sub(r"\s+", " ", fragment)
    # Drop footnote markers such as "[ Note 1 ]"; they point to wiki notes.
    fragment = re.sub(r"\s*\[\s*note\s*\d+\s*\]", "", fragment, flags=re.I)
    # Remove the space tags leave in front of punctuation.
    fragment = re.sub(r"\s+([,.;:!?)])", r"\1", fragment)
    fragment = re.sub(r"\(\s+", "(", fragment)
    # The rendered wiki sometimes repeats the item type, e.g. "Bobber Bobber".
    fragment = re.sub(
        r"\b(Bobber|Lantern|Boat|Title|Skin|Enhancement)\s+\1\b",
        r"\1",
        fragment,
        flags=re.I,
    )
    return fragment.strip(" ,")


def _strip_reward_prefix(value: str) -> str:
    return re.sub(r"^reward\s*:\s*", "", value, flags=re.I).strip()


def _mastery_section(page: str) -> str | None:
    marker = page.find('id="Mastery"')
    if marker == -1:
        return None
    end = page.find("<h2", marker + 10)
    return page[marker : end if end != -1 else len(page)]


def _parse_section(page: str, title: str, base_url: str) -> RodMastery | None:
    section = _mastery_section(page)
    if section is None:
        return None

    level_match = re.search(
        r"Starting Level Requirement:\s*<b>(.*?)</b>", section, re.S | re.I
    )
    level = _text(level_match.group(1)) if level_match else ""

    grand_reward = ""
    quests: list[MasteryQuest] = []

    blocks = re.split(r'(?=<div class="rod-mastery-challenge)', section)[1:]
    for block in blocks:
        is_grand = "rod-mastery-grand" in block[:250]

        header = re.search(r"rod-mastery-header.*?<i>(.*?)</i>", block, re.S)
        description = re.search(
            r'class="rod-mastery-description">(.*?)</div>', block, re.S
        )
        reward = re.search(r'class="rod-mastery-reward">(.*?)</div>', block, re.S)
        note = re.search(
            r'class="rod-mastery-reward-note">(.*?)</div>', block, re.S
        )

        reward_text = _strip_reward_prefix(_text(reward.group(1))) if reward else ""

        if is_grand:
            grand_reward = reward_text
            continue

        name = _text(header.group(1)) if header else ""
        if not name:
            continue
        quests.append(
            MasteryQuest(
                name=name,
                description=_text(description.group(1)) if description else "",
                reward=reward_text,
                note=_text(note.group(1)) if note else "",
            )
        )

    return RodMastery(
        title=title,
        level=level,
        grand_reward=grand_reward,
        quests=tuple(quests),
        url=base_url + quote(title.replace(" ", "_")),
    )


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


async def load_mastery_rods(wiki: WikiClient) -> list[str]:
    """Return the names of every rod that has a Rod Mastery questline."""

    async def loader() -> list[str]:
        members = await wiki.category_members(MASTERY_CATEGORY)
        return sorted(dict.fromkeys(members), key=str.lower)

    return await _cached("mastery:rods", loader)


async def load_mastery(wiki: WikiClient, title: str) -> RodMastery | None:
    """Return the mastery questline for ``title``, or ``None`` if it has none."""

    async def loader() -> RodMastery | None:
        try:
            page_title, page = await wiki.parsed_html(title)
        except PageNotFoundError:
            return None
        return _parse_section(page, page_title, wiki.base_url)

    return await _cached(f"mastery:{title.lower()}", loader)
