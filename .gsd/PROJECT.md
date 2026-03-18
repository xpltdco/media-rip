# media.rip()

## What This Is

A self-hostable, redistributable Docker container — a web-based yt-dlp frontend that anyone can run on their own infrastructure. Users paste a URL, pick quality, and download media without creating an account, sending data anywhere, or knowing what a terminal is. Ships with a cyberpunk default theme, session isolation, and ephemeral downloads. Fully configurable via mounted config file for personal, family, team, or public use.

Ground-up build. Not a MeTube fork. Treats theming, session behavior, purge policy, and operator experience as first-class concerns.

## Core Value

A user can paste any yt-dlp-supported URL, see exactly what they're about to download, and get it — without creating an account, without sending data anywhere, and without knowing what a terminal is.

## Current State

Greenfield. Spec complete (see `/PROJECT.md`). Architecture, feature, stack, and pitfall research complete (see `.planning/research/`). No code written yet.

## Architecture / Key Patterns

- **Backend:** Python 3.12 + FastAPI, yt-dlp as library (not subprocess), aiosqlite for SQLite, sse-starlette for SSE, APScheduler 3.x for cron, bcrypt for admin auth
- **Frontend:** Vue 3 + TypeScript + Pinia + Vite
- **Transport:** SSE (server-push only, no WebSocket)
- **Persistence:** SQLite with WAL mode
- **Critical pattern:** `ThreadPoolExecutor` + `loop.call_soon_threadsafe` bridges sync yt-dlp into async FastAPI — the load-bearing architectural seam
- **Session isolation:** Per-browser cookie-scoped queues (isolated/shared/open modes)
- **Config hierarchy:** Hardcoded defaults → config.yaml → env var overrides → SQLite admin writes
- **Distribution:** Single multi-stage Docker image, GHCR + Docker Hub, amd64 + arm64

## Capability Contract

See `.gsd/REQUIREMENTS.md` for the explicit capability contract, requirement status, and coverage mapping.

## Milestone Sequence

- [ ] M001: media.rip() v1.0 — Full-featured self-hosted yt-dlp web frontend, Docker-distributed
