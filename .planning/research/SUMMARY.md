# Project Research Summary

**Project:** media.rip() — self-hosted yt-dlp web frontend
**Domain:** Self-hosted media downloader / yt-dlp web UI
**Researched:** 2026-03-17
**Confidence:** HIGH

## Executive Summary

media.rip() is a self-hosted web UI for yt-dlp: users paste URLs, select quality, and the tool downloads media to a local volume. The competitive landscape (MeTube, yt-dlp-web-ui, ytptube) reveals a consistent set of gaps — no competitor does mobile well, none offer per-session isolation, and theming is either absent or env-var-only. The recommended approach is a Python 3.12 / FastAPI backend serving a Vue 3 SPA, with yt-dlp used as a library (not subprocess) inside a `ThreadPoolExecutor`, and real-time progress delivered over SSE rather than WebSockets. All versions are verified stable as of March 2026. The stack is well-documented with established integration patterns.

The primary architectural challenge is the sync-to-async bridge: yt-dlp is synchronous and blocking, FastAPI is async. The correct pattern — `ThreadPoolExecutor` + `loop.call_soon_threadsafe` to route progress hook events into per-session `asyncio.Queue`s — is well-understood and must be built correctly in Phase 1. Getting this wrong produces either a blocked event loop or silent event loss, and retrofitting it later is expensive. Every subsequent feature (SSE progress, session isolation, cookies.txt auth) depends on this bridge being correct.

The top risks are (1) shared `YoutubeDL` instances corrupting concurrent downloads, (2) SSE `CancelledError` swallowing creating zombie connections, (3) cookies.txt leakage via CVE-2023-35934 if cookie files are not per-session and purge-scoped, and (4) SQLite write contention without WAL mode. All four are preventable at setup time with known mitigations. The session isolation differentiator (the feature MeTube explicitly closed as "won't fix") is also the feature with the most architectural surface area — it must be designed in from Phase 1, not bolted on.

## Key Findings

### Recommended Stack

The backend is Python 3.12 (avoiding 3.13's passlib breakage), FastAPI 0.135.1 (Pydantic v2, native SSE support), yt-dlp 2026.3.17 as a library, aiosqlite 0.22.1 for async SQLite, APScheduler 3.x (not 4.x alpha) for cron jobs, and sse-starlette 3.3.3 for production-reliable SSE disconnect handling. Password hashing uses bcrypt 5.0.0 directly — passlib is unmaintained and breaks on Python 3.13. Config is loaded from `config.yaml` and env vars via `pydantic-settings[yaml]` with `MEDIARIP__SECTION__KEY` override pattern. The frontend is Vue 3.5.30 (avoiding 3.6 beta's Vapor mode churn), Pinia 3 (Vuex is dead for Vue 3), Vite 8 with Rolldown, and Vitest 4. See STACK.md for pinned versions and integration patterns.

**Core technologies:**
- Python 3.12 + FastAPI 0.135.1: async HTTP API, SSE, HTTPBasic auth — Pydantic v2 required, async-first design matches download model
- yt-dlp 2026.3.17 (library mode): download engine — used as `import yt_dlp`, not subprocess; gives structured progress hooks and no shell-injection surface
- aiosqlite 0.22.1: job/session/config persistence — single-file DB, zero external deps, WAL mode required for concurrent downloads
- sse-starlette 3.3.3: SSE transport — more reliable disconnect handling than FastAPI's native SSE for long-lived connections
- Vue 3.5.30 + Pinia 3 + Vite 8: frontend SPA — Composition API, `<script setup>`, Rolldown builds
- ThreadPoolExecutor (not ProcessPoolExecutor): runs yt-dlp sync code — `YoutubeDL` is not picklable; threads only

### Expected Features

The full v1.0 feature set is ambitious but well-scoped. All features are mapped to dependencies in FEATURES.md. Session isolation is the primary differentiator and the feature that drives architectural decisions for the entire product.

