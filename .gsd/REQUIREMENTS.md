# Requirements

This file is the explicit capability and coverage contract for the project.

Use it to track what is actively in scope, what has been validated by completed work, what is intentionally deferred, and what is explicitly out of scope.

## Active

### R001 — URL submission + download for any yt-dlp-supported site
- Class: core-capability
- Status: active
- Description: User pastes any URL supported by yt-dlp and the system downloads it to the configured output directory
- Why it matters: The fundamental product primitive — everything else depends on this working
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Jobs keyed by UUID4 (R024), not URL — concurrent same-URL downloads are supported

### R002 — Live format/quality extraction and selection
- Class: core-capability
- Status: active
- Description: GET /api/formats?url= calls yt-dlp extract_info to return available formats; user picks resolution, codec, ext before downloading
- Why it matters: Power users won't use a tool that hides quality choice. Competitors use presets — live extraction is a step up
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: Extraction can take 3-10s for some sites — UI must show loading state. filesize is frequently null

### R003 — Real-time SSE progress
- Class: core-capability
- Status: active
- Description: Server-sent events stream delivers job status transitions (queued→extracting→downloading→completed/failed) with download progress (percent, speed, ETA) per session
- Why it matters: No progress = no trust. Users need to see something is happening
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: SSE via sse-starlette, not WebSocket. Events: init, job_update, job_removed, error, purge_complete

### R004 — SSE init replay on reconnect
- Class: continuity
- Status: active
- Description: When a client reconnects to the SSE endpoint, the server replays current job states from the DB as synthetic events before entering the live queue
- Why it matters: Without this, page refresh clears the queue view even though downloads are running. Breaks session isolation's value proposition entirely
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: none
- Validation: unmapped
- Notes: Eliminates "spinner forever after refresh" bugs. The DB is source of truth, not frontend memory

### R005 — Download queue: view, cancel, filter, sort
- Class: primary-user-loop
- Status: active
- Description: Users see all their downloads in a unified queue with status, progress, and can cancel or remove entries. Filter by status, sort by date/name
- Why it matters: Table stakes for any download manager UX
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: unmapped
- Notes: Queue is a projection of SQLite state replayed via SSE

### R006 — Playlist support: parent + collapsible child jobs
- Class: core-capability
- Status: active
- Description: Playlist URLs create a parent job with collapsible child video rows. Parent status reflects aggregate child progress. Mixed success/failure shown per child
- Why it matters: Playlists are a primary use case for self-hosters. MeTube treats them as flat — collapsible parent/child is a step up
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: M001/S01
- Validation: unmapped
- Notes: A 200-video playlist = 201 rows — must be collapsed by default. Parent completes when all children reach completed or failed

