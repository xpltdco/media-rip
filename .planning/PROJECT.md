# media.rip()

## What This Is

A self-hostable, redistributable Docker container providing a web-based yt-dlp frontend for anyone who wants to rip internet content without touching the CLI. Designed for power users to share with trusted friends, for solo self-hosters who want a clean UI over yt-dlp, and for operators deploying shared or internal instances. Ships with a great default experience — cyberpunk theme, isolated sessions, ephemeral downloads, automatic purge — and is fully configurable via a mounted `config.yaml` so operators can reshape it for any use case.

Not a MeTube fork. A ground-up rebuild that treats theming, session behavior, purge policy, privacy, and health monitoring as first-class concerns.

## Core Value

A user can paste any yt-dlp-supported URL, see exactly what they're about to download, and get it — without creating an account, without sending data anywhere, and without knowing what a terminal is.

## Current Milestone: v1.0 Initial Release

**Goal:** Ship a fully functional, self-hostable yt-dlp web frontend — downloads, session management, theming, admin auth, and Docker distribution.

**Target features:**
- Core download engine (URL detection, format selection, real-time progress)
- Session system (cookie-based, isolated by default, export/import)
- Theming (cyberpunk default, dark, light; drop-in custom themes)
- Admin UI with basic login (Sonarr-style) and live config management
- Health, observability, privacy controls
- Docker distribution with CI/CD pipeline
- Post-ship polish phase (defaults tuning)

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Downloads**
- [ ] User can submit any yt-dlp-supported URL (video, audio, playlist)
- [ ] URL auto-detection triggers format scraping as soon as a valid URL is detected (no submit required)
- [ ] User sees full list of available formats/quality with clear file type and size info before downloading
- [ ] User can start all items in a queue or start individual items selectively
- [ ] Playlist support: collapsible parent row + child rows, bulk or individual start
- [ ] Download progress shown in real-time via SSE
- [ ] Completed downloads clearly indicated in UI
- [ ] User can filter and sort the download queue

**Session & Identity**
- [ ] Session cookie (`mrip_session`) auto-created on first visit, 24hr TTL
- [ ] Session persists across browser refresh and reconnects (SSE replays state on reconnect)
- [ ] User can delete their own session and all associated data (downloads, logs, cookies)
- [ ] User can export their session as a portable file (download history, queue state, preferences)
- [ ] User can import a previously exported session to restore their download history — enables basic identity continuity on persistent instances
- [ ] Cookie auth: user can upload a `cookies.txt` file (Netscape format) per-session for authenticated downloads (private/paywalled content)

**Link Sharing**
- [ ] User can copy the original source URL to clipboard (share-to-rip)
- [ ] Completed downloads are served at a shareable URL so a friend can download the file directly

**Theming & UI**
- [ ] Three built-in themes: cyberpunk (default), dark, light
- [ ] Theme selection persisted in localStorage
- [ ] Operators can drop theme directories into `/themes` volume — appears in picker without recompile
- [ ] Theme file format is flat, well-commented, and human-readable — a single file per theme with clear variable names and inline docs so anyone (or an AI) can understand and modify it without prior CSS/frontend knowledge
- [ ] Built-in themes serve as learning examples: heavily commented, covering every UI region, showing what each token controls
- [ ] Responsive layout: desktop (sidebar + table) and mobile (bottom tabs + card list)
- [ ] All touch targets minimum 44px on mobile

**Admin & Configuration**
- [ ] Admin login: username/password protected admin UI (like qBittorrent/Sonarr/Radarr) — no token-in-header, no raw config required; default credentials set at first boot with forced change prompt
- [ ] Admin panel is the primary config surface — session mode, purge policy, filename templates, branding all configurable via UI without touching files
- [ ] `config.yaml` mount still supported as override layer for operators who prefer infra-as-code / GitOps workflows
- [ ] Operator can configure session mode: `isolated` (default) / `shared` / `open`
- [ ] Operator can configure purge: `scheduled` / `manual` / `never`, with TTL for files and logs independently
- [ ] Operator can configure output filename templates globally (source-aware: YouTube, SoundCloud, generic)
- [ ] Admin panel: active sessions, storage usage, manual purge trigger, unsupported URL log download, live config editor
- [ ] Branding overridable: name, tagline, logo

