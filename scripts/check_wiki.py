#!/usr/bin/env python3
"""Uji cepat scraper tanpa perlu Discord.

Jalankan dari root project:

    python scripts/check_wiki.py
    python scripts/check_wiki.py salmon
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Settings  # noqa: E402
from bot.parsing import parse_codes, parse_infobox  # noqa: E402
from bot.wiki import WikiClient  # noqa: E402


async def main() -> None:
    settings = Settings.load()
    wiki = WikiClient(settings.api_url, settings.user_agent, base_url=settings.base_url)
    fish_name = sys.argv[1] if len(sys.argv) > 1 else "Salmon"

    try:
        print(f"== Pencarian: {fish_name} ==")
        for result in await wiki.search(fish_name, limit=5):
            print(f"- {result.title} -> {result.url}")

        print(f"\n== Ringkasan halaman: {fish_name} ==")
        info = await wiki.page(fish_name)
        print(f"{info.title} (missing={info.missing})")
        print(info.extract[:500])

        print(f"\n== Infobox ikan: {fish_name} ==")
        _, wikitext = await wiki.wikitext(fish_name)
        box = parse_infobox(wikitext, "FishInfobox")
        if box is None:
            print("(tidak ada FishInfobox)")
        else:
            for key, value in box.items():
                print(f"{key:16}: {value}")

        print("\n== Kode redeem ==")
        _, codes_text = await wiki.wikitext("Codes")
        codes = parse_codes(codes_text)
        print(f"Total: {len(codes)} (aktif: {sum(c['status'] == 'active' for c in codes)})")
        for code in codes[:5]:
            print(f"- [{code['status']}] {code['code']} | {code['expires']} | {code['rewards'][:80]}")
    finally:
        await wiki.close()


if __name__ == "__main__":
    asyncio.run(main())
