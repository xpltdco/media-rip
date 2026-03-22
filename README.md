# media.rip()

A self-hostable yt-dlp web frontend. Paste a URL, pick quality, download — with session isolation, real-time progress, and a cyberpunk default theme.

![License](https://img.shields.io/badge/license-MIT-blue)
![Docker](https://img.shields.io/badge/docker-ghcr.io%2Fxpltdco%2Fmedia--rip-blue)

## Features

- **Paste & download** — Any URL yt-dlp supports. Format picker with live quality extraction.
- **Real-time progress** — Server-Sent Events stream download progress to the browser instantly.
- **Session isolation** — Each browser gets its own download queue. No cross-talk.
- **Playlist support** — Collapsible parent/child jobs with per-video status tracking.
- **Three built-in themes** — Cyberpunk (default), Dark, Light. Switch in the header.
- **Custom themes** — Drop a CSS file into `/themes` volume. No rebuild needed.
- **Admin panel** — Session management, storage info, manual purge, error logs. Protected by bcrypt auth.
- **Cookie auth** — Upload cookies.txt per session for paywalled/private content.
- **Auto-purge** — Configurable scheduled cleanup of old downloads and logs.
- **Zero telemetry** — No outbound requests. No CDN, no fonts, no analytics. CSP enforced.
- **Mobile-friendly** — Responsive layout with bottom tabs on small screens.

## Quickstart

```bash
docker compose up
```

Open [http://localhost:8080](http://localhost:8080) and paste a URL. On first run, you'll set an admin password.

Downloads are saved to `./downloads/`. Everything else (database, sessions, logs) lives in a named Docker volume.

> **That's it.** The defaults are production-ready: isolated sessions, admin panel with first-run setup wizard, 24h auto-purge, 3 concurrent downloads. Most users don't need to set any environment variables.

## Docker Volumes

| Mount | Purpose | Required |
|-------|---------|----------|
| `/downloads` | Downloaded media files | ✅ Bind mount recommended |
| `/data` | SQLite database, session cookies, error logs | ✅ Named volume recommended |
| `/themes` | Custom theme CSS overrides | Optional |
| `/app/config.yaml` | YAML config file | Optional |

## Configuration

Everything works out of the box. The settings below are for operators who want to tune specific behavior.

### Most Useful Settings

These are the knobs most operators actually touch — all shown commented out in `docker-compose.yml`:

| Variable | Default | When to change |
|----------|---------|----------------|
| `MEDIARIP__SESSION__MODE` | `isolated` | Set to `shared` for family/team use, `open` to disable sessions entirely |
| `MEDIARIP__DOWNLOADS__MAX_CONCURRENT` | `3` | Increase for faster connections, decrease on low-spec hardware |
| `MEDIARIP__PURGE__MAX_AGE_MINUTES` | `1440` | Raise for longer retention, or set `PURGE__ENABLED=false` to keep forever |
| `MEDIARIP__ADMIN__PASSWORD_HASH` | _(empty)_ | Pre-set to skip the first-run wizard (useful for automated deployments) |
| `MEDIARIP__YTDLP__EXTRACTOR_ARGS` | `{}` | Tune YouTube player client if downloads 403 (see [yt-dlp Tuning](#yt-dlp-tuning)) |

### All Settings

<details>
<summary>Full reference — click to expand</summary>

#### Core

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__SERVER__PORT` | `8000` | Internal server port |
| `MEDIARIP__SERVER__LOG_LEVEL` | `info` | Log level (`debug`, `info`, `warning`, `error`) |
| `MEDIARIP__DOWNLOADS__MAX_CONCURRENT` | `3` | Maximum parallel downloads |
| `MEDIARIP__SESSION__MODE` | `isolated` | `isolated`, `shared`, or `open` |
| `MEDIARIP__SESSION__TIMEOUT_HOURS` | `72` | Session cookie lifetime (hours) |

#### Admin

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__ADMIN__ENABLED` | `true` | Enable admin panel |
| `MEDIARIP__ADMIN__USERNAME` | `admin` | Admin username |
| `MEDIARIP__ADMIN__PASSWORD_HASH` | _(empty)_ | Bcrypt hash of admin password |

#### Purge

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__PURGE__ENABLED` | `true` | Enable automatic cleanup of old downloads |
| `MEDIARIP__PURGE__MAX_AGE_MINUTES` | `1440` | Delete completed downloads older than this (minutes) |
| `MEDIARIP__PURGE__CRON` | `* * * * *` | Purge check schedule (cron syntax) |
| `MEDIARIP__PURGE__PRIVACY_MODE` | `false` | Aggressive cleanup — removes downloads + logs on schedule |
| `MEDIARIP__PURGE__PRIVACY_RETENTION_MINUTES` | `1440` | Retention period when privacy mode is enabled |

#### UI

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__UI__DEFAULT_THEME` | `dark` | Default theme (`dark`, `light`, `cyberpunk`, or custom) |
| `MEDIARIP__UI__WELCOME_MESSAGE` | _(built-in)_ | Header subtitle text shown to users |

#### yt-dlp

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__YTDLP__EXTRACTOR_ARGS` | `{}` | JSON object of yt-dlp extractor args |

> **Note:** Internal paths (`SERVER__DB_PATH`, `SERVER__DATA_DIR`, `DOWNLOADS__OUTPUT_DIR`) are pre-configured in the Docker image. Only override these if you change the volume mount points.

</details>

### Session Modes

- **isolated** (default): Each browser session has its own private download queue.
- **shared**: All sessions see all downloads. Good for household/team use.
- **open**: No session tracking at all. Everyone shares one queue.

### Admin Panel

Enabled by default. On first run, you'll be prompted to set a password in the browser.

To pre-configure for automated deployments (skip the wizard):

```bash
# Generate a bcrypt hash
docker run --rm python:3.12-slim python -c \
  "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())"

# Then set in docker-compose.yml:
# MEDIARIP__ADMIN__PASSWORD_HASH=$2b$12$...your.hash...
```

### yt-dlp Tuning

If YouTube downloads fail with HTTP 403, try changing the player client:

```bash
# Environment variable
MEDIARIP__YTDLP__EXTRACTOR_ARGS='{"youtube": {"player_client": ["web_safari"]}}'
```

```yaml
# Or in config.yaml
ytdlp:
  extractor_args:
    youtube:
      player_client: ["web_safari", "android_vr"]
```

You can also upload a `cookies.txt` from a logged-in browser session via the UI for authenticated downloads.

## Custom Themes

1. Create a folder in your themes volume: `./themes/my-theme/`
2. Add `metadata.json`:
   ```json
   { "name": "My Theme", "author": "You", "description": "A cool theme" }
   ```
3. Add `theme.css` with CSS variable overrides:
   ```css
   [data-theme="my-theme"] {
     --color-bg: #1a1a2e;
     --color-accent: #e94560;
     /* See base.css for all 50+ tokens */
   }
   ```
4. Restart the container. Your theme appears in the picker.

See the built-in themes in `frontend/src/themes/` for fully commented examples.

## Secure Deployment

For production with TLS, use the included Caddy reverse proxy:

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
# Edit .env with your domain and admin password hash
docker compose up -d
```

Caddy automatically provisions Let's Encrypt TLS certificates for your domain.

## Development

### Backend

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest pytest-asyncio pytest-anyio httpx ruff
.venv/bin/python -m pytest tests/ -v -m "not integration"
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # Dev server with hot reload
npx vitest run    # Run tests
npm run build     # Production build
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check with version + uptime |
| `/api/config/public` | GET | Public configuration |
| `/api/downloads` | GET | List downloads for current session |
| `/api/downloads` | POST | Start a new download |
| `/api/downloads/{id}` | DELETE | Cancel/remove a download |
| `/api/formats` | GET | Extract available formats for a URL |
| `/api/events` | GET | SSE stream for real-time progress |
| `/api/cookies` | POST | Upload cookies.txt for authenticated downloads |
| `/api/cookies` | DELETE | Remove cookies.txt for current session |
| `/api/themes` | GET | List available custom themes |
| `/api/admin/*` | GET/POST | Admin endpoints (requires auth) |

## Architecture

- **Backend**: Python 3.12 + FastAPI + aiosqlite + yt-dlp
- **Frontend**: Vue 3 + TypeScript + Pinia + Vite
- **Transport**: Server-Sent Events for real-time progress
- **Database**: SQLite with WAL mode
- **Styling**: CSS custom properties (no Tailwind, no component library)
- **Container**: Multi-stage build, non-root user, amd64 + arm64

## License

MIT
