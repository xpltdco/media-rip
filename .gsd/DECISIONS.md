# Decisions Register

<!-- Append-only. Never edit or remove existing rows.
     To reverse a decision, add a new row that supersedes it.
     Read this file at the start of any planning or research phase. -->

| # | When | Scope | Decision | Choice | Rationale | Revisable? |
|---|------|-------|----------|--------|-----------|------------|
| D001 | M001 | arch | Backend framework | Python 3.12 + FastAPI | Async-first, Pydantic v2, SSE support, well-documented yt-dlp integration patterns | No |
| D002 | M001 | arch | Frontend framework | Vue 3 + TypeScript + Pinia + Vite | Composition API, `<script setup>`, Pinia 3 (Vuex dead for Vue 3), Vite 8 with Rolldown | No |
| D003 | M001 | arch | Real-time transport | SSE via sse-starlette (not WebSocket) | Server-push only needed; SSE is simpler, HTTP-native, auto-reconnecting. sse-starlette has better disconnect handling than FastAPI native SSE | No |
| D004 | M001 | arch | Database | SQLite via aiosqlite with WAL mode | Single-file, zero external deps, sufficient for single-instance self-hosted tool. WAL required for concurrent download writes | No |
| D005 | M001 | arch | yt-dlp integration | Library import, not subprocess | Structured progress hooks, no shell injection surface, typed error info | No |
| D006 | M001 | arch | Sync-to-async bridge | ThreadPoolExecutor + loop.call_soon_threadsafe | YoutubeDL not picklable (rules out ProcessPoolExecutor). call_soon_threadsafe is the only safe bridge from sync threads to asyncio Queue | No |
| D007 | M001 | arch | Session identity | Opaque UUID in httpOnly cookie, all state in SQLite | Starlette SessionMiddleware signs entire session dict into cookie — grows unboundedly and can be decoded. Opaque ID is simpler and safer | No |
| D008 | M001 | arch | Admin authentication | HTTPBasic + bcrypt 5.0.0 (direct, not passlib) | passlib is unmaintained, breaks on Python 3.13. bcrypt direct is simple and correct. timing-safe comparison via secrets.compare_digest | No |
| D009 | M001 | arch | Config hierarchy | Defaults → config.yaml → env vars → SQLite admin writes | Operators need both infra-as-code (YAML, env) AND live UI config. YAML seeds DB on first boot, then SQLite wins | No |
| D010 | M001 | arch | Scheduler | APScheduler 3.x AsyncIOScheduler (not 4.x alpha) | 3.x is stable and well-documented. 4.x is alpha with breaking changes | Yes — when 4.x ships stable |
| D011 | M001 | convention | TLS handling | Reverse proxy responsibility, not in-container | Standard self-hosted pattern. App provides startup warning when admin enabled without TLS. Secure deployment example with reverse proxy sidecar | No |
| D012 | M001 | convention | Commit strategy | Branch-per-slice with squash merge to main | Clean main history, one commit per slice, individually revertable | No |
| D013 | M001 | scope | Anti-features | OAuth/SSO, WebSocket, user accounts, embedded player, auto-update yt-dlp, subscription monitoring, FlareSolverr — all explicitly out of scope | Each would massively increase scope or conflict with anonymous-first, zero-telemetry positioning | No |