**Health & Observability**
- [ ] `GET /api/health` returns service status, yt-dlp version, uptime, and key health flags (disk space available, queue depth)
- [ ] Clear structured logging routed internally (no stdout noise)
- [ ] Health flags surfaced in admin panel

**Privacy & Data Control**
- [ ] Zero automatic outbound telemetry — no analytics, CDN calls, update checks, or beacons
- [ ] All PII (IPs, session IDs, cookie files) included in purge scope when operator enables it
- [ ] Unsupported URL reporting: user-triggered only, logs domain by default (`report_full_url: false` = domain only), zero automatic submission
- [ ] Config option: `reporting.github_issues` opens pre-filled issue (disabled by default)

**Unsupported URL Reporting**
- [ ] Failed jobs show error + "Report unsupported site" button
- [ ] Report appends structured entry to `/data/unsupported_urls.log`
- [ ] Admin can download the report log via API

**Distribution & CI/CD**
- [ ] Single multi-stage Docker image: `ghcr.io/xpltd/media-rip` + `docker.io/xpltd/media-rip`
- [ ] Multi-platform: `linux/amd64` + `linux/arm64`
- [ ] CI on PR: lint (ruff, eslint), type-check (vue-tsc), tests (pytest, vitest), Docker build smoke test
- [ ] CD on tag `v*.*.*`: build, push to both registries, generate GitHub Release with changelog
- [ ] `config.yaml` reference documented in README — all fields, defaults, env var overrides explained

### Out of Scope

- External API / arr-stack integration (Radarr/Sonarr-style programmatic use) — documented as future milestone, architecture should not block it
- OAuth / user accounts — end-user sessions are anonymous by design; admin auth is basic username/password only, no SSO
- Real-time chat or social features — not core
- Video posts or re-hosting — media.rip downloads, does not transcode or re-serve content at scale
- Mobile native app — web-first

## Context

- Inspired by frustration with MeTube's poor customizability — layout, theming, and defaults are hard to change
- Target operators: power users sharing with trusted friends, solo self-hosters, internal team tools
- Privacy-first: trust is the core proposition — users should feel confident their activity isn't being tracked or leaked
- yt-dlp used as library (`import yt_dlp`), not subprocess — gives fine-grained progress hooks and avoids shell injection
- Session cookie approach chosen so users can reconnect after internet drop and resume where they left off
- Cookie auth (cookies.txt upload) enables downloading paywalled/private content without embedding credentials in the app
- A post-ship polish phase is planned: after the core product is working, do a dedicated pass to tune defaults, tighten the out-of-box experience, and make the cyberpunk theme sing

## Constraints

- **Tech Stack**: Python 3.12 + FastAPI (backend), Vue 3 + TypeScript + Vite + Pinia (frontend), SQLite via aiosqlite, SSE for real-time, APScheduler for cron tasks
- **Distribution**: Single Docker image, no external runtime dependencies beyond ffmpeg
- **Zero-config**: Must work out of the box with no mounted config — all settings have safe defaults
- **Compatibility**: Must support at minimum all sites MeTube supports at launch

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| yt-dlp as library, not subprocess | Fine-grained progress hooks, structured error handling, no shell injection surface | — Pending |
| SSE over WebSockets | Simpler, HTTP-native, auto-reconnect built into browser EventSource | — Pending |
| SQLite for job state | Single-file, zero-dependency, sufficient for concurrency needs | — Pending |
| Session isolation as default | Privacy-first default; operators opt into shared/open | — Pending |
| cookies.txt upload (Netscape format) | yt-dlp native support, well-documented browser extension workflow for users | — Pending |
| External API deferred to v2 | Keeps v1 scope manageable; current API surface designed cleanly so future consumers aren't blocked | — Pending |
| Admin UI auth (basic login) over ADMIN_TOKEN | Lowers barrier for non-technical operators; config-via-UI means no docker restarts to change settings; `config.yaml` still supported as override layer | — Pending |
| Session export/import | Enables identity continuity on persistent instances without a real account system; stays anonymous-first by default | — Pending |
| Theme files human-readable + heavily commented | Lowers floor for customization to near zero — anyone with a text editor or AI assistant can retheme without frontend knowledge | — Pending |

---
*Last updated: 2026-03-17 — added session export/import, theme file accessibility goals, admin basic auth login, polish phase*