**Must have (table stakes):**
- URL submission + format/quality selector (live extraction via yt-dlp, not presets)
- Real-time SSE progress with SSE init replay on reconnect
- Download queue: filter, sort, cancel, playlist parent/child collapsible
- Session isolation: isolated (default) / shared / open modes via cookie-based UUID
- cookies.txt upload per-session (Netscape format, purge-scoped)
- Mobile-responsive layout (bottom tabs, 44px touch targets, card list at <768px)
- Admin panel: username/password login, session list, storage, manual purge, config editor
- Purge system: scheduled/manual/never, independent file and log TTLs
- Three built-in themes: cyberpunk (default), dark, light
- Docker: single image, GHCR + Docker Hub, amd64 + arm64
- Health endpoint, session export/import, link sharing, unsupported URL reporting

**Should have (competitive):**
- Drop-in custom theme system via volume mount — the feature MeTube refuses to build
- Source-aware output templates (per-site defaults)
- Heavily commented built-in themes as drop-in documentation
- Zero automatic outbound telemetry (explicit design constraint, not an afterthought)

**Defer (v2+):**
- Subscription/channel monitoring — fundamentally different product scope (TubeArchivist territory)
- External arr-stack API integration — architecture does not block this; clean service layer is ready
- Telegram/Discord bot — documented as extension point; clean REST API makes it straightforward later

**Anti-features (do not build):**
- OAuth/SSO, WebSockets, user accounts/registration, embedded video player, automatic yt-dlp updates at runtime, FlareSolverr integration

### Architecture Approach

The system is a single Docker container: Vue 3 SPA (built to `/app/static/` at image build time, served by FastAPI `StaticFiles`) communicating with a FastAPI backend over REST + SSE. The backend has a clear layered structure — `core/` (long-lived singletons: SSEBroker, ConfigManager, DB pool), `middleware/` (session cookie), `routers/` (thin, delegate to services), `services/` (business logic: DownloadService, PurgeService, SessionExporter). The critical architectural decision is the async bridge: `DownloadService` holds a dedicated `ThreadPoolExecutor`; progress hooks use `loop.call_soon_threadsafe` to route events into per-session `asyncio.Queue`s in the `SSEBroker` singleton. See ARCHITECTURE.md for the full system diagram, data flow paths, and anti-patterns.

**Major components:**
1. `SSEBroker` (`app/core/sse_broker.py`) — per-session `asyncio.Queue` fan-out; singleton; bridges thread-pool workers to SSE clients
2. `DownloadService` (`app/services/download.py`) — long-lived, owns `ThreadPoolExecutor`, job registry, and yt-dlp invocation per job
3. `SessionMiddleware` (`app/middleware/session.py`) — auto-creates `mrip_session` UUID cookie; stores opaque ID only (not content)
4. `ConfigManager` (`app/core/config.py`) — three-layer config: hardcoded defaults → `config.yaml` → SQLite admin writes
5. `PurgeService` (`app/services/purge.py`) — file TTL, session TTL, log trim; called by APScheduler and admin trigger
6. Vue Pinia `sse` store (`frontend/src/stores/sse.ts`) — isolated SSE lifecycle; downloads store subscribes to it

**Key patterns:**
- Sync-to-async bridge: `loop.call_soon_threadsafe(queue.put_nowait, event)` — never call asyncio primitives directly from progress hook
- Per-session SSE queue fan-out: `SSEBroker` maps `session_id → List[Queue]`; one queue per tab, not per session
- SSE replay on reconnect: endpoint replays current DB state as synthetic events before entering live queue
- Config hierarchy: defaults → YAML (seeds DB on first boot) → SQLite (live admin writes win)
- Opaque session cookie: only UUID stored in cookie; all state lives in SQLite

### Critical Pitfalls

1. **Shared `YoutubeDL` instance across concurrent downloads** — create a fresh `YoutubeDL` per job inside the worker function; never share across threads. Warning signs: progress percentages swap between unrelated jobs; `TypeError` in progress hook. Address in Phase 1.

2. **Calling asyncio primitives directly from progress hook** — use `loop.call_soon_threadsafe(queue.put_nowait, event)` only; capture the event loop at FastAPI startup before executor threads start. Warning signs: SSE never receives progress; `RuntimeError: no running event loop`. Address in Phase 1.

