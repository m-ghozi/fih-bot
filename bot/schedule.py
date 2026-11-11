"""Schedule helpers for seasons and recurring spawns.

The wiki renders these countdowns with client-side JavaScript
(``MediaWiki:Countdowns.js``) using data from ``Template:Seasons`` and
``Template:Main page settings/events``. The periods are fixed, so the bot
computes the same schedule locally instead of scraping the wiki.

Season cycles are aligned to the Unix epoch: ``floor(now / 576min) mod 4``
gives Spring, Summer, Autumn, Winter. Recurring spawns repeat every
``period`` seconds from the epoch (``start = 0``, ``period_offset = 0``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

__all__ = [
    "SEASON_DURATION",
    "SEASONS",
    "SeasonSchedule",
    "SPAWNS",
    "SpawnSchedule",
    "next_occurrence",
    "season_schedule",
]

MINUTE = 60
HOUR = 3600
DAY = 86400

# Each season lasts 576 real-life minutes (9.6 hours); a full cycle is 38.4h.
SEASON_DURATION = 576 * MINUTE
SEASON_CYCLE = 4 * SEASON_DURATION
SEASONS = ("Spring", "Summer", "Autumn", "Winter")


@dataclass(frozen=True)
class SeasonSchedule:
    name: str
    start: datetime
    end: datetime
    current: bool


@dataclass(frozen=True)
class SpawnSchedule:
    name: str
    period: int
    emoji: str
    detail: str


# Periods taken from Template:Main page settings/events on the wiki.
SPAWNS: tuple[SpawnSchedule, ...] = (
    SpawnSchedule("Global Mosslurker Spawn", 4 * HOUR, "🐊", "Mosslurker"),
    SpawnSchedule("Global Narwhal Migration Spawn", 3 * HOUR, "🐋", "Narwhal Migration"),
    SpawnSchedule("Global Dreadfin Spawn", 12600, "🦈", "Dreadfin"),
    SpawnSchedule("Daily Shop Reset", DAY, "🛒", "Daily Shop"),
)


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def season_schedule(now: datetime | None = None) -> list[SeasonSchedule]:
    """Return the current and upcoming seasons in cycle order."""
    current_time = _now(now).astimezone(timezone.utc)
    slot = int(current_time.timestamp()) // SEASON_DURATION
    current_index = slot % len(SEASONS)
    current_start = slot * SEASON_DURATION

    schedule: list[SeasonSchedule] = []
    for index, name in enumerate(SEASONS):
        offset = (index - current_index) % len(SEASONS)
        start_ts = current_start + offset * SEASON_DURATION
        start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
        end = datetime.fromtimestamp(start_ts + SEASON_DURATION, tz=timezone.utc)
        schedule.append(
            SeasonSchedule(name=name, start=start, end=end, current=offset == 0)
        )
    return schedule


def next_occurrence(period: int, now: datetime | None = None) -> datetime:
    """Return the next epoch-aligned occurrence for a recurring spawn."""
    timestamp = int(_now(now).timestamp())
    next_ts = (timestamp // period + 1) * period
    return datetime.fromtimestamp(next_ts, tz=timezone.utc)


def seconds_until(moment: datetime, now: datetime | None = None) -> int:
    return max(0, int(moment.timestamp() - _now(now).timestamp()))


def format_duration(seconds: int) -> str:
    """Format a duration like ``3h 12m`` for inline text."""
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, DAY)
    hours, rest = divmod(rest, HOUR)
    minutes, secs = divmod(rest, MINUTE)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
