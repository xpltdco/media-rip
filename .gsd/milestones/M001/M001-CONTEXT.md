# M001: media.rip() v1.0 — Context

**Gathered:** 2026-03-17
**Status:** Ready for planning

## Project Description

media.rip() is a self-hostable web-based yt-dlp frontend distributed as a Docker container. Users paste any yt-dlp-supported URL, select format/quality from live extraction, and download media — no account, no telemetry, no terminal. Ground-up build targeting the gaps every competitor (MeTube, yt-dlp-web-ui, ytptube) leaves open: session isolation, real theming, mobile UX, and operator-first configuration.

## Why This Milestone

This is the only milestone. M001 delivers the complete v1.0 product — from first line of code through Docker distribution. The product cannot ship partially; a download tool without real-time progress, or with progress but no session isolation, or with isolation but no admin panel, would be an incomplete product that fails to differentiate from existing tools.

## User-Visible Outcome

### When this milestone is complete, the user can:

- Run `docker compose up` and access a fully functional download UI at :8080 with cyberpunk theme, zero configuration
- Paste any yt-dlp-supported URL, pick format/quality from live extraction, and download to /downloads
- See real-time progress (percent, speed, ETA) via SSE, surviving page refreshes
- Use isolated session mode (default) so two browsers see only their own downloads
- Upload cookies.txt for paywalled content, scoped to their session
- Switch between cyberpunk, dark, and light themes — or drop a custom theme into /themes
- Access admin panel via username/password login to manage sessions, storage, purge, and config
- Deploy securely using the provided reverse-proxy + TLS compose example

### Entry point / environment

- Entry point: `docker compose up` → http://localhost:8080 (dev), https://media.example.com (prod behind reverse proxy)
- Environment: Docker container, browser-accessed
- Live dependencies involved: yt-dlp (bundled library), ffmpeg (bundled binary), SQLite (embedded)

## Completion Class

- Contract complete means: all API endpoints respond correctly, yt-dlp downloads succeed, SSE streams deliver events, session isolation works, admin auth rejects unauthorized requests, purge deletes correct files, themes apply correctly
- Integration complete means: frontend ↔ backend SSE flow works end-to-end, yt-dlp progress hooks bridge to browser progress bars, admin config changes take effect live, theme volume mount → picker → apply chain works
- Operational complete means: Docker image builds for both architectures, CI runs on PR, CD publishes on tag, health endpoint responds, startup TLS warning fires when appropriate

## Final Integrated Acceptance

To call this milestone complete, we must prove:

- Paste a YouTube URL in the browser → pick quality → see real-time progress → file appears in /downloads (the full primary loop)
- Open two different browsers → each sees only its own downloads (session isolation)
- Admin login → change a config value → effect visible without container restart
- Drop a custom theme folder into /themes volume → restart → appears in theme picker → applies correctly
- `docker compose up` with zero config → everything works at :8080 with cyberpunk theme and isolated mode
- Tag v0.1.0 → GitHub Actions builds and pushes amd64 + arm64 images to both registries

## Risks and Unknowns

- **Sync-to-async bridge correctness** — yt-dlp is synchronous, FastAPI is async. ThreadPoolExecutor + `call_soon_threadsafe` is the known-correct pattern, but getting the event loop capture and progress hook wiring wrong produces silent event loss or blocked loops. Must be proven in S01
- **SSE disconnect handling** — CancelledError swallowing creates zombie connections. sse-starlette handles this but the generator must use try/finally correctly. Must be proven in S02
- **SQLite write contention** — WAL mode + busy_timeout handles this for the expected load, but must be enabled at DB init before any schema work. Addressed in S01
- **CSS variable contract is a one-way door** — Token names cannot change after operators write custom themes. Must be designed deliberately in S05, not evolved by accident
- **cookies.txt security** — CVE-2023-35934 requires pinning yt-dlp >= 2023-07-06. Cookie files are sensitive — never log, store per-session, delete on purge
- **Admin auth over cleartext** — If operator doesn't use TLS, admin credentials sent in cleartext. Mitigated by startup warning + secure deployment docs, but can't be prevented from the app side

