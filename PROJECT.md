# media.rip()

> **pull anything.**

A self-hostable, redistributable Docker container — a web-based yt-dlp frontend that anyone can run on their own infrastructure. Ships with a great default experience (cyberpunk theme, session isolation, ephemeral downloads) but is fully configurable via a mounted config file so operators can reshape it for their use case: personal/family sharing, internal team tools, public open instances, or anything in between.

Not a MeTube fork. A ground-up rebuild that treats theming, session behavior, purge policy, and reporting as first-class concerns rather than bolted-on hacks.

---

## Distribution

- **GHCR:** `ghcr.io/xpltd/media-rip`
- **Docker Hub:** `xpltd/media-rip`
- **License:** MIT

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Frontend | Vue 3 + TypeScript + Vite + Pinia |
| Real-time | SSE (Server-Sent Events) |
| State | SQLite via aiosqlite |
| Build | Single multi-stage Docker image |
| Scheduler | APScheduler |
| Downloader | yt-dlp (library, not subprocess) |

---

## Project Structure

```
media-rip/
├── .github/
│   ├── workflows/
│   │   ├── publish.yml              # Build + push GHCR + Docker Hub on tag
│   │   └── ci.yml                   # Lint + test on PR
│   └── ISSUE_TEMPLATE/
│       └── unsupported-site.md
│
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory, lifespan, middleware, mounts
│   │   ├── config.py                # Config loader: config.yaml + env var overrides
│   │   ├── dependencies.py          # FastAPI Depends() — session resolution, admin auth
│   │   │
│   │   ├── api/
│   │   │   ├── router.py
│   │   │   ├── downloads.py         # POST/GET/DELETE /api/downloads
│   │   │   ├── events.py            # GET /api/events (SSE stream)
│   │   │   ├── formats.py           # GET /api/formats?url=
│   │   │   ├── system.py            # GET /api/health, GET /api/config/public
│   │   │   └── admin.py             # /api/admin/*
│   │   │
│   │   ├── core/
│   │   │   ├── session_manager.py
│   │   │   ├── job_manager.py       # SQLite CRUD, mode-aware queries
│   │   │   ├── sse_bus.py           # Per-session asyncio.Queue dispatcher
│   │   │   ├── downloader.py        # yt-dlp integration, thread pool, hooks
│   │   │   ├── scheduler.py         # APScheduler: cron purge, session expiry
│   │   │   ├── purge.py
│   │   │   ├── output_template.py   # Source-aware template resolution
│   │   │   └── reporter.py          # Unsupported URL log writer
│   │   │
│   │   └── models/
│   │       ├── job.py
│   │       ├── session.py
│   │       └── events.py
│   │
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── DesktopLayout.vue
│   │   │   │   └── MobileLayout.vue
│   │   │   ├── UrlInput.vue
│   │   │   ├── DownloadTable.vue
│   │   │   ├── DownloadList.vue
│   │   │   ├── DownloadRow.vue
│   │   │   ├── PlaylistGroup.vue
│   │   │   ├── ReportButton.vue
│   │   │   ├── SettingsSheet.vue
│   │   │   ├── ThemePicker.vue
│   │   │   └── AdminPanel.vue
│   │   ├── stores/
│   │   │   ├── downloads.ts
│   │   │   ├── config.ts
│   │   │   └── ui.ts
│   │   ├── api/
│   │   │   └── client.ts
│   │   └── themes/
│   │       ├── base.css
│   │       ├── cyberpunk.css
│   │       ├── dark.css
│   │       └── light.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── themes/                          # Volume mount point for external themes
│   └── .gitkeep
├── config/                          # Volume mount point for config.yaml
│   └── .gitkeep
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── docker-compose.example.yml
├── LICENSE
└── README.md
```

---

## Feature Requirements

### Core Downloads
- Submit any yt-dlp-supported URL (video, audio, playlist)
- Format/quality selector populated by live yt-dlp info extraction (`GET /api/formats?url=`)
- Per-download output template override
- Source-aware default templates (YouTube, SoundCloud, generic fallback)
- Concurrent same-URL support — jobs keyed by UUID4, never URL
- Playlist support: parent job + child job linking, collapsible UI row

### Session System (configurable, server-wide)

| Mode | Behavior |
|---|---|
| `isolated` (default) | Each browser session sees only its own downloads; httpOnly UUID4 cookie |
| `shared` | All sessions see all downloads — one unified queue |
| `open` | No session tracking; anonymous, stateless |

- `isolated` uses `mrip_session` httpOnly cookie
- On SSE connect, server replays current session's jobs as `init` event (page refresh safe)

### Real-Time Progress
- SSE stream per session at `GET /api/events`
- Events: `init`, `job_update`, `job_removed`, `error`, `purge_complete`
- `EventSource` auto-reconnects in browser
- Downloads via HTTP POST; no WebSocket