### R007 — Session isolation: isolated (default) / shared / open modes
- Class: differentiator
- Status: active
- Description: Operator selects session mode server-wide. Isolated: each browser sees only its own downloads via httpOnly UUID cookie. Shared: all sessions see all downloads. Open: no session tracking
- Why it matters: The primary differentiator from MeTube (issue #591 closed as "won't fix"). The feature that created demand for forks
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: isolated is the zero-config safe default. Mode switching mid-deployment: isolated rows remain scoped, shared queries all rows

### R008 — Cookie auth: per-session cookies.txt upload
- Class: core-capability
- Status: active
- Description: Users upload a Netscape-format cookies.txt file scoped to their session. Enables downloading paywalled/private content. Files purged on session clear
- Why it matters: The practical reason people move off MeTube. Enables authenticated downloads without embedding credentials in the app
- Source: research
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: CVE-2023-35934 — pin yt-dlp >= 2023-07-06. Store per-session at data/sessions/{id}/cookies.txt. Never log contents. Normalize CRLF→LF. Chrome cookie extraction broken since July 2024 — surface Firefox recommendation in UI

### R009 — Purge system: scheduled/manual/never, independent file + log TTL
- Class: operability
- Status: active
- Description: Operator configures purge mode (scheduled cron, manual-only, never). File TTL and log TTL are independent values. Purge activity written to audit log. Purge must skip active downloads
- Why it matters: Ephemeral storage is the contract with users. Operators need control over disk lifecycle
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Purge must filter status IN (completed, failed, cancelled) — never delete files for active downloads. Handle already-deleted files gracefully

### R010 — Three built-in themes: cyberpunk (default), dark, light
- Class: differentiator
- Status: active
- Description: Three themes baked into the Docker image. Cyberpunk is default: #00a8ff/#ff6b2b, JetBrains Mono, scanlines, grid overlay. Dark and light are clean alternatives
- Why it matters: Visual identity differentiator — every other tool ships with plain material/tailwind defaults. Cyberpunk makes first impressions memorable
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: none
- Validation: unmapped
- Notes: Built-in themes compiled into frontend bundle. Heavily commented as drop-in documentation for custom theme authors

### R011 — Drop-in custom theme system via volume mount
- Class: differentiator
- Status: active
- Description: Operators drop a theme folder into /themes volume mount. Theme pack: theme.css (CSS variable overrides) + metadata.json + optional preview.png + optional assets/. Appears in picker without recompile
- Why it matters: The feature MeTube refuses to build. Lowers theming floor to "edit a CSS file"
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: none
- Validation: unmapped
- Notes: Theme directory scanned at startup + on-demand re-scan. No file watchers needed

### R012 — CSS variable contract (base.css) as stable theme API
- Class: constraint
- Status: active
- Description: A documented, stable set of CSS custom properties (--color-bg, --color-accent-primary, --font-ui, --radius-sm, --effect-overlay, etc.) that all themes override. Token names cannot change after v1.0 ships — they are the public API for custom themes
- Why it matters: Changing token names after operators write custom themes breaks those themes. This is a one-way door
- Source: user
- Primary owning slice: M001/S05
- Supporting slices: M001/S03
- Validation: unmapped
- Notes: Must be designed before component work references token names. Establish early in S05, referenced by S03 components

### R013 — Mobile-responsive layout
- Class: primary-user-loop
- Status: active
- Description: <768px breakpoint: bottom tab bar (Submit/Queue/Settings), full-width URL input, card list for queue (swipe-to-cancel), bottom sheet for format options. All tap targets minimum 44px
- Why it matters: >50% of self-hoster interactions happen on phone or tablet. No existing yt-dlp web UI does mobile well
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: unmapped
- Notes: Desktop (≥768px): top header bar, left sidebar (collapsible), full download table

### R014 — Admin panel with secure auth
- Class: operability
- Status: active
- Description: Admin panel with username/password login (HTTPBasic + bcrypt). First-boot credential setup with forced change prompt. Session list, storage view, manual purge trigger, live config editor, unsupported URL log download. Security posture: timing-safe comparison (secrets.compare_digest), Secure/HttpOnly/SameSite=Strict cookies behind TLS, security headers on admin routes (HSTS, X-Content-Type-Options, X-Frame-Options), startup warning when admin enabled without TLS detected
- Why it matters: Shipping an admin panel with crappy auth undermines the trust proposition of the entire product. Operators deserve qBittorrent/Sonarr-level login UX, not raw tokens
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: If no X-Forwarded-Proto: https detected, log warning. Admin routes hidden from nav unless credentials configured

### R015 — Unsupported URL reporting with audit log
- Class: failure-visibility
- Status: active
- Description: When yt-dlp fails with extraction error, job shows failed badge + "Report unsupported site" button. Click appends to log (domain-only by default, full URL opt-in). Admin downloads log. Zero automatic outbound reporting
- Why it matters: Users see exactly what gets logged. Trust feature — transparency in failure handling
- Source: user
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: User-triggered only. Config report_full_url controls privacy level

### R016 — Health endpoint
- Class: operability
- Status: active
- Description: GET /api/health returns status, version, yt_dlp_version, uptime
- Why it matters: Uptime Kuma and similar monitoring tools are table stakes for self-hosters
- Source: user
- Primary owning slice: M001/S02
- Supporting slices: none
- Validation: unmapped
- Notes: Extend with disk space and queue depth if practical

### R017 — Session export/import
- Class: continuity
- Status: active
- Description: Export session as JSON archive (download history + queue state + preferences). Import restores history into a new session. Does not require sign-in, stays anonymous-first
- Why it matters: Enables identity continuity on persistent instances without a real account system. No competitor offers this
- Source: research
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Meaningless in open mode — UI should hide export button when session mode is open

### R018 — Link sharing (completed file shareable URL)
- Class: primary-user-loop
- Status: active
- Description: Completed downloads are served at predictable URLs. Users can copy a direct download link to share with others
- Why it matters: Removes the "now what?" question after downloading — users share a ripped file with a friend via URL
- Source: research
- Primary owning slice: M001/S04
- Supporting slices: none
- Validation: unmapped
- Notes: Requires knowing the output filename. Files served via FastAPI StaticFiles or explicit route on /downloads

### R019 — Source-aware output templates
- Class: core-capability
- Status: active
- Description: Per-site default output templates (YouTube: uploader/title, SoundCloud: uploader/title, generic: title). Configurable via config.yaml source_templates map
- Why it matters: Sensible defaults per-site are a step up from MeTube's single global template. Organizes downloads without user effort
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Per-download override also supported (R025)

### R020 — Zero automatic outbound telemetry
- Class: constraint
- Status: active
- Description: The container makes zero automatic outbound network requests. No CDN calls, no Google Fonts, no update checks, no analytics. All fonts and assets bundled or self-hosted
- Why it matters: Trust is the core proposition. Competing tools have subtle external requests. This is an explicit design constraint, not an afterthought
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: all
- Validation: unmapped
- Notes: Verified by checking zero outbound network requests from container during normal operation

### R021 — Docker: single multi-stage image, GHCR + Docker Hub, amd64 + arm64
- Class: launchability
- Status: active
- Description: Single Dockerfile, multi-stage build (Node frontend builder → Python deps → slim runtime with ffmpeg). Published to ghcr.io/xpltd/media-rip and docker.io/xpltd/media-rip. Both amd64 and arm64 architectures
- Why it matters: Docker is the distribution mechanism for self-hosted tools. arm64 users (Raspberry Pi, Apple Silicon NAS) are a significant audience
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: none
- Validation: unmapped
- Notes: Target <400MB compressed. ffmpeg from Debian apt supports arm64 natively

### R022 — CI/CD: lint + test on PR, build + push on tag
- Class: launchability
- Status: active
- Description: GitHub Actions: ci.yml runs ruff + pytest + eslint + vue-tsc + vitest + Docker smoke on PRs. publish.yml builds multi-platform image and pushes to both registries on v*.*.* tags. Generates GitHub Release with changelog
- Why it matters: Ensures the image stays functional as yt-dlp extractors evolve. Automated quality gate
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: none
- Validation: unmapped
- Notes: CI smoke-tests downloads from 2+ sites to catch extractor breakage

### R023 — Config system: config.yaml + env var overrides + admin live writes
- Class: operability
- Status: active
- Description: Three-layer config: hardcoded defaults → config.yaml (read-only at start) → env var overrides (MEDIARIP__SECTION__KEY) → SQLite admin writes (live, no restart). All fields optional — zero-config works out of the box
- Why it matters: Operators need infrastructure-as-code (YAML, env vars) AND live UI config without restart
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: M001/S04
- Validation: unmapped
- Notes: YAML seeds DB on first boot, then SQLite wins. YAML never reflects admin UI changes — document this clearly

### R024 — Concurrent same-URL support
- Class: core-capability
- Status: active
- Description: Jobs keyed by UUID4, not URL. Submitting the same URL twice at different qualities creates two independent jobs
- Why it matters: Users legitimately want the same video in different formats. URL-keyed dedup would prevent this
- Source: user
- Primary owning slice: M001/S01
- Supporting slices: none
- Validation: unmapped
- Notes: Intentional design per PROJECT.md

### R025 — Per-download output template override
- Class: core-capability
- Status: active
- Description: Users can override the output template on a per-download basis, in addition to the source-aware defaults (R019)
- Why it matters: Power users want control over file naming for specific downloads
- Source: user
- Primary owning slice: M001/S03
- Supporting slices: none
- Validation: unmapped
- Notes: UI field in "More options" area

### R026 — Secure deployment example
- Class: launchability
- Status: active
- Description: docker-compose.example.yml ships with a reverse proxy + TLS configuration as the default documented deployment path, not an afterthought
- Why it matters: Making the secure path the default path prevents operators from accidentally running admin auth over cleartext
- Source: user
- Primary owning slice: M001/S06
- Supporting slices: none
- Validation: unmapped
- Notes: Caddy or Traefik sidecar — decision deferred to slice planning

## Deferred

### R027 — Per-format download presets (saved quality profiles)
- Class: primary-user-loop
- Status: deferred
- Description: Save "my 720p MP3 preset" for reuse across downloads
- Why it matters: Convenience feature for repeat users
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Deferred — v1 needs live format selection working first. Add when session system is stable

### R028 — GitHub issue prefill for unsupported URL reporting
- Class: failure-visibility
- Status: deferred
- Description: Config option reporting.github_issues: true opens pre-filled GitHub issue for unsupported URLs
- Why it matters: Streamlines community reporting of extractor gaps
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Deferred — enable only after log download (R015) is validated

### R029 — Queue filter/sort persistence in localStorage
- Class: primary-user-loop
- Status: deferred
- Description: Store last sort/filter state in localStorage so it persists across page loads
- Why it matters: Minor convenience — avoids resetting sort every refresh
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: unmapped
- Notes: Trivial to add post-v1

## Out of Scope

### R030 — OAuth / SSO integration
- Class: anti-feature
- Status: out-of-scope
- Description: Centralized auth via OAuth/SSO providers
- Why it matters: Prevents massive scope increase. Reverse proxy handles AuthN; media.rip handles AuthZ via session mode + admin auth
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Authentik, Authelia, Traefik ForwardAuth are the operator's tools for this

### R031 — WebSocket transport
- Class: anti-feature
- Status: out-of-scope
- Description: WebSocket for real-time communication
- Why it matters: SSE covers 100% of actual needs (server-push only). WebSocket adds complexity without benefit
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: SSE is simpler, HTTP-native, auto-reconnecting via browser EventSource

### R032 — User accounts / registration
- Class: anti-feature
- Status: out-of-scope
- Description: User registration, login, password reset
- Why it matters: Anonymous-first identity model. Session isolation provides multi-user support without accounts
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Would fundamentally change the product shape

### R033 — Automatic yt-dlp update at runtime
- Class: anti-feature
- Status: out-of-scope
- Description: Auto-update yt-dlp extractors inside running container
- Why it matters: Breaks immutable containers and reproducible builds. Version drift between deployments
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Pin version in requirements; publish new image on yt-dlp releases via CI

### R034 — Embedded video player
- Class: anti-feature
- Status: out-of-scope
- Description: Play downloaded media within the web UI
- Why it matters: Adds significant frontend complexity, licensing surface for codecs, scope creep. Files go to Jellyfin/Plex anyway
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Serve files at predictable paths; users open in their preferred player

### R035 — Subscription / channel monitoring
- Class: anti-feature
- Status: out-of-scope
- Description: "Set it and forget it" channel archiving
- Why it matters: Fundamentally different product — a scheduler/archiver vs a download UI. Tools like Pinchflat, TubeArchivist do this better
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: Architecture should not block adding it later. APScheduler already present for purge

### R036 — FlareSolverr / Cloudflare bypass
- Class: anti-feature
- Status: out-of-scope
- Description: Cloudflare bypass via external FlareSolverr service
- Why it matters: Introduces external service dependency, legal gray area, niche use case
- Source: research
- Primary owning slice: none
- Supporting slices: none
- Validation: n/a
- Notes: cookies.txt upload (R008) solves authenticated content for most users

## Traceability

| ID | Class | Status | Primary owner | Supporting | Proof |
|---|---|---|---|---|---|
| R001 | core-capability | active | M001/S01 | none | unmapped |
| R002 | core-capability | active | M001/S01 | M001/S03 | unmapped |
| R003 | core-capability | active | M001/S02 | M001/S03 | unmapped |
| R004 | continuity | active | M001/S02 | none | unmapped |
| R005 | primary-user-loop | active | M001/S03 | none | unmapped |
| R006 | core-capability | active | M001/S03 | M001/S01 | unmapped |
| R007 | differentiator | active | M001/S02 | M001/S03 | unmapped |
| R008 | core-capability | active | M001/S04 | none | unmapped |
| R009 | operability | active | M001/S04 | none | unmapped |
| R010 | differentiator | active | M001/S05 | none | unmapped |
| R011 | differentiator | active | M001/S05 | none | unmapped |
| R012 | constraint | active | M001/S05 | M001/S03 | unmapped |
| R013 | primary-user-loop | active | M001/S03 | none | unmapped |
| R014 | operability | active | M001/S04 | none | unmapped |
| R015 | failure-visibility | active | M001/S04 | none | unmapped |
| R016 | operability | active | M001/S02 | none | unmapped |
| R017 | continuity | active | M001/S04 | none | unmapped |
| R018 | primary-user-loop | active | M001/S04 | none | unmapped |
| R019 | core-capability | active | M001/S01 | none | unmapped |
| R020 | constraint | active | M001/S06 | all | unmapped |
| R021 | launchability | active | M001/S06 | none | unmapped |
| R022 | launchability | active | M001/S06 | none | unmapped |
| R023 | operability | active | M001/S01 | M001/S04 | unmapped |
| R024 | core-capability | active | M001/S01 | none | unmapped |
| R025 | core-capability | active | M001/S03 | none | unmapped |
| R026 | launchability | active | M001/S06 | none | unmapped |
| R027 | primary-user-loop | deferred | none | none | unmapped |
| R028 | failure-visibility | deferred | none | none | unmapped |
| R029 | primary-user-loop | deferred | none | none | unmapped |
| R030 | anti-feature | out-of-scope | none | none | n/a |
| R031 | anti-feature | out-of-scope | none | none | n/a |
| R032 | anti-feature | out-of-scope | none | none | n/a |
| R033 | anti-feature | out-of-scope | none | none | n/a |
| R034 | anti-feature | out-of-scope | none | none | n/a |
| R035 | anti-feature | out-of-scope | none | none | n/a |
| R036 | anti-feature | out-of-scope | none | none | n/a |

## Coverage Summary

- Active requirements: 26
- Mapped to slices: 26
- Validated: 0
- Unmapped active requirements: 0