3. **SSE `CancelledError` swallowing creating zombie connections** — never use `except Exception` in SSE generators; always use `try/finally` and explicitly `raise` in `except asyncio.CancelledError`. Warning signs: server memory grows slowly; zombie tasks visible in `asyncio.all_tasks()`. Address in Phase 2.

4. **SQLite write contention without WAL mode** — enable `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA busy_timeout=5000` at DB init before any other schema work. Warning signs: `SQLITE_BUSY` errors under 3+ concurrent downloads. Address in Phase 1.

5. **cookies.txt leakage (CVE-2023-35934)** — pin yt-dlp >= 2023-07-06; store cookies.txt per-session at `data/sessions/{session_id}/cookies.txt`; delete on job completion and session purge. Address in Phase 2 when cookie auth is implemented; pin version constraint in Phase 1.

6. **Purge deleting files for active downloads** — purge queries must filter `status IN ('completed', 'failed', 'cancelled')`; never rely on timestamp alone. Write a regression test as part of purge implementation. Address in Phase 3.

## Implications for Roadmap

The build order from ARCHITECTURE.md is the correct dependency-respecting sequence. The SSE transport is on the critical path — all meaningful frontend progress validation requires it. Session isolation must be designed in from Phase 1 (the middleware and DB schema), not added in Phase 3.

### Phase 1: Foundation

**Rationale:** Everything else depends on this layer. DB schema, WAL mode, session cookie middleware, SSEBroker, and ConfigManager have no inter-dependencies and must be correct before any business logic is added. The yt-dlp integration pattern (ThreadPoolExecutor + `call_soon_threadsafe`) must also be established here — it is the load-bearing architectural decision.
**Delivers:** Working yt-dlp download engine, DB schema with WAL mode, session cookie middleware, SSEBroker, ConfigManager, URL submission + format probe API
**Addresses:** URL submission, format/quality selector, real-time SSE progress (the core loop)
**Avoids:** Shared `YoutubeDL` instance pitfall, asyncio bridge pitfall, SQLite WAL pitfall — all three must be implemented correctly in this phase, not retrofitted

### Phase 2: SSE Transport + Session System

**Rationale:** SSE replay-on-reconnect and per-session isolation are the features that differentiate this product from MeTube. Both require the DB and SSEBroker from Phase 1. SSE `Last-Event-ID` replay and session cookie handling must be designed together — they share state assumptions. cookies.txt upload is also here because it depends on the session system.
**Delivers:** Full SSE streaming with disconnect handling, reconnect replay, and per-session queue isolation; session isolation modes (isolated/shared/open); cookies.txt upload per-session
**Uses:** sse-starlette 3.3.3, `asyncio.Queue` per-session fan-out, aiosqlite session table
**Implements:** SSEBroker fan-out pattern, SSE reconnect replay, SessionMiddleware, `SessionService`
**Avoids:** `CancelledError` swallowing, SSE reconnect storm, cookies.txt CVE-2023-35934

### Phase 3: Frontend Core

**Rationale:** Once the Phase 2 API shape is stable (SSE events typed, endpoints defined), the frontend can be built against it. Pinia SSE store and downloads store must be built together — their event contract is the interface. The download queue component drives the primary UX validation.
**Delivers:** Vue 3 SPA with download queue, format picker, progress bars, playlist parent/child rows, mobile-responsive layout (bottom tabs, 44px targets)
**Uses:** Vue 3.5.30, Pinia 3, Vite 8, `EventSource` API, `fetch` for REST
**Implements:** Pinia `sse` store (isolated lifecycle), `downloads` store (SSE-driven mutations), `DownloadQueue`, `FormatPicker`, `ProgressBar`, `PlaylistRow` components

### Phase 4: Admin + Auth

