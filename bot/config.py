from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

DEFAULT_API_URL = "https://fischipedia.org/w/api.php"
DEFAULT_BASE_URL = "https://fischipedia.org/wiki/"
DEFAULT_USER_AGENT = "FischWikiBot/1.0 (Discord bot)"


@dataclass(frozen=True)
class Settings:
    token: str
    api_url: str
    base_url: str
    user_agent: str
    guild_id: int | None

    @classmethod
    def load(cls) -> "Settings":
        guild_raw = os.getenv("GUILD_ID", "").strip()
        guild_id: int | None = None
        if guild_raw:
            try:
                guild_id = int(guild_raw)
            except ValueError:
                guild_id = None

        return cls(
            token=os.getenv("DISCORD_TOKEN", "").strip(),
            api_url=os.getenv("WIKI_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL,
            base_url=os.getenv("WIKI_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
            user_agent=os.getenv("WIKI_USER_AGENT", DEFAULT_USER_AGENT).strip()
            or DEFAULT_USER_AGENT,
            guild_id=guild_id,
        )
