# Fisch Wiki Discord Bot

A Discord bot that fetches information from the [Official Fisch Wiki](https://fischipedia.org/wiki/Fisch_Wiki).

This bot does **not** scrape HTML. The Fisch wiki runs on MediaWiki, so the bot uses the
**official MediaWiki API** (`https://fischipedia.org/w/api.php`), which is far more stable
and friendly to the wiki servers.

## Features

All commands work both as prefix commands (`!`) and slash commands (`/`).

| Command | Description |
| --- | --- |
| `!wiki <query>` / `/wiki` | Search wiki pages (with pagination). |
| `!page <title>` / `/page` | Show a page summary plus a link to the source. |
| `!fish <name>` / `/fish` | Show fish data from `FishInfobox`: rarity, location, weather, season, bait, XP, value, catch chance, and more. |
| `!rod <name>` / `/rod` | Show fishing rod stats (stage, price, lure, luck, control, resilience, max kg, line distance, disturbance) and its ability. |
| `!enchant <name>` / `/enchant` | Show the wiki's recommended enchantments for a rod (keeperbound, optimal grinding, and other options). |
| `!codes [status]` / `/codes` | List redeem codes (active / inactive / all) with their rewards. |
| `!status` / `/status` | Show bot health, WebSocket and wiki API latency, uptime, and server info. |
| `!info` / `/info` | Show developer, source code, version, and data-source information. |
| `!help [command]` / `/help` | List every command, or show usage and parameters for one command. |

Examples:

```
!wiki megalodon
!fish salmon
!rod trident rod
!enchant no-life rod
!codes all
!status
!info
!help rod
```

`/rod` and `/enchant` also offer slash-command autocomplete for rod names. Partial names work too, e.g. `!rod trident` or `!rod no-life`.

Every result includes a link to the original page. API responses are cached for 5 minutes
so repeated commands do not hammer the wiki.

## Requirements

- Python 3.10+
- A Discord bot (token)

## 1. Create a Discord bot

1. Open <https://discord.com/developers/applications> and click **New Application**.
2. Go to the **Bot** tab, click **Reset Token**, and copy the token.
3. Still on the **Bot** tab, enable **Message Content Intent** under *Privileged Gateway Intents*. This is required for the `!` prefix commands (slash commands work without it).
4. Open **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `View Channels`, `Send Messages`, `Embed Links`
5. Open the generated URL to invite the bot to your server.

## 2. Installation

```bash
cd fih-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```env
DISCORD_TOKEN=your_bot_token
GUILD_ID=your_server_id   # optional, makes commands appear faster
```

`GUILD_ID` is useful during development: commands appear immediately in that server. If
left empty, commands are synced globally (this can take a few minutes).

## 3. Running

```bash
python run.py
```

On the first run, commands are automatically synced to Discord.

## Test the scraper without Discord

To verify that the API and parser work:

```bash
python scripts/check_wiki.py
python scripts/check_wiki.py Megalodon
```

This script prints search results, the page summary, the `FishInfobox` contents, and the
code list.

## Project structure

```
fih-bot/
├── run.py                    # entry point
├── requirements.txt
├── .env.example
├── bot/
│   ├── client.py             # commands.Bot subclass + slash command sync
│   ├── config.py             # .env loading
│   ├── wiki.py               # MediaWiki API client + cache + retry
│   ├── parsing.py            # wikitext parser (infobox, code tables, templates)
│   ├── ui.py                 # pagination buttons
│   └── cogs/
│       ├── wiki_commands.py  # /wiki, /page, /fish, /codes
│       ├── rod_commands.py   # /rod, /enchant
│       └── general_commands.py # /status, /info, /help
└── scripts/
    └── check_wiki.py         # scraper check without Discord
```

## How data is fetched

- `/wiki` → `action=query&list=search`
- `/page` → `action=query&prop=extracts|pageimages`
- `/fish` → `action=parse&prop=wikitext`, then the `{{FishInfobox}}` parameters are parsed
- `/rod` → `action=parse&prop=wikitext` for the `{{RodInfobox}}` stats and the `== Ability ==` section
- `/enchant` → the `== Enchanting ==` section is parsed from the rod page
- `/codes` → `action=parse&prop=wikitext` for the `Codes` page, then the *Active Codes* /
  *Inactive Codes* tables are parsed

Because this is API-based, layout changes will not break the bot as long as the
`FishInfobox` template name and the code table structure stay roughly the same.

## Notes

- Wiki content is licensed under **CC BY-NC-SA 4.0**. Source attribution is included in
  every embed footer. Do not use it for commercial purposes.
- Be respectful to the wiki: the bot sends a clear `User-Agent`, uses `maxlag=5`, and
  caches responses. Update `WIKI_USER_AGENT` to include your contact info if the bot is
  used publicly.
- If the wiki renames the template or changes the code table structure, adjust
  `bot/parsing.py`.