## Existing Codebase / Prior Art

- `PROJECT.md` — comprehensive product spec with data models, API surface, SSE schema, config schema, Dockerfile sketch, CI/CD outline
- `.planning/research/ARCHITECTURE.md` — system diagram, component boundaries, data flow paths, anti-patterns, Docker layering strategy
- `.planning/research/FEATURES.md` — feature landscape, competitor analysis, dependency graph, edge cases, MVP definition
- `.planning/research/STACK.md` — pinned versions for all dependencies, integration patterns, known pitfalls per library
- `.planning/research/PITFALLS.md` — critical pitfalls with prevention strategies and warning signs
- `.planning/research/SUMMARY.md` — executive summary of all research with confidence assessments

> See `.gsd/DECISIONS.md` for all architectural and pattern decisions — it is an append-only register; read it during planning, append to it during execution.

## Relevant Requirements

- R001-R006 — Core download loop (URL → format → progress → queue → playlist)
- R007 — Session isolation (the primary differentiator)
- R003, R004 — SSE transport + replay (the technical enabler for isolation)
- R014 — Admin panel with secure auth (trust proposition)
- R010-R012 — Theme system (visual identity + operator customization)
- R021-R022 — Docker distribution + CI/CD (the delivery mechanism)
- R020 — Zero telemetry (hard constraint on all slices)

## Scope

### In Scope

- Complete backend: FastAPI app with all API endpoints, yt-dlp integration, SSE, sessions, admin, purge, config, health
- Complete frontend: Vue 3 SPA with download queue, format picker, progress, playlist UI, mobile layout, admin panel, theme picker
- Three built-in themes + drop-in custom theme system
- Cookie auth (cookies.txt per-session)
- Session export/import
- Unsupported URL reporting
- Docker packaging + CI/CD
- Secure deployment documentation

### Out of Scope / Non-Goals

- OAuth/SSO, user accounts, WebSocket, embedded player, auto-update yt-dlp, subscription monitoring, FlareSolverr (see R030-R036)
- TLS termination inside the container (reverse proxy responsibility)
- Telegram/Discord bot (v2+ extension point)
- Arr-stack API integration (v2+)

## Technical Constraints

- Python 3.12 (not 3.13 — passlib breakage)
- yt-dlp as library, not subprocess (structured progress hooks, no shell injection)
- YoutubeDL instance created fresh per job — never shared across threads
- ThreadPoolExecutor only (not ProcessPoolExecutor — YoutubeDL not picklable)
- SQLite with WAL mode, synchronous=NORMAL, busy_timeout=5000 — enabled before any schema work
- SSE via sse-starlette (not FastAPI native — better disconnect handling)
- APScheduler 3.x (not 4.x alpha)
- bcrypt 5.0.0 direct (not passlib — unmaintained, Python 3.13 breakage)
- All fonts/assets bundled — zero external CDN requests

## Integration Points

- **yt-dlp** — library import, ThreadPoolExecutor workers, progress hooks via call_soon_threadsafe
- **ffmpeg** — installed in Docker image, found by yt-dlp via PATH for muxing
- **sse-starlette** — EventSourceResponse wrapping async generators
- **APScheduler AsyncIOScheduler** — started in FastAPI lifespan, shares event loop
- **aiosqlite** — connection pool via FastAPI Depends, WAL mode
- **GitHub Actions** — CI (lint/test on PR) + CD (build/push on tag)
- **GHCR + Docker Hub** — image registry targets

## Open Questions

- **Reverse proxy for deployment example** — Caddy vs Traefik. Leaning Caddy for simplicity (one-liner TLS). Decide during S06 planning
- **First-boot admin UX** — How pushy should the forced credential change prompt be? Decide during S04 planning
- **HTTP/2 for SSE connection limit** — SSE has 6-connection-per-domain limit on HTTP/1.1. Caddy handles HTTP/2 automatically if chosen as reverse proxy. Confirm approach during S06