**Rationale:** Admin routes must be protected before the panel is built — shipping an unprotected admin panel even briefly is not acceptable. HTTPBasic + bcrypt is simple and sufficient; no JWT needed. Admin panel enables operator self-service for config, session management, and purge.
**Delivers:** Admin authentication (HTTPBasic + bcrypt, first-boot credential setup with forced change prompt), Admin panel UI (session list, storage view, manual purge trigger, live config editor, unsupported URL log download)
**Uses:** bcrypt 5.0.0 (direct, not passlib), `secrets.compare_digest` for constant-time comparison, `pydantic-settings[yaml]` config hierarchy
**Avoids:** Plaintext admin credentials, timing side channels in auth comparison

### Phase 5: Supporting Features

**Rationale:** These features enhance the product but do not block the primary user journey. Theme system requires a stable CSS variable contract (establish early in this phase before any components reference token names — changing token names later breaks all custom themes). Purge requires Admin auth from Phase 4. Session export depends on the session system from Phase 2.
**Delivers:** Three built-in themes (cyberpunk default, dark, light) + drop-in custom theme system via volume mount + theme picker UI; PurgeService with APScheduler cron (file TTL, session TTL, log rotation); session export/import; health endpoint; link sharing; unsupported URL reporting; source-aware output templates
**Avoids:** Purge-deletes-active-downloads pitfall (status guard required); theme token naming lock-in (establish CSS variable contract before component work)

### Phase 6: Distribution

**Rationale:** Docker packaging is a feature for this audience. Multi-stage build keeps image size under 400MB compressed. amd64 + arm64 is required — arm64 users (Raspberry Pi, Apple Silicon NAS devices) are a significant self-hosted audience. CI/CD ensures the image stays functional as yt-dlp extractors evolve.
**Delivers:** Multi-stage Dockerfile (Node builder → Python deps builder → slim runtime with ffmpeg), docker-compose.yml, GitHub Actions CI (lint, type-check, test, Docker smoke), GitHub Actions CD (tag → build + push GHCR + Docker Hub → release)
**Avoids:** Docker image bloat (multi-stage build + `.dockerignore` + slim base targets <400MB compressed), stale extractor risk (CI smoke-tests downloads from 2+ sites)

### Phase Ordering Rationale

- Phase 1 before Phase 2: SSEBroker and DB must exist before SSE endpoint or session middleware can be built
- Phase 2 before Phase 3: Frontend SSE store requires a typed event contract; that contract comes from the working SSE endpoint
- Phase 4 after Phase 2: Admin routes depend on session infrastructure for session listing; auth must precede the panel itself
- Phase 5 after Phase 4: Purge needs admin auth; theme system needs stable components to reference token names
- Phase 6 last: Docker packaging wraps a working application; CI/CD requires the test suite from earlier phases

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 2 (SSE + Session):** `Last-Event-ID` replay implementation details are non-trivial; session mode switching behavior (isolated → shared mid-deployment) needs explicit design before coding. Consider a dedicated research step on SSE event ID sequencing strategy.
- **Phase 5 (Theme system):** CSS variable contract naming is a one-way door — token names cannot change after operators write custom themes. Needs deliberate design (not just "we'll figure it out") before Phase 3 component work begins.
- **Phase 6 (Docker/CI):** Multi-platform QEMU builds on GitHub Actions standard runners can be slow; arm64 smoke testing strategy needs explicit plan.

Phases with standard patterns (skip research-phase):

