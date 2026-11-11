# Fisch Wiki Discord Bot

A Discord bot that fetches information from the [Official Fisch Wiki](https://fischipedia.org/wiki/Fisch_Wiki).

This bot does **not** scrape HTML. The Fisch wiki runs on MediaWiki, so the bot uses the
**official MediaWiki API** (`https://fischipedia.org/w/api.php`), which is far more stable
and friendly to the wiki servers.

## Features

| Command | Description |
| --- | --- |
| `/wiki <query>` | Search wiki pages (with pagination). |
| `/page <title>` | Show a page summary plus a link to the source. |
| `/fish <name>` | Show fish data from `FishInfobox`: rarity, location, weather, season, bait, XP, value, catch chance, and more. |
| `/codes [status]` | List redeem codes (active / inactive / all) with their rewards. |

Every result includes a link to the original page. API responses are cached for 5 minutes
so repeated commands do not hammer the wiki.

## Requirements

- Python 3.10+
- A Discord bot (token)

## 1. Create a Discord bot

1. Open <https://discord.com/developers/applications> and click **New Application**.
2. Go to the **Bot** tab, click **Reset Token**, and copy the token.
3. You do not need to enable *Message Content Intent* — the bot only uses slash commands.
4. Open **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`
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
│       └── wiki_commands.py  # /wiki, /page, /fish, /codes
└── scripts/
    └── check_wiki.py         # scraper check without Discord
```

## How data is fetched

- `/wiki` → `action=query&list=search`
- `/page` → `action=query&prop=extracts|pageimages`
- `/fish` → `action=parse&prop=wikitext`, then the `{{FishInfobox}}` parameters are parsed
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
