# Feature Research

**Domain:** yt-dlp web frontend / self-hosted media downloader
**Researched:** 2026-03-17
**Confidence:** HIGH (core features), MEDIUM (UX patterns), HIGH (competitor gaps)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| URL paste + download | The core primitive — every tool has this | LOW | Must support all yt-dlp-supported sites, not just YouTube |
| Real-time download progress | Users need feedback; "Processing..." with no indicator is dead UX | MEDIUM | MeTube uses WebSocket; we use SSE — both solve this. SSE is simpler and HTTP-native with auto-reconnect |
| Queue view (active + completed) | Users submit multiple URLs; need to track all of them | LOW | MeTube separates active/done lists; unified queue with status is cleaner |
| Format/quality selection | Power users always want control over resolution, codec, ext | MEDIUM | Must show resolution, codec, ext, filesize estimate. yt-dlp returns all fields: height, vcodec, acodec, ext, filesize, fps |
| Playlist support | Playlists are a primary use case for self-hosters | HIGH | Parent + child job model. MeTube treats playlists as flat — collapsible parent/child is a step up |
| Cancel / remove a download | Users make mistakes | LOW | DELETE /api/downloads/{id}; must handle mid-stream cancellation gracefully |
| Persistent queue across refresh | Losing the queue on page refresh is unacceptable | MEDIUM | Requires SSE `init` event replaying state on connect. MeTube uses state file; our SQLite-backed SSE replay is equivalent |
| Mobile-accessible UI | >50% of self-hoster interactions happen on phone or tablet | HIGH | No existing yt-dlp web UI does mobile well. All competitors are desktop-first. 44px touch targets, bottom nav required |
| Docker distribution | The self-hosted audience expects Docker | LOW | Single image, both registries, amd64 + arm64 |
| Health endpoint | Ops audiences rely on this for monitoring integrations (Uptime Kuma, etc.) | LOW | `GET /api/health` with version, uptime, disk space, queue depth |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Session isolation (isolated / shared / open modes) | MeTube Issue #591 closed as "won't fix" — maintainer dismisses multi-user isolation as bloat; community forked it to add this | HIGH | Cookie-based httpOnly UUID4; operator chooses mode; addresses the exact pain point that created demand for forks |
| Cookie auth (cookies.txt upload per-session) | Enables paywalled/private content without embedding credentials in the app; yt-dlp Netscape format is well-documented | MEDIUM | Files must be scoped per-session, purged on session clear. Security note: cookie files are sensitive — never log, never expose via API, delete on purge |
| Drop-in custom themes via volume mount | No competitor offers this. MeTube has light/dark/auto only via env var. yt-dlp-web-ui has no theming | HIGH | CSS variable contract required first. Theme directory: theme.css + metadata.json + optional preview.png. Hot-loaded at startup |
| Heavily commented built-in themes as documentation | Lowers floor for customization to near-zero — anyone with a text editor or AI can retheme | LOW | No runtime cost. Every CSS token documented inline. Built-in themes serve as learning examples |
| Admin UI with username/password login (not raw token) | yt-dlp-web-ui uses JWT tokens in headers/query params — not user-friendly. MeTube has no admin UI at all. qBittorrent/Sonarr-style login is the expected self-hosted pattern | MEDIUM | First-boot credential setup with forced change prompt. Config-via-UI means no docker restarts for settings changes |
| Session export/import | No competitor offers portable session state. Enables identity continuity on persistent instances without a real account system | MEDIUM | JSON export of download history + queue state + preferences. Import restores history. Does not require sign-in, stays anonymous-first |
| Unsupported URL reporting with audit log | No competitor surfaces extraction errors with actionable reporting. MeTube just shows "error" | LOW | User-triggered only. Logs domain by default. Admin downloads log. Optional GitHub issue prefill |
| Source-aware output templates | Sensible per-site defaults (YouTube: uploader/title, SoundCloud: uploader/title, generic: title). MeTube uses one global template | LOW | Config-driven. Per-download override also supported |
| Link sharing (completed file URL) | Users want to share a ripped file with a friend — a direct download URL removes the "now what?" question | LOW | Serve completed files under predictable path. Requires knowing the output filename |
| Zero automatic outbound telemetry | Competing tools have subtle CDN calls, Google Fonts, or update checks. Trust is the core proposition | LOW | No external requests from container. All fonts/assets bundled or self-hosted |
| Cyberpunk default theme | Visual identity differentiator. Every other tool ships with plain material/tailwind defaults | MEDIUM | #00a8ff/#ff6b2b, JetBrains Mono, scanlines, grid overlay. Makes first impressions memorable |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| OAuth / SSO integration | Multi-user deployments want centralized auth | Massive scope increase; introduces external runtime dependency; anonymous-first identity model conflicts with account-based auth | Reverse proxy handles AuthN (Authentik, Authelia, Traefik ForwardAuth); media.rip handles AuthZ via session mode + admin token |
| Real-time everything via WebSocket | Seems more capable than SSE | WebSockets require persistent bidirectional connections, more complex infra, harder to load-balance; SSE covers 100% of the UI's actual needs (server-push only) | SSE — simpler, HTTP-native, auto-reconnecting via browser EventSource |
| User accounts / registration | Makes multi-user feel "proper" | Adds password hashing, email, account management, password reset flow — massive scope for a download tool; users expect anonymous operation | Session isolation mode: each browser gets its own cookie-scoped queue without any account |
| Automatic yt-dlp update on startup | Ensures latest extractor support | Breaks immutable containers and reproducible builds; version drift between deployments; network dependency at boot time | Pin yt-dlp version in requirements.txt; publish new image on yt-dlp releases via CI |
| Embedded video player | Looks impressive in demos | Adds significant frontend complexity, licensing surface for codecs, and scope creep for a downloader tool; most files need to go to Jellyfin/Plex anyway | Serve files at predictable paths; let users open in their preferred player |
| Telegram / Discord bot integration | Power users want remote submission | Separate runtime concern; adds credentials management, API rate limits, message parsing complexity; not what v1 needs to prove | Documented as v2+ extension point; clean API surface makes it straightforward to add later |
| Subscription / channel monitoring | "Set it and forget it" appeal | Fundamentally different product — a scheduler/archiver vs a download UI; scope would double; tools like Pinchflat, TubeArchivist do this better | Out of scope — architecture should not block adding it; APScheduler is already present for purge |
| Per-format download presets | Advanced users want "my 720p MP3 preset" saved | Medium complexity, but defers well to v1.x — v1 needs live format selection working first before persisting preferences | Implement after session system is stable; presets can be stored per-session in config |
| FlareSolverr / Cloudflare bypass | Some sites block yt-dlp | Introduces external service dependency, legal gray area, maintenance surface; YTPTube does this but it's an edge case | cookies.txt upload solves the authenticated content problem for most users; FlareSolverr is too niche for v1 |

