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

Open [http://localhost:8080](http://localhost:8080) and paste a URL.

Downloads are saved to `./downloads/`.

## Docker Volumes

| Mount | Purpose | Persists |
|-------|---------|----------|
| `/downloads` | Downloaded media files | ✅ Bind mount recommended |
| `/data` | SQLite database, session cookies, error logs | ✅ Named volume recommended |
| `/themes` | Custom theme CSS overrides (optional) | Read-only bind mount |
| `/app/config.yaml` | YAML config file (optional) | Read-only bind mount |

**Important:** The `/data` volume contains the database (download history, admin state, error logs) and session cookie files. Use a named volume or bind mount to persist across container restarts.

## Configuration

All settings have sensible defaults. Override via environment variables or `config.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__SERVER__PORT` | `8000` | Internal server port |
| `MEDIARIP__SERVER__DB_PATH` | `/data/mediarip.db` | SQLite database path |
| `MEDIARIP__SERVER__DATA_DIR` | `/data` | Persistent data directory |
| `MEDIARIP__DOWNLOADS__OUTPUT_DIR` | `/downloads` | Where files are saved |
| `MEDIARIP__DOWNLOADS__MAX_CONCURRENT` | `3` | Maximum parallel downloads |
| `MEDIARIP__SESSION__MODE` | `isolated` | `isolated`, `shared`, or `open` |
| `MEDIARIP__SESSION__TIMEOUT_HOURS` | `72` | Session cookie lifetime |
| `MEDIARIP__ADMIN__ENABLED` | `false` | Enable admin panel |
| `MEDIARIP__ADMIN__USERNAME` | `admin` | Admin username |
| `MEDIARIP__ADMIN__PASSWORD_HASH` | _(empty)_ | Bcrypt hash of admin password |
| `MEDIARIP__PURGE__ENABLED` | `false` | Enable auto-purge of old downloads |
| `MEDIARIP__PURGE__MAX_AGE_HOURS` | `168` | Delete downloads older than this |
| `MEDIARIP__PURGE__CRON` | `0 3 * * *` | Purge schedule (cron syntax) |
| `MEDIARIP__THEMES_DIR` | `/themes` | Custom themes directory |

### Session Modes

- **isolated** (default): Each browser session has its own private queue.
- **shared**: All sessions see all downloads. Good for household/team use.
- **open**: No session tracking at all.

### Admin Panel

Enable the admin panel to manage sessions, view storage, trigger manual purge, and review error logs:

```yaml
# docker-compose.yml environment section
MEDIARIP__ADMIN__ENABLED: "true"
MEDIARIP__ADMIN__USERNAME: "admin"
MEDIARIP__ADMIN__PASSWORD_HASH: "$2b$12$..."  # see below
```

Generate a bcrypt password hash:
```bash
docker run --rm python:3.12-slim python -c \
  "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())"
```

Admin state (login, settings changes) persists in the SQLite database at `/data/mediarip.db`.

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
