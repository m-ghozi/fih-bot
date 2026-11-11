"""Utilities for turning MediaWiki wikitext into clean data and text.

This module intentionally does not depend on discord.py so it can be tested
separately through ``scripts/check_wiki.py``.
"""

from __future__ import annotations

import html
import re
from typing import Any

__all__ = [
    "clean_wikitext",
    "parse_infobox",
    "parse_codes",
    "clean_extract",
    "split_top_level",
    "strip_html",
    "extract_section",
    "extract_template_version",
]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_INNER_TEMPLATE_RE = re.compile(r"\{\{([^{}]*)\}\}")
_LINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]*))?\]\]")
_EXTERNAL_LINK_RE = re.compile(r"\[(https?://\S+)\s+([^\]]+)\]")
_FILE_LINK_RE = re.compile(r"\[\[(?:File|Image):[^\]]*\]\]", re.IGNORECASE)
_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>", re.IGNORECASE | re.DOTALL)
_REF_SELF_RE = re.compile(r"<ref[^>]*/\s*>", re.IGNORECASE)
_NAMED_PARAM_RE = re.compile(r"^([A-Za-z0-9_\- ]+)\s*=\s*(.*)$", re.DOTALL)

_MAX_TEMPLATE_PASSES = 25


def strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    return html.unescape(_HTML_TAG_RE.sub("", text or ""))