## Feature Dependencies

```
[SQLite Job Store]
    └──required-by──> [Download Queue View]
    └──required-by──> [Real-Time SSE Progress]
    └──required-by──> [Playlist Parent/Child Jobs]

[Session System (cookie-based)]
    └──required-by──> [Session Isolation Mode]
    └──required-by──> [Cookie Auth (cookies.txt per-session)]
    └──required-by──> [Session Export/Import]
    └──required-by──> [SSE per-session stream]

[SSE Bus (per-session)]
    └──required-by──> [Real-Time Progress Updates]
    └──required-by──> [Init replay on reconnect]
    └──required-by──> [purge_complete event]

[yt-dlp Integration (library mode)]
    └──required-by──> [Format/Quality Selection (GET /api/formats)]
    └──required-by──> [Download execution]
    └──required-by──> [Playlist resolution → child jobs]
    └──required-by──> [Error detection → unsupported URL reporting]

[Admin Auth (username/password)]
    └──required-by──> [Admin Panel UI]
    └──required-by──> [Purge API endpoint]
    └──required-by──> [Session list / storage endpoints]
    └──required-by──> [Unsupported URL log download]

[CSS Variable Contract (base.css)]
    └──required-by──> [Built-in themes (cyberpunk, dark, light)]
    └──required-by──> [Drop-in custom themes]
    └──required-by──> [Theme picker UI]

[Theme Picker UI]
    └──enhances──> [Drop-in custom themes]

[Completed Download File Serving]
    └──required-by──> [Link sharing (shareable download URL)]

[Purge Scheduler (APScheduler)]
    └──enhances──> [Session TTL expiry]
    └──enhances──> [File and log TTL purge]

[Format/Quality Selection]
    └──enhances──> [Per-download output template override]

[Session Export]
    └──requires──> [Session System]
    └──conflicts-with~~> [open mode] (no session = nothing to export)
```

