"""Utilitas untuk mengubah wikitext MediaWiki menjadi data/teks yang rapi.

Modul ini sengaja tidak bergantung pada discord.py supaya bisa diuji
secara terpisah lewat ``scripts/check_wiki.py``.
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
    """Hapus tag HTML dan decode entity."""
    return html.unescape(_HTML_TAG_RE.sub("", text or ""))


def split_top_level(text: str, sep: str = "|") -> list[str]:
    """Split ``text`` pada ``sep`` yang berada di level teratas.

    ``sep`` bisa berupa karakter tunggal atau beberapa karakter (mis. ``"||"``).
    Isi di dalam ``{{ ... }}`` dan ``[[ ... ]]`` tidak ikut dipecah.
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
    """Ubah satu template menjadi teks biasa."""
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

    # Template tak dikenal: tampilkan argumen pertama bila ada.
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
    # Sisa template yang tidak seimbang dibuang agar tidak tampil sebagai kode.
    return re.sub(r"\{\{[^{}]*\}\}", "", text)


def clean_wikitext(text: str) -> str:
    """Konversi potongan wikitext menjadi teks yang enak dibaca."""
    if not text:
        return ""

    text = _REF_RE.sub("", text)
    text = _REF_SELF_RE.sub("", text)
    text = _FILE_LINK_RE.sub("", text)
    text = re.sub(r"<br\s*/?>", ", ", text, flags=re.IGNORECASE)
    # Magic word dengan kurung tunggal yang dipakai wiki (mis. {space}).
    text = re.sub(r"\{space\}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\{nbsp\}", "\u00a0", text, flags=re.IGNORECASE)
    text = _expand_templates(text)

    # [[Halaman|label]] -> label, [[Halaman]] -> Halaman
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
    """Ambil isi template (tanpa ``{{ }}`` terluar) dengan pencocokan kurung."""
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
    """Ambil parameter infobox dan bersihkan nilainya.

    Mengembalikan ``None`` jika template tidak ditemukan.
    """
    body = _find_template_body(wikitext, template_name)
    if body is None:
        return None

    parts = split_top_level(body, "|")
    # parts[0] adalah nama template.
    params: dict[str, str] = {}
    for part in parts[1:]:
        match = _NAMED_PARAM_RE.match(part)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = clean_wikitext(match.group(2))
        params[key] = value
    return params


_META_SECTIONS = {"change history", "navigation", "references", "external links", "gallery"}


def clean_extract(text: str) -> str:
    """Rapikan teks hasil ``prop=extracts`` (buang heading, rapikan newline)."""
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    cleaned: list[str] = []
    for line in lines:
        if not line:
            continue
        if line.startswith("=="):
            continue
        if line.lower().rstrip(":") in _META_SECTIONS:
            continue
        cleaned.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()


def parse_codes(wikitext: str) -> list[dict[str, str]]:
    """Ambil daftar kode dari halaman ``Codes``.

    Mendukung tabel "Active Codes" dan "Inactive Codes" yang dipakai wiki.
    """
    lines = wikitext.splitlines()
    codes: list[dict[str, str]] = []
    i = 0
    n = len(lines)

    while i < n:
        if not lines[i].strip().startswith("{|"):
            i += 1
            continue

        # ---- Fase 1: baca caption dan baris header tabel.
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
                break  # baris data pertama; header sudah terbaca
            i += 1

        if not header or header[0].strip().lower() != "code":
            # Bukan tabel kode; lewati sampai akhir tabel.
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

        # ---- Fase 2: baca baris-baris data.
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
    """Ambil nilai pertama yang tidak kosong dari ``record``."""
    for key in keys:
        value = record.get(key)
        if value:
            return str(value)
    return ""