def split_top_level(text: str, sep: str = "|") -> list[str]:
    """Split ``text`` on top-level occurrences of ``sep``.

    ``sep`` may be one character or several (e.g. ``"||"``). Content inside
    ``{{ ... }}`` and ``[[ ... ]]`` is never split.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    i = 0
    n = len(text)

    while i < n:
        two = text[i : i + 2]
        if two in ("{{", "[["):
            depth += 1
            buf.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            buf.append(two)
            i += 2
            continue
        if depth == 0 and text.startswith(sep, i):
            parts.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        buf.append(text[i])
        i += 1

    parts.append("".join(buf))
    return parts


def _zero_pad(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value.zfill(2)
    return value


def _render_template(name: str, args: list[str]) -> str:
    """Turn a single template into plain text."""
    name = name.strip()
    lower = name.lower()

    if lower.startswith("#") or lower.startswith("pagesin") or lower.startswith("formatnum"):
        return ""
    if lower == "!":
        return "|"
    if lower == "=":
        return "="

    positional: list[str] = []
    named: dict[str, str] = {}
    for arg in args:
        match = _NAMED_PARAM_RE.match(arg)
        if match:
            named[match.group(1).strip().lower()] = match.group(2).strip()
        else:
            positional.append(arg.strip())

    def pos(index: int, default: str = "") -> str:
        return positional[index] if len(positional) > index else default

    if lower in {"code", "rarity", "tt", "description", "effect", "tooltip"}:
        return pos(0)
    if lower in {"none", "na", "n/a"}:
        return "N/A"
    if lower == "date":
        y, m, d = pos(0), pos(1), pos(2)
        if not y:
            return ""
        if m and d:
            return f"{y}-{_zero_pad(m)}-{_zero_pad(d)}"
        return "-".join(part for part in (y, m, d) if part)
    if lower in {"c$", "cash", "money"}:
        return f"{pos(0)} Cash".strip()
    if lower == "treats":
        return f"{pos(0)} Treats".strip()
    if lower == "xp":
        return f"{pos(0)} XP".strip()
    if lower in {"kg", "weight"}:
        return f"{pos(0)} kg".strip()
    if lower == "bait":
        amount = pos(1)
        return f"{pos(0)} x{amount}" if amount else pos(0)
    if lower == "item":
        item_type = named.get("type", "")
        return f"{pos(0)} ({item_type})" if item_type else pos(0)
    if lower == "skin":
        return pos(0)
    if lower == "boat":
        return pos(0)
    if lower in {"playertitle", "player_title"}:
        return pos(0)
    if lower == "title":
        return pos(0)
    if lower == "color":
        return ""

    # Unknown template: show the first positional argument when available.
    return pos(0) or named.get("text", "")


def _expand_templates(text: str) -> str:
    for _ in range(_MAX_TEMPLATE_PASSES):
        def replace(match: re.Match[str]) -> str:
            inner = match.group(1)
            parts = split_top_level(inner, "|")
            return _render_template(parts[0], parts[1:])

        new_text, count = _INNER_TEMPLATE_RE.subn(replace, text)
        text = new_text
        if count == 0:
            break
    # Drop any unbalanced leftovers so they never show up as raw code.
    return re.sub(r"\{\{[^{}]*\}\}", "", text)


def clean_wikitext(text: str) -> str:
    """Convert a wikitext snippet into readable text."""
    if not text:
        return ""

    text = _REF_RE.sub("", text)
    text = _REF_SELF_RE.sub("", text)
    text = _FILE_LINK_RE.sub("", text)
    text = re.sub(r"<br\s*/?>", ", ", text, flags=re.IGNORECASE)
    # Single-brace magic words used by the wiki (e.g. {space}).
    text = re.sub(r"\{space\}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\{nbsp\}", "\u00a0", text, flags=re.IGNORECASE)
    text = _expand_templates(text)

    # [[Page|label]] -> label, [[Page]] -> Page
    previous = None
    while previous != text:
        previous = text
        text = _LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)

    text = _EXTERNAL_LINK_RE.sub(lambda m: m.group(2).strip(), text)
    text = strip_html(text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\[\[|\]\]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip(" \n\t|")


def _find_template_body(wikitext: str, template_name: str) -> str | None:
    """Return the template body (without outer ``{{ }}``) using brace matching."""
    lowered = wikitext.lower()
    marker = "{{" + template_name.lower()
    start = lowered.find(marker)
    if start == -1:
        return None

    depth = 0
    i = start
    n = len(wikitext)
    while i < n - 1:
        pair = wikitext[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start + 2 : i - 2]
            continue
        i += 1
    return None


def parse_infobox(wikitext: str, template_name: str = "FishInfobox") -> dict[str, str] | None:
    """Extract infobox parameters and clean their values.

    Returns ``None`` when the template is not found.
    """
    body = _find_template_body(wikitext, template_name)
    if body is None:
        return None

    parts = split_top_level(body, "|")
    # parts[0] is the template name.
    params: dict[str, str] = {}
    for part in parts[1:]:
        match = _NAMED_PARAM_RE.match(part)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = clean_wikitext(match.group(2))
        params[key] = value
    return params


def extract_section(wikitext: str, heading: str) -> str:
    """Return the body of a heading section (any level), without the heading."""
    if not wikitext:
        return ""

    heading_re = re.compile(
        r"(?m)^(==+)[ \t]*" + re.escape(heading) + r"[ \t]*\1[ \t]*$"
    )
    match = heading_re.search(wikitext)
    if not match:
        return ""

    level = len(match.group(1))
    start = match.end()
    next_re = re.compile(r"(?m)^(={2,})[ \t]*[^=\n]+?[ \t]*\1[ \t]*$")
    for next_heading in next_re.finditer(wikitext, start):
        if len(next_heading.group(1)) <= level:
            return wikitext[start : next_heading.start()].strip()
    return wikitext[start:].strip()


def extract_template_version(text: str, template_name: str = "Subjective") -> str:
    """Return the version argument of a template such as ``{{Subjective|1.58.0}}``."""
    match = re.search(
        r"\{\{" + re.escape(template_name) + r"\s*\|([^}|]+)", text, re.IGNORECASE
    )
    return match.group(1).strip() if match else ""


_META_SECTIONS = {"change history", "navigation", "references", "external links", "gallery"}

def clean_extract(text: str) -> str:
    """Tidy text returned by ``prop=extracts`` (drop headings, fix newlines)."""
    if not text:
        return ""
    cleaned: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("=="):
            continue
        if line.lower().rstrip(":") in _META_SECTIONS:
            continue
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


def parse_codes(wikitext: str) -> list[dict[str, str]]:
    """Extract the code list from the ``Codes`` page.

    Supports the "Active Codes" and "Inactive Codes" tables used by the wiki.
    """
    lines = wikitext.splitlines()
    codes: list[dict[str, str]] = []
    i = 0
    n = len(lines)

    while i < n:
        if not lines[i].strip().startswith("{|"):
            i += 1
            continue

        # ---- Phase 1: read the caption and the table header row.
        i += 1
        caption = ""
        header: list[str] | None = None
        while i < n:
            stripped = lines[i].strip()
            if stripped.startswith("|}"):
                i += 1
                break
            if stripped.startswith("|+"):
                caption = clean_wikitext(stripped[2:])
            elif stripped.startswith("!"):
                header = [
                    clean_wikitext(cell) for cell in split_top_level(stripped[1:], "!!")
                ]
            elif stripped.startswith("|") and not stripped.startswith("|-"):
                break  # first data row; header has been read
            i += 1

        if not header or header[0].strip().lower() != "code":
            # Not a code table; skip to the end of the table.
            while i < n and not lines[i].strip().startswith("|}"):
                i += 1
            i += 1
            continue

        status = "inactive" if "inactive" in caption.lower() else "active"
        columns = [column.strip().lower() for column in header]
        current_row: list[list[str]] = []

        def flush_row(row: list[list[str]]) -> None:
            if not row:
                return
            cells = [cell for group in row for cell in group]
            if len(cells) < 2:
                return
            record = {
                column: cells[idx] if idx < len(cells) else ""
                for idx, column in enumerate(columns)
            }
            code = record.get("code", "").strip()
            if not code:
                return
            codes.append(
                {
                    "code": code,
                    "level": record.get("level req.", "N/A") or "N/A",
                    "added": record.get("date added", ""),
                    "expires": record.get("expires", record.get("date expired", "")),
                    "rewards": record.get("rewards", ""),
                    "status": status,
                }
            )

        # ---- Phase 2: read the data rows.
        while i < n:
            stripped = lines[i].strip()
            if stripped.startswith("|}"):
                flush_row(current_row)
                i += 1
                break
            if stripped.startswith("|-"):
                flush_row(current_row)
                current_row = []
            elif stripped.startswith("|") and not stripped.startswith("|+"):
                cells = [clean_wikitext(cell) for cell in split_top_level(stripped[1:], "||")]
                current_row.append(cells)
            i += 1

    return codes


def pick(record: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty value from ``record``."""
    for key in keys:
        value = record.get(key)
        if value:
            return str(value)
    return ""