### Dependency Notes

- **Session system required before session export/import:** No session state to serialize without it. Export is meaningless in `open` mode.
- **SSE bus must exist before progress updates:** Progress hooks from yt-dlp thread pool need a dispatcher to push events to the correct session's queue.
- **yt-dlp integration required before format selection:** `GET /api/formats?url=` calls `yt-dlp.extract_info(process=False)` — format list is live-extracted, not pre-cached.
- **CSS variable contract required before any theming:** All three built-in themes and the drop-in theme system depend on the base.css token contract being stable. Changing token names later breaks all custom themes operators have written.
- **Job store required before queue view:** The frontend queue is a projection of SQLite state replayed via SSE `init` events — the DB is the source of truth, not frontend memory.
- **Admin auth required before admin panel:** Admin routes must be protected before the panel is built, otherwise the panel ships with no auth and operators have no safe path to production.
- **File serving endpoint required before link sharing:** Shareable URLs point to a served file path. This is a FastAPI `StaticFiles` or explicit route serving `/downloads`.

## MVP Definition

### Launch With (v1.0)

Minimum viable product — the full target feature set per PROJECT.md.

- [x] URL submission + auto-detection triggers format scraping — core primitive
- [x] Format/quality selector (populated live from yt-dlp info extraction) — power users won't use a tool that hides quality choice
- [x] Real-time progress via SSE (queued → extracting → downloading → completed/failed) — no progress = no trust
- [x] Download queue: filter, sort, cancel, playlist collapsible parent/child — queue management is table stakes
- [x] Session system: isolated (default) / shared / open — the primary differentiation from MeTube; isolated mode is the zero-config safe default
- [x] SSE init replay on reconnect — required for page refresh resilience; without this isolated mode is useless
- [x] Cookie auth (cookies.txt upload per-session, Netscape format) — enables paywalled content; the practical reason people move off MeTube
- [x] Purge system: scheduled / manual / never; independent file + log TTL — ephemeral storage is the contract with users
- [x] Three built-in themes: cyberpunk (default), dark, light — visual identity and immediate differentiation
- [x] Drop-in custom theme system (volume mount) — the feature request MeTube refuses to build
- [x] Mobile-responsive layout (bottom tabs + card list at <768px) — no competitor does mobile; 44px touch targets
- [x] Admin panel: username/password login, session list, storage, manual purge, unsupported URL log, live config — operators need a UI, not raw config
- [x] Unsupported URL reporting (user-triggered, domain-only by default) — trust feature; users see exactly what gets logged
- [x] Health endpoint (`GET /api/health`) — Uptime Kuma and similar monitoring tools are table stakes for self-hosters
- [x] Session export/import — enables identity continuity on persistent instances
- [x] Link sharing (source URL clipboard + completed file shareable URL) — reduces friction for the "share with a friend" use case
- [x] Zero automatic outbound telemetry — non-negotiable privacy baseline
- [x] Docker: single image, GHCR + Docker Hub, amd64 + arm64 — distribution is a feature

### Add After Validation (v1.x)

Features to add once core is working and v1.0 is shipped.