- **Phase 1 (Foundation):** ThreadPoolExecutor + `call_soon_threadsafe` pattern is fully documented in STACK.md and ARCHITECTURE.md. WAL pragma sequence is known. DB schema is defined.
- **Phase 3 (Frontend Core):** Vue 3 + Pinia + Vite patterns are well-established. SSE via `EventSource` is a browser standard.
- **Phase 4 (Admin + Auth):** HTTPBasic + bcrypt pattern is fully specified in STACK.md. No novel patterns needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI and npm as of 2026-03-17. Critical alternatives (passlib, APScheduler 4.x, ProcessPoolExecutor, Vue 3.6 beta) explicitly ruled out with rationale. |
| Features | HIGH (core), MEDIUM (UX patterns) | Competitor feature gaps verified via GitHub issues (MeTube #591 closed won't-fix). UX patterns (mobile layout specifics, theme interaction details) are based on community consensus, not official specs. |
| Architecture | HIGH (integration patterns), MEDIUM (schema shape) | ThreadPoolExecutor + `call_soon_threadsafe` pattern verified via yt-dlp issue #9487. Schema shape is a design choice, not a discovered pattern — reviewed but not battle-tested. |
| Pitfalls | HIGH (critical), MEDIUM (performance traps) | Critical pitfalls verified via CVE advisories, official yt-dlp issues, and sse-starlette docs. Performance trap thresholds (e.g., "10,000+ job rows for index to matter") are community estimates. |

**Overall confidence:** HIGH

### Gaps to Address

- **Session mode switching mid-deployment:** Research documents the data model implications (isolated rows remain per-session when switching to shared) but does not specify a migration or operator-facing behavior contract. Design explicitly before Phase 2 implementation.
- **CSS variable token naming:** No canonical reference for a yt-dlp-themed CSS variable contract exists. The token set must be designed from scratch in Phase 5 (or early Phase 3 if components will reference them). Treat as a design deliverable, not an implementation detail.
- **HTTP/2 in single-container deployment:** SSE 6-connection-per-domain limit on HTTP/1.1 is documented as a risk. The mitigation (nginx/caddy in front, or `uvicorn --http h2`) is noted but not fully specified in the architecture. Confirm which approach is the recommended default for the Docker compose reference deployment.
- **yt-dlp extractor freshness strategy:** Pinning to `yt-dlp==2026.3.17` is correct for reproducibility, but extractors break as sites update. The update strategy ("publish new image on yt-dlp releases via CI") is noted but not implemented. Plan this in Phase 6 as a CI/CD workflow.

## Sources

### Primary (HIGH confidence)
- [PyPI: yt-dlp, FastAPI, uvicorn, aiosqlite, APScheduler, pydantic-settings, sse-starlette, bcrypt, httpx, pytest](https://pypi.org/) — all versions verified 2026-03-17
- [npm: vue, vue-router, pinia, vite, @vitejs/plugin-vue, vitest](https://www.npmjs.com/) — all versions verified 2026-03-17
- [yt-dlp Security Advisory GHSA-v8mc-9377-rwjj (CVE-2023-35934)](https://github.com/yt-dlp/yt-dlp/security/advisories/GHSA-v8mc-9377-rwjj) — cookie leak via redirect
- [yt-dlp issue #9487](https://github.com/yt-dlp/yt-dlp/issues/9487) — ThreadPoolExecutor vs ProcessPoolExecutor constraint
- [MeTube issue #591](https://github.com/alexta69/metube/issues/591) — session isolation closed as won't-fix
- [sse-starlette: Client Disconnection Detection](https://deepwiki.com/sysid/sse-starlette/3.5-client-disconnection-detection) — CancelledError must be re-raised
- [FastAPI docs: HTTP Basic Auth](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/) — HTTPBasic pattern
- [FastAPI docs: SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — EventSourceResponse

### Secondary (MEDIUM confidence)
- [MeTube GitHub](https://github.com/alexta69/metube) — competitor feature analysis
- [yt-dlp-web-ui GitHub](https://github.com/marcopiovanello/yt-dlp-web-ui) — competitor feature analysis
- [ytptube GitHub](https://github.com/arabcoders/ytptube) — competitor feature analysis
- [APScheduler 3.x docs](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — CronTrigger.from_crontab pattern
- [Browser connection limits for SSE](https://www.javascriptroom.com/blog/server-sent-events-and-browser-limits/) — 6-connection HTTP/1.1 limit
- [passlib deprecation discussion](https://github.com/fastapi/fastapi/discussions/11773) — Python 3.12/3.13 breakage confirmed

### Tertiary (LOW confidence)
- [Docker image size targets for arm64](https://github.com/wader/static-ffmpeg) — community estimate of <400MB compressed; not formally benchmarked for this stack

---
*Research completed: 2026-03-17*
*Ready for roadmap: yes*