### Unified Job Queue
- Single SQLite table
- Status lifecycle: `queued → extracting → downloading → completed → failed → expired`
- Playlists: collapsible parent row + child video rows

### File & Log Purge

| Mode | Behavior |
|---|---|
| `scheduled` (default) | Cron expression, e.g. `"0 3 * * *"` |
| `manual` | Only on `POST /api/admin/purge` |
| `never` | No auto-deletion |

- Purge scope: `files`, `logs`, `both`, or `none`
- File TTL and log TTL are independent values
- Purge activity written to audit log

### Theme System

Built on CSS variables. Themes are directories — drop a folder into `/themes` volume, it appears in the picker. No recompile needed for user themes.

**Theme pack format:**
```
/themes/my-theme/
  theme.css        # CSS variable overrides
  metadata.json    # { name, author, version, description }
  preview.png      # optional thumbnail
  assets/          # optional fonts, images
```

**Built-in themes (baked into image):**
- `cyberpunk` — default: #00a8ff/#ff6b2b, JetBrains Mono, scanlines, grid overlay
- `dark` — clean dark, no effects
- `light` — light mode

**CSS variable contract (`base.css`):**
```css
--color-bg, --color-surface, --color-surface-raised
--color-accent-primary, --color-accent-secondary
--color-text, --color-text-muted, --color-border
--color-success, --color-warning, --color-error
--font-ui, --font-mono
--radius-sm, --radius-md, --radius-lg
--effect-overlay  /* optional scanline/grid layer */
```

Theme selection persisted in `localStorage`. Hot-loaded from `/themes` at startup.

### Mobile + Desktop UI

**Breakpoints:** `< 768px` = mobile, `≥ 768px` = desktop

**Desktop:**
- Top header bar: branding, theme picker, admin link
- Left sidebar (collapsible): submit form + options
- Main area: full download table

**Mobile:**
- Bottom tab bar: Submit / Queue / Settings
- URL input full-width at top
- Card list for queue (swipe-to-cancel)
- "More options" bottom sheet for format/quality/template
- All tap targets minimum 44px

### Unsupported URL Reporting

When yt-dlp fails with extraction error:
1. Job row shows `failed` badge + error message
2. "Report unsupported site" button appears
3. Click → appends to `/data/unsupported_urls.log`:
   ```
   2026-03-17T03:14:00Z  UNSUPPORTED  domain=example.com  error="Unsupported URL"  yt-dlp=2025.x.x
   ```
4. Config `report_full_url: false` logs domain only (privacy mode)
5. Config `reporting.github_issues: true` opens pre-filled GitHub issue (opt-in, disabled by default)
6. Admin downloads log via `GET /api/admin/reports/unsupported`
7. Zero automatic outbound telemetry — user sees exactly what will be submitted

### Admin Panel

Protected by optional `ADMIN_TOKEN` (bearer header). If unset, admin routes are open.

- `GET /api/admin/sessions` — active sessions + job counts
- `GET /api/admin/storage` — disk usage of downloads dir
- `POST /api/admin/purge` — trigger manual purge
- `GET /api/admin/reports/unsupported` — download unsupported URL log
- `GET /api/admin/config` — sanitized effective config (no secrets)

Frontend `/admin` route: hidden from nav unless token is configured or user supplies it.

---

## Data Models

### Job
```python
@dataclass
class Job:
    id: str                  # UUID4
    session_id: str | None
    url: str
    status: JobStatus        # queued|extracting|downloading|completed|failed|expired
    title: str | None
    thumbnail: str | None
    uploader: str | None
    duration: int | None
    format_id: str | None
    quality: str | None
    output_template: str | None
    filename: str | None
    filesize: int | None
    downloaded_bytes: int
    speed: float | None
    eta: int | None
    percent: float
    error: str | None
    reported: bool
    playlist_id: str | None
    is_playlist: bool
    child_count: int | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None
```

### Session
```python
@dataclass
class Session:
    id: str                  # UUID4, cookie "mrip_session"
    created_at: datetime
    last_seen: datetime
    job_count: int
```

---

## API Surface

```
# Public
GET  /api/health                    → {status, version, yt_dlp_version, uptime}
GET  /api/config/public             → sanitized config (session mode, themes, branding)
GET  /api/downloads                 → jobs for current session
POST /api/downloads                 → submit download, returns Job
DELETE /api/downloads/{id}          → cancel/remove
GET  /api/formats?url={url}         → available formats
GET  /api/events                    → SSE stream

# Admin (bearer ADMIN_TOKEN if configured)
GET  /api/admin/sessions
GET  /api/admin/storage
POST /api/admin/purge
GET  /api/admin/reports/unsupported
GET  /api/admin/config
```

---

## SSE Event Schema

```json
// init — replayed on connect/reconnect
{"jobs": [...], "session_mode": "isolated"}

// job_update
{<full Job object>}

// job_removed
{"id": "uuid"}

// error
{"id": "uuid", "message": "...", "can_report": true}

// purge_complete
{"deleted_files": 12, "freed_bytes": 4096000}
```