- [ ] Per-format/quality download presets — add when session system is stable and users ask for it
- [ ] Branding polish pass — tune cyberpunk defaults, tighten out-of-box experience, ensure built-in theme comments are comprehensive
- [ ] `reporting.github_issues: true` — pre-filled GitHub issue opening; disabled by default, enable only after log download is validated
- [ ] Queue filter/sort persistence — store last sort state in localStorage

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] External arr-stack API (Radarr/Sonarr programmatic integration) — architecture designed not to block this; clean API surface ready
- [ ] Download presets / saved quality profiles — needs session stability first
- [ ] Subscription / channel monitoring — fundamentally different product scope; defer to TubeArchivist/Pinchflat integration or separate milestone
- [ ] Telegram/Discord bot — documented extension point; clean REST API makes it straightforward

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| URL submission + download | HIGH | LOW | P1 |
| Real-time SSE progress | HIGH | MEDIUM | P1 |
| Format/quality selector | HIGH | MEDIUM | P1 |
| Job queue (view + cancel) | HIGH | LOW | P1 |
| Playlist parent/child jobs | HIGH | HIGH | P1 |
| Session isolation (cookie-based) | HIGH | HIGH | P1 |
| SSE init replay on reconnect | HIGH | MEDIUM | P1 |
| Three built-in themes | HIGH | MEDIUM | P1 |
| Mobile-responsive layout | HIGH | HIGH | P1 |
| Docker distribution | HIGH | LOW | P1 |
| Health endpoint | MEDIUM | LOW | P1 |
| Cookie auth (cookies.txt upload) | HIGH | MEDIUM | P1 |
| Purge system (scheduled/manual/never) | MEDIUM | MEDIUM | P1 |
| Admin panel (username/password) | MEDIUM | HIGH | P1 |
| Drop-in custom themes (volume mount) | MEDIUM | HIGH | P1 |
| Session export/import | MEDIUM | MEDIUM | P1 |
| Unsupported URL reporting | LOW | LOW | P1 |
| Link sharing | LOW | LOW | P1 |
| Zero outbound telemetry | HIGH | LOW | P1 (constraint, not feature) |
| Source-aware output templates | MEDIUM | LOW | P1 |
| Per-format download presets | MEDIUM | MEDIUM | P2 |
| GitHub issue prefill for reporting | LOW | LOW | P2 |
| Subscription/channel monitoring | MEDIUM | HIGH | P3 |
| Arr-stack API integration | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.0 launch
- P2: Should have in v1.x
- P3: Future milestone

## Competitor Feature Analysis

