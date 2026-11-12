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
| `!mastery [rod]` / `/mastery` | List rods with Rod Mastery, or show a rod's mastery quests, starting level, and rewards. |
| `!codes [status]` / `/codes` | List redeem codes (active / inactive / all) with their rewards. |
| `!mutations [query]` / `/mutations` | List fish mutations with value multipliers, priority, source, and appraisable chance. |
| `!bait [query]` / `/bait` | List bait rarity, preferred/universal luck, resilience, lure speed, and abilities. |
| `!harpoon [query]` / `/harpoon` | List harpoon gun stats: power, range, reload, velocity, resilience, accuracy, and max kg. |
| `!spear [query]` / `/spear` | List spear stats: power, handling, piercing, location, and source. |
| `!seasons` / `/seasons` | Show the current season, upcoming rotation, and seasonal spawn-rate effects. |
| `!spawn` / `/spawn` | Show the next global spawns (Mosslurker, Narwhal Migration, Dreadfin) and the Daily Shop reset. |
| `!status` / `/status` | Show bot health, WebSocket and wiki API latency, uptime, and server info. |
| `!info` / `/info` | Show developer, source code, version, and data-source information. |
| `!help [command]` / `/help` | List every command, or show usage and parameters for one command. |

Examples:

```
!wiki megalodon
!fish salmon
!rod trident rod
!enchant no-life rod
!mastery trident rod
!codes all
!mutations ghost
!bait worm
!harpoon crystal
!spear artisan
!seasons
!spawn
!status
!info
!help rod
```

`/rod`, `/enchant`, and `/mastery` also offer slash-command autocomplete for rod names. Partial names work too, e.g. `!rod trident`, `!enchant no-life`, or `!mastery trident`.
`/fish` accepts multi-word names and is case-insensitive after lookup, so `!fish whale shark` finds **Whale Shark** even though wiki titles are case-sensitive.

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

`GUILD_ID` is useful during development: the bot always syncs commands globally so
every server sees them, and it additionally syncs to this guild so changes show up
immediately there. Global command updates can take a few minutes to reach all servers.

## 3. Running

### systemd user service (recommended)

```bash
bash deploy/install-service.sh
```

The installer creates `~/.config/systemd/user/fih-bot.service`, enables it now and at
boot, and restarts the bot automatically if it crashes.

```bash
systemctl --user status fih-bot
systemctl --user restart fih-bot
journalctl --user -u fih-bot -f      # live logs
```

To remove the service:

```bash
bash deploy/uninstall-service.sh
```

### Manual run

```bash
python run.py
```

On the first run, commands are automatically synced to Discord.

### Logging

- Under systemd, logs go to journald: `journalctl --user -u fih-bot -f`.
- Set `LOG_FILE=/path/to/bot.log` in `.env` to also write a rotating file
  (5 MB, 3 backups).
- Set `LOG_LEVEL=DEBUG` in `.env` for more detail.

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
├── deploy/
│   ├── fih-bot.service.in    # systemd unit template
│   ├── install-service.sh    # install + enable the user service
│   └── uninstall-service.sh  # remove the service
├── bot/
│   ├── client.py             # commands.Bot subclass + slash command sync
│   ├── config.py             # .env loading
│   ├── wiki.py               # MediaWiki API client + cache + retry
│   ├── parsing.py            # wikitext parser (infobox, code tables, templates)
│   ├── catalogs.py           # mutation/bait/harpoon/spear table parser + cache
│   ├── mastery.py            # rod mastery quest parser + cache
│   ├── schedule.py           # season cycle + recurring spawn timers
│   ├── ui.py                 # pagination buttons
│   └── cogs/
│       ├── wiki_commands.py  # /wiki, /page, /fish, /codes
│       ├── rod_commands.py   # /rod, /enchant, /mastery
│       ├── catalog_commands.py # /mutations, /bait, /harpoon, /spear
│       ├── schedule_commands.py # /seasons, /spawn
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
- `/mastery` → the rendered Rod Mastery panels from the rod page, parsed once and cached for an hour
- `/codes` → `action=parse&prop=wikitext` for the `Codes` page, then the *Active Codes* /
  *Inactive Codes* tables are parsed
- `/seasons` and `/spawn` → computed locally from the fixed wiki schedules
  (`Template:Seasons`, `Template:Main page settings/events`); no API call is needed
- `/mutations`, `/bait`, `/harpoon`, `/spear` → rendered tables from the
  `Mutations`, `Bait`, `Harpoon Guns`, and `Spears` pages, parsed once and cached for an hour

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