---

## Configuration

Primary: `config.yaml` mounted at `/config/config.yaml`. All fields optional; zero-config works out of the box.

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  cors_origins: ["*"]

branding:
  name: "media.rip()"
  tagline: "pull anything."
  logo_path: null

session:
  mode: "isolated"             # isolated | shared | open
  ttl_hours: 24

downloads:
  output_dir: "/downloads"
  max_concurrent: 3
  default_quality: "bestvideo+bestaudio/best"
  default_format: "mp4"
  source_templates:
    "youtube.com": "%(uploader)s/%(title)s.%(ext)s"
    "youtu.be":    "%(uploader)s/%(title)s.%(ext)s"
    "soundcloud.com": "%(uploader)s/%(title)s.%(ext)s"
    "*":           "%(title)s.%(ext)s"
  proxy: null

purge:
  mode: "scheduled"            # scheduled | manual | never
  schedule: "0 3 * * *"
  files_ttl_hours: 24
  logs_ttl_hours: 168
  scope: "both"                # files | logs | both | none

ui:
  default_theme: "cyberpunk"
  allow_theme_switching: true
  themes_dir: "/themes"

reporting:
  unsupported_urls: true
  report_full_url: true
  log_path: "/data/unsupported_urls.log"
  github_issues: false

admin:
  token: null
  enabled: true
```

**Env var override pattern:** `MEDIARIP__SECTION__KEY`
- `MEDIARIP__SESSION__MODE=shared`
- `MEDIARIP__ADMIN__TOKEN=mysecret`
- `MEDIARIP__PURGE__MODE=never`

---

## Dockerfile (multi-stage)

```dockerfile
# Stage 1: Frontend build
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /app/dist ./static
VOLUME ["/downloads", "/data", "/config", "/themes"]
EXPOSE 8080
ENV MEDIARIP__DOWNLOADS__OUTPUT_DIR=/downloads \
    MEDIARIP__SERVER__DATA_DIR=/data
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## yt-dlp Integration Notes

- `import yt_dlp` — library, not subprocess
- `ThreadPoolExecutor(max_workers=config.downloads.max_concurrent)`
- `asyncio.run_in_executor` bridges sync yt-dlp into async FastAPI
- Custom `YDLLogger` suppresses stdout, routes to structured logs
- Progress hook fires `job_update` SSE events on `downloading` and `finished`
- Extraction failure → `reporter.log_unsupported()` if enabled → job `failed` with `can_report=True`

### Playlist flow
1. POST playlist URL → parent job `is_playlist=True`, status=`extracting`
2. yt-dlp resolves entries in executor → child jobs created with `playlist_id=parent.id`
3. Parent = `downloading` when first child starts
4. Parent = `completed` when all children reach `completed` or `failed`

---

## CI/CD

### `publish.yml` — on `v*.*.*` tags
- Multi-platform build: `linux/amd64`, `linux/arm64`
- Push to `ghcr.io/xpltd/media-rip:{version}` + `:latest`
- Push to `docker.io/xpltd/media-rip:{version}` + `:latest`
- Generate GitHub Release with changelog

### `ci.yml` — on PRs to `main`
- Backend: `ruff` lint + `pytest`
- Frontend: `eslint` + `vue-tsc` + `vitest`
- Docker build smoke test

---

## Implementation Phases

| Phase | Scope |
|---|---|
| 1 | Skeleton & Config System |
| 2 | Backend: Models, Sessions, SSE, Job Store |
| 3 | Backend: yt-dlp, Purge, Reporting, Admin |
| 4 | Frontend: Core UI + SSE Client |
| 5 | Frontend: Theming + Settings + Admin Panel |
| 6 | CI/CD & Packaging |

---

## Verification Checklist

1. **Zero-config start:** `docker compose up` → loads at `:8080`, cyberpunk theme, isolated mode
2. **Config override:** mount `config.yaml` with `session.mode: shared` → unified queue
3. **Env var override:** `MEDIARIP__PURGE__MODE=never` → scheduler does not run
4. **Download flow:** YouTube URL → extracting → progress → completed → file in `/downloads`
5. **Session isolation:** two browser profiles → each sees only own jobs
6. **Concurrent same-URL:** same URL twice at different qualities → two independent rows
7. **Playlist:** playlist URL → collapsible parent + child rows
8. **Mobile:** 375px viewport → bottom tabs, card list, touch targets ≥ 44px
9. **Theming:** drop theme into `/themes` → appears in picker, applies correctly
10. **Purge (scheduled):** 1-minute cron + 0h TTL → files deleted
11. **Purge (manual):** `POST /api/admin/purge` → immediate purge
12. **Unsupported report:** bad URL → failed → click Report → entry in log
13. **Admin auth:** `ADMIN_TOKEN` set → `/admin` requires token
14. **Multi-platform image:** tag `v0.1.0` → both registries, both arches