| Feature | MeTube | yt-dlp-web-ui | ytptube | media.rip() |
|---------|--------|---------------|---------|-------------|
| URL submission | Yes | Yes | Yes | Yes |
| Real-time progress | WebSocket | WebSocket/RPC | WebSocket | SSE (simpler, auto-reconnect) |
| Format selection | Quality presets (no live extraction) | Yes | Yes (presets) | Live extraction via `GET /api/formats` |
| Playlist support | Yes (flat) | Yes | Yes | Yes (collapsible parent/child) |
| Session isolation | No — all sessions see all downloads (closed as won't fix) | No | Basic auth only | Yes — isolated/shared/open modes |
| Cookie auth | Yes (global, not per-session) | No | Yes | Yes (per-session, purge-scoped) |
| Theming | light/dark/auto env var | None | None | 3 built-ins + drop-in custom themes |
| Mobile-first UI | No (desktop-first) | No | No | Yes (bottom tabs, card list, 44px targets) |
| Admin panel | No | Basic auth header | Basic auth | Username/password login UI, config editor |
| Session export/import | No | No | No | Yes |
| Purge policy | `CLEAR_COMPLETED_AFTER` only | No | No | scheduled/manual/never, independent TTLs |
| Unsupported URL reporting | Error shown only | Error shown only | Error shown only | User-triggered log + admin download |
| Health endpoint | No | No | No | Yes — version, uptime, disk space, queue depth |
| Link sharing | Base URL config only | No | No | Clipboard + direct file download URL |
| Zero telemetry | Yes | Yes | Yes | Yes (explicit design constraint) |
| Docker distribution | Yes (amd64 only) | Yes | Yes | Yes (amd64 + arm64) |

## Edge Cases and Expected Behaviors

### Format Selection

- **Slow info extraction:** `GET /api/formats?url=` calls `extract_info(process=False)` — for some sites this takes 3-10 seconds. UI must show a loading state on the format picker immediately after URL is pasted.
- **No formats returned:** Some sites return a direct URL without format list. UI should fall back to "Best available" option gracefully.
- **Audio-only formats:** Some formats have `vcodec: none` — these should be labeled clearly (e.g., "Audio only — MP3 128kbps").
- **Format IDs are extractor-specific:** `format_id` values are not portable across sites; always pass them as opaque strings to yt-dlp.
- **filesize field is frequently null:** Many formats don't report filesize in the info_dict. Show "~estimate" or "unknown" — never show 0.

### Cookie Auth

- **Cookie expiry:** Cookies expire within ~2 weeks of export. yt-dlp will fail with auth error after expiry — job should show `failed` with a "cookies may be expired" hint.
- **Cookie scope:** cookies.txt contains all site cookies from the browser export. Users should understand this is sensitive. Never log cookie file contents; purge on session clear.
- **Chrome cookie extraction broken since July 2024:** Chrome's App-Bound Encryption makes external extraction impossible. Firefox is the recommended browser for cookie export. UI should surface this note in the cookie upload flow.
- **CRLF vs LF:** Windows-generated cookies.txt files may use CRLF line endings, causing yt-dlp parse errors. Backend should normalize to LF on upload.

### Playlist Downloads

- **Large playlists:** A 200-video playlist creates 201 rows in the queue (1 parent + 200 children). UI must handle this gracefully — collapsed by default, with count shown on parent row.
- **Mixed success/failure in playlists:** Some child videos in a playlist may be geo-blocked or removed. Parent job should complete with a `partial` status or show child failure counts.
- **Playlist URL re-extraction:** If a user submits the same playlist URL twice, they get two independent parent jobs (keyed by UUID, not URL). This is intentional per PROJECT.md.

### Session System

- **SSE reconnect race:** If the user refreshes while a download is mid-progress, the SSE `init` event must replay the current job state. Without this, the queue appears empty after refresh even though downloads are running.
- **Session mode changes by operator:** If an operator switches from `isolated` to `shared` mid-deployment, existing per-session rows remain scoped to their session IDs. `shared` mode queries all rows regardless of session_id. This is a data model concern — no migration needed, but operator docs should explain the behavior.
- **`open` mode + session export conflict:** In `open` mode, no session is assigned (session_id = null). Session export has nothing to export. UI should hide the export button in `open` mode.

### Purge

- **Purge while download is active:** Purge must skip jobs with status `downloading` or `queued`. Only `completed`, `failed`, and `expired` jobs are eligible.
- **File already deleted manually:** If a user deletes a file from `/downloads` outside the app, purge should handle the missing file gracefully (log it, continue).
- **Log TTL vs file TTL independence:** The design intentionally allows keeping logs longer than files (e.g., files_ttl_hours: 24, logs_ttl_hours: 168). The purge.scope config controls what gets deleted.

## Sources

- [MeTube GitHub — alexta69/metube](https://github.com/alexta69/metube)
- [MeTube Issue #591 — User management / per-user isolation request](https://github.com/alexta69/metube/issues/591)
- [MeTube Issue #535 — Optional login page request](https://github.com/alexta69/metube/issues/535)
- [yt-dlp-web-ui — marcopiovanello/yt-dlp-web-ui](https://github.com/marcopiovanello/yt-dlp-web-ui)
- [yt-dlp-web-ui Authentication methods wiki](https://github.com/marcopiovanello/yt-dlp-web-ui/wiki/Authentication-methods)
- [ytptube — arabcoders/ytptube](https://github.com/arabcoders/ytptube)
- [yt-dlp Information Extraction Pipeline — DeepWiki](https://deepwiki.com/yt-dlp/yt-dlp/2.2-information-extraction-pipeline)
- [yt-dlp cookie system — DeepWiki](https://deepwiki.com/yt-dlp/yt-dlp/5.5-browser-integration-and-cookie-system)
- [The Ultimate Guide to GUI Front-Ends for yt-dlp 2025 — BrightCoding](https://www.blog.brightcoding.dev/2025/12/06/the-ultimate-guide-to-gui-front-ends-for-youtube-dl-yt-dlp-download-videos-like-a-pro-2025-edition/)
- [6 Ways to Get YouTube Cookies for yt-dlp in 2026 — DEV Community](https://dev.to/osovsky/6-ways-to-get-youtube-cookies-for-yt-dlp-in-2026-only-1-works-2cnb)
- [MeTube on Hacker News — user discussion of limitations](https://news.ycombinator.com/item?id=41098974)

---
*Feature research for: yt-dlp web frontend / self-hosted media downloader*
*Researched: 2026-03-17*
