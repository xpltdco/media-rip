# media.rip()

## What This Is

A self-hostable, redistributable Docker container — a web-based yt-dlp frontend that anyone can run on their own infrastructure. Users paste a URL, pick quality, and download media without creating an account, sending data anywhere, or knowing what a terminal is. Ships with a cyberpunk default theme, session isolation, and ephemeral downloads. Fully configurable via mounted config file for personal, family, team, or public use.

Ground-up build. Not a MeTube fork. Treats theming, session behavior, purge policy, and operator experience as first-class concerns.

## Core Value

A user can paste any yt-dlp-supported URL, see exactly what they're about to download, and get it — without creating an account, without sending data anywhere, and without knowing what a terminal is.

## Current State

**v1.0.0 — Feature-complete and ship-ready.**

M001 (v1.0 full build — 6 slices) and M002 (UI/UX polish — 3 slices) are complete. 213 tests passing (179 backend, 34 frontend). Code pushed to GitHub. Docker image, CI/CD workflows, and deployment examples are in place.

All core capabilities implemented: URL submission + download, live format extraction, real-time SSE progress with reconnect replay, download queue management, playlist support with parent/child jobs, session isolation (isolated/shared/open), cookie auth upload, purge system (scheduled/manual/never), three built-in themes + custom theme system, admin panel with bcrypt auth, unsupported URL reporting, health endpoint, session export/import, link sharing, source-aware output templates, mobile-responsive layout, and zero outbound telemetry.

## Architecture / Key Patterns

- **Backend:** Python 3.12 + FastAPI, yt-dlp as library (not subprocess), aiosqlite for SQLite, sse-starlette for SSE, APScheduler 3.x for cron, bcrypt for admin auth
- **Frontend:** Vue 3 + TypeScript + Pinia + Vite
- **Transport:** SSE (server-push only, no WebSocket)
- **Persistence:** SQLite with WAL mode — `/data/mediarip.db` in Docker
- **Critical pattern:** `ThreadPoolExecutor` + `loop.call_soon_threadsafe` bridges sync yt-dlp into async FastAPI — the load-bearing architectural seam
- **Session isolation:** Per-browser cookie-scoped queues (isolated/shared/open modes)
- **Config hierarchy:** Hardcoded defaults → config.yaml → env var overrides (MEDIARIP__*) → SQLite admin writes
- **Distribution:** Single multi-stage Docker image (ghcr.io/xpltdco/media-rip), amd64 + arm64
- **Security:** CSP headers (self-only), no outbound requests, bcrypt admin auth, httpOnly session cookies

## Persistent Volumes (Docker)

| Mount | Purpose | Required |
|-------|---------|----------|
| `/downloads` | Downloaded media files | Yes |
| `/data` | SQLite database, session state, error logs | Yes |
| `/themes` | Custom theme CSS overrides | No |
| `/app/config.yaml` | YAML configuration file | No |

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone History

- ✅ M001: media.rip() v1.0 — Full-featured self-hosted yt-dlp web frontend (6 slices)
- ✅ M002: UI/UX Polish — Ship-Ready Frontend (3 slices)
