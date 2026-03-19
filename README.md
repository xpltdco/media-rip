# media.rip()

A self-hostable yt-dlp web frontend. Paste a URL, pick quality, download — with session isolation, real-time progress, and a cyberpunk default theme.

![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Paste & download** — Any URL yt-dlp supports. Format picker with live quality extraction.
- **Real-time progress** — Server-Sent Events stream download progress to the browser instantly.
- **Session isolation** — Each browser gets its own download queue. No cross-talk.
- **Three built-in themes** — Cyberpunk (default), Dark, Light. Switch in the header.
- **Custom themes** — Drop a CSS file into `/themes` volume. No rebuild needed.
- **Admin panel** — Session management, storage info, manual purge. Protected by HTTP Basic + bcrypt.
- **Zero telemetry** — No outbound requests. Your downloads are your business.
- **Mobile-friendly** — Responsive layout with bottom tabs on small screens.

## Quickstart

```bash
docker compose up
```

Open [http://localhost:8080](http://localhost:8080) and paste a URL.

Downloads are saved to `./downloads/`.

## Configuration

All settings have sensible defaults. Override via environment variables or `config.yaml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEDIARIP__SERVER__PORT` | `8000` | Internal server port |
| `MEDIARIP__DOWNLOADS__OUTPUT_DIR` | `/downloads` | Where files are saved |
| `MEDIARIP__DOWNLOADS__MAX_CONCURRENT` | `3` | Maximum parallel downloads |
| `MEDIARIP__SESSION__MODE` | `isolated` | `isolated`, `shared`, or `open` |
| `MEDIARIP__SESSION__TIMEOUT_HOURS` | `72` | Session cookie lifetime |
| `MEDIARIP__ADMIN__ENABLED` | `false` | Enable admin panel |
| `MEDIARIP__ADMIN__USERNAME` | `admin` | Admin username |
| `MEDIARIP__ADMIN__PASSWORD_HASH` | _(empty)_ | Bcrypt hash of admin password |
| `MEDIARIP__PURGE__ENABLED` | `false` | Enable auto-purge of old downloads |
| `MEDIARIP__PURGE__MAX_AGE_HOURS` | `168` | Delete downloads older than this |
| `MEDIARIP__THEMES_DIR` | `/themes` | Custom themes directory |

### Session Modes

- **isolated** (default): Each browser session has its own private queue.
- **shared**: All sessions see all downloads. Good for household/team use.
- **open**: No session tracking at all.

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

For production with TLS:

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
# Edit .env with your domain and admin password hash
docker compose up -d
```

This uses Caddy as a reverse proxy with automatic Let's Encrypt TLS.

Generate an admin password hash:
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'YOUR_PASSWORD', bcrypt.gensalt()).decode())"
```

## Development

### Backend

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest pytest-asyncio pytest-anyio httpx ruff
.venv/bin/python -m pytest tests/ -v
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
| `/api/themes` | GET | List available custom themes |
| `/api/admin/*` | GET/POST | Admin endpoints (requires auth) |

## Architecture

- **Backend**: Python 3.12 + FastAPI + aiosqlite + yt-dlp
- **Frontend**: Vue 3 + TypeScript + Pinia + Vite
- **Transport**: Server-Sent Events for real-time progress
- **Database**: SQLite with WAL mode
- **Styling**: CSS custom properties (no Tailwind, no component library)

## License

MIT
