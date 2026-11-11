"""Formatting helpers for colored Discord output.

Discord only renders text colors inside ANSI code blocks, so the helpers
here build those blocks. Embed side colors and emoji are used elsewhere for
additional color cues.
"""

from __future__ import annotations

import discord

__all__ = [
    "ansi",
    "ansi_table",
    "code_block",
    "pad",
    "rarity_color",
    "rarity_dot",
    "rod_color",
    "sign_color",
    "weather_text",
    "season_text",
]

RESET = "\x1b[0m"
BOLD = "\x1b[1m"

ANSI_COLORS = {
    "gray": "\x1b[30m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "magenta": "\x1b[35m",
    "cyan": "\x1b[36m",
    "white": "\x1b[37m",
    "bright_red": "\x1b[91m",
    "bright_green": "\x1b[92m",
    "bright_yellow": "\x1b[93m",
    "bright_blue": "\x1b[94m",
    "bright_magenta": "\x1b[95m",
    "bright_cyan": "\x1b[96m",
}

# rarity -> (embed hex, ansi color, dot emoji)
_RARITY = {
    "trash": ("#8a8a8a", "gray", "⚫"),
    "common": ("#95a5a6", "gray", "⚪"),
    "uncommon": ("#2ecc71", "green", "🟢"),
    "unusual": ("#1abc9c", "cyan", "🔵"),
    "rare": ("#3498db", "blue", "🔵"),
    "legendary": ("#f1c40f", "yellow", "🟡"),
    "mythical": ("#9b59b6", "magenta", "🟣"),
    "relic": ("#e91e63", "magenta", "🟣"),
    "exotic": ("#ff9800", "yellow", "🟠"),
    "apex": ("#e74c3c", "red", "🔴"),
    "limited": ("#ff69b4", "magenta", "🟣"),
    "secret": ("#7b1fa2", "magenta", "🟣"),
    "extinct": ("#616161", "gray", "⚫"),
    "special": ("#00bcd4", "cyan", "🔵"),
    "fragment": ("#00bcd4", "cyan", "🔵"),
    "gemstone": ("#00bcd4", "cyan", "🔵"),
    "seed": ("#66bb6a", "green", "🟢"),
}

_DEFAULT_RARITY = ("#3ba7d8", "blue", "🔵")

_STAGE_COLORS = [
    "#7ed957",
    "#a3e635",
    "#facc15",
    "#fb923c",
    "#ef4444",
    "#a855f7",
    "#3b82f6",
]

_WEATHER = {
    "rain": "🌧️ Rain",
    "clear": "☀️ Clear",
    "fog": "🌫️ Fog",
    "wind": "💨 Wind",
    "storm": "⛈️ Storm",
    "snow": "❄️ Snow",
    "heat": "🔥 Heat",
    "sandstorm": "🌪️ Sandstorm",
}

_SEASON = {
    "spring": "🌸 Spring",
    "summer": "☀️ Summer",
    "autumn": "🍂 Autumn",
    "winter": "❄️ Winter",
}


def ansi(text: str, color: str = "white", *, bold: bool = False) -> str:
    prefix = (BOLD if bold else "") + ANSI_COLORS.get(color, "")
    return f"{prefix}{text}{RESET}"


def pad(text: object, width: int, align: str = "left") -> str:
    value = str(text)
    if len(value) >= width:
        return value
    fill = " " * (width - len(value))
    return value + fill if align == "left" else fill + value


def code_block(lines: list[str] | str, lang: str = "ansi") -> str:
    body = "\n".join(lines) if isinstance(lines, (list, tuple)) else lines
    return f"```{lang}\n{body}\n```"


def ansi_table(
    rows: list[tuple[str, str, str]], *, label_width: int = 13, value_width: int = 9
) -> str:
    """Render ``(label, value, color)`` rows as a colored ANSI table."""
    lines = [
        f"{ansi(pad(label, label_width), 'cyan', bold=True)}"
        f"{ansi(pad(value, value_width, 'right'), color)}"
        for label, value, color in rows
    ]
    return code_block(lines)


def rarity_color(rarity: str | None) -> discord.Color:
    hex_color = _RARITY.get((rarity or "").strip().lower(), _DEFAULT_RARITY)[0]
    return discord.Color.from_str(hex_color)


def rarity_dot(rarity: str | None) -> str:
    return _RARITY.get((rarity or "").strip().lower(), _DEFAULT_RARITY)[2]


def rod_color(menu_color: str | None, stage: str | None) -> discord.Color:
    if menu_color:
        try:
            return discord.Color.from_str(menu_color)
        except ValueError:
            pass
    if stage and stage.strip().isdigit():
        index = min(max(int(stage) - 1, 0), len(_STAGE_COLORS) - 1)
        return discord.Color.from_str(_STAGE_COLORS[index])
    return discord.Color.from_str("#3ba7d8")


def sign_color(value: str | None) -> str:
    text = (value or "").strip().replace(",", "").replace("%", "").replace("+", "")
    try:
        number = float(text)
    except ValueError:
        return "white"
    if number < 0:
        return "red"
    if number > 0:
        return "green"
    return "gray"


def _format_multivalue(value: str, mapping: dict[str, str]) -> str:
    parts = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return ", ".join(mapping.get(part.lower(), part) for part in parts)


def weather_text(value: str) -> str:
    return _format_multivalue(value, _WEATHER)


def season_text(value: str) -> str:
    return _format_multivalue(value, _SEASON)
