# Fisch Wiki Discord Bot

Bot Discord untuk mengambil informasi dari [Official Fisch Wiki](https://fischipedia.org/wiki/Fisch_Wiki).

Bot ini **tidak** melakukan HTML scraping. Wiki Fisch berjalan di MediaWiki, jadi bot memakai
**MediaWiki API resmi** (`https://fischipedia.org/w/api.php`) yang jauh lebih stabil dan ramah
terhadap server wiki.

## Fitur

| Command | Fungsi |
| --- | --- |
| `/wiki <kata kunci>` | Mencari halaman di wiki (dengan pagination). |
| `/page <judul>` | Menampilkan ringkasan sebuah halaman + link sumber. |
| `/fish <nama>` | Menampilkan data ikan dari `FishInfobox`: rarity, lokasi, cuaca, musim, umpan, XP, harga, peluang, dll. |
| `/codes [status]` | Daftar kode redeem (aktif / tidak aktif / semua) beserta hadiahnya. |

Semua hasil menyertakan link ke halaman aslinya. Respons API di-cache selama 5 menit agar
command yang sama tidak membebani wiki.

## Persyaratan

- Python 3.10+
- Bot Discord (token)

## 1. Membuat bot Discord

1. Buka <https://discord.com/developers/applications> lalu klik **New Application**.
2. Masuk ke tab **Bot**, klik **Reset Token**, lalu salin token-nya.
3. Tidak perlu mengaktifkan *Message Content Intent* — bot hanya memakai slash command.
4. Buka tab **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`
5. Buka URL hasil generate untuk mengundang bot ke server kamu.

## 2. Instalasi

```bash
cd fih-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Isi `.env`:

```env
DISCORD_TOKEN=token_bot_kamu
GUILD_ID=id_server_kamu   # opsional, mempercepat munculnya command
```

`GUILD_ID` berguna saat development: command langsung muncul di server tersebut. Jika
dikosongkan, command disinkronkan secara global (bisa butuh beberapa menit).

## 3. Menjalankan

```bash
python run.py
```

Saat pertama kali jalan, command akan otomatis disinkronkan ke Discord.

## Uji scraper tanpa Discord

Untuk memastikan API dan parser bekerja:

```bash
python scripts/check_wiki.py
python scripts/check_wiki.py Megalodon
```

Script ini menampilkan hasil pencarian, ringkasan halaman, isi `FishInfobox`, dan daftar kode.

## Struktur project

```
fih-bot/
├── run.py                    # entry point
├── requirements.txt
├── .env.example
├── bot/
│   ├── client.py             # subclass commands.Bot + sinkronisasi slash command
│   ├── config.py             # pembacaan .env
│   ├── wiki.py               # klien MediaWiki API + cache + retry
│   ├── parsing.py            # parser wikitext (infobox, tabel kode, template)
│   ├── ui.py                 # tombol pagination
│   └── cogs/
│       └── wiki_commands.py  # definisi /wiki, /page, /fish, /codes
└── scripts/
    └── check_wiki.py         # uji scraper tanpa Discord
```

## Cara kerja pengambilan data

- `/wiki` → `action=query&list=search`
- `/page` → `action=query&prop=extracts|pageimages`
- `/fish` → `action=parse&prop=wikitext`, lalu parameter `{{FishInfobox}}` di-parse
- `/codes` → `action=parse&prop=wikitext` halaman `Codes`, lalu tabel *Active Codes* /
  *Inactive Codes* di-parse

Karena berbasis API, perubahan layout halaman tidak akan merusak bot selama nama template
(`FishInfobox`) dan struktur tabel kode tidak berubah drastis.

## Catatan

- Isi wiki dilisensikan **CC BY-NC-SA 4.0**. Atribusi sumber sudah dicantumkan di footer
  setiap embed. Jangan gunakan untuk keperluan komersial.
- Hormati wiki: bot mengirim `User-Agent` yang jelas, memakai `maxlag=5`, dan melakukan
  cache. Ubah `WIKI_USER_AGENT` agar menyertakan kontak kamu bila bot dipakai publik.
- Jika wiki mengubah nama template atau struktur tabel kode, sesuaikan
  `bot/parsing.py`.
