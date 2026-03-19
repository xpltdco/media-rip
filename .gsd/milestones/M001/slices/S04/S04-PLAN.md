# S04: Admin, Auth + Supporting Features

**Goal:** Deliver admin authentication, purge system, cookie auth upload, file serving for link sharing, unsupported URL logging, and an admin frontend panel — all behind bcrypt-secured HTTPBasic auth with security headers and TLS detection warning.
**Demo:** Navigate to /admin → prompted for credentials → login with bcrypt-hashed password → see session list, storage overview, unsupported URL log. Trigger manual purge → expired files cleaned. Upload cookies.txt on the main UI → authenticated download succeeds. Copy a shareable link for a completed download → opens in new tab. Startup logs warn if TLS not detected.

## Must-Haves

- Admin auth: HTTPBasic + bcrypt, `Depends(require_admin)` on all admin routes
- First-boot: if no admin credentials configured, admin panel disabled (not silently open)
- Security headers on admin routes: X-Content-Type-Options, X-Frame-Options
- TLS detection: startup warning when admin enabled without `X-Forwarded-Proto: https`
- Purge service: APScheduler cron job (configurable) + manual trigger via admin API
- Purge logic: delete files + DB rows for completed/failed/expired jobs older than TTL, skip active
- Cookie auth: `POST /api/cookies` uploads Netscape cookies.txt per-session, `DELETE /api/cookies` removes
- File serving: `GET /downloads/{filename}` serves completed files for link sharing (R018)
- Unsupported URL log: failed extractions logged to `unsupported_urls` table, admin can list/download
- Admin API: `GET /api/admin/sessions`, `GET /api/admin/storage`, `POST /api/admin/purge`, `GET /api/admin/unsupported-urls`
- Admin frontend: Vue route `/admin` with login form, session list, storage view, purge button
- All existing 122 backend tests + 21 frontend tests still pass

## Proof Level

- This slice proves: integration (admin auth protecting routes, purge deleting correct files, cookie auth enabling authenticated downloads)
- Real runtime required: yes (bcrypt hashing, file I/O, APScheduler)
- Human/UAT required: yes (admin login flow, file download verification)

## Verification

- `cd backend && .venv/Scripts/python -m pytest tests/ -v` — all tests pass (S01-S04)
- `cd frontend && npx vitest run` — all frontend tests pass
- `cd frontend && npm run build` — zero errors
- `backend/tests/test_admin_auth.py` — auth required, bcrypt verification, security headers
- `backend/tests/test_purge.py` — TTL filtering, active job protection, file cleanup
- `backend/tests/test_cookies.py` — upload, session scoping, CRLF normalization, deletion
- `backend/tests/test_file_serving.py` — completed file served, 404 for missing

## Observability / Diagnostics

- Runtime signals: `mediarip.admin` logger at INFO for login attempts; `mediarip.purge` at INFO for purge runs with count of deleted files/rows
- Inspection surfaces: `GET /api/admin/sessions` lists active sessions; `GET /api/admin/storage` shows disk usage; `GET /api/admin/unsupported-urls` shows failed extractions
- Failure visibility: purge logs include skipped-active count; cookie upload logs session_id + filename (never contents)
- Redaction constraints: admin password_hash never in responses; cookie file contents never logged

## Integration Closure

- Upstream surfaces consumed: `database.py` (jobs, sessions tables), `config.py` (admin, purge, session settings), `SessionMiddleware` (session identity), `SSEBroker` (purge_complete event), `DownloadService` (cancel)
- New wiring introduced: admin auth middleware, purge scheduler in lifespan, cookie file storage, static file serving, admin Vue routes
- What remains: S05 (theme system), S06 (Docker + CI/CD)

## Tasks

- [x] **T01: Admin auth middleware + security headers + TLS warning** `est:45m`
  - Why: Every admin route depends on authentication existing. Must be first.
  - Files: `backend/app/dependencies.py`, `backend/app/main.py`, `backend/tests/test_admin_auth.py`
  - Do: Add `require_admin` dependency using HTTPBasic + bcrypt. Check `config.admin.enabled` — if disabled, return 404 for all admin routes. Compare credentials with `secrets.compare_digest` for username, `bcrypt.checkpw` for password. Add security headers middleware for admin routes (X-Content-Type-Options: nosniff, X-Frame-Options: DENY). Log TLS warning at startup if admin enabled and no HTTPS indicators. Write tests: unauthenticated → 401, wrong password → 401, correct credentials → 200, disabled admin → 404, security headers present.
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_auth.py -v`
  - Done when: Admin routes require valid credentials, security headers present, TLS warning logged when appropriate

- [x] **T02: Purge service with APScheduler + manual trigger** `est:45m`
  - Why: Closes R009 (purge system). Operators need control over disk lifecycle.
  - Files: `backend/app/services/purge.py`, `backend/app/routers/admin.py`, `backend/app/main.py`, `backend/tests/test_purge.py`
  - Do: Build `PurgeService` with `run_purge(db, config, output_dir)` — queries jobs where `status IN (completed, failed, expired)` AND `completed_at < now - max_age_hours`, deletes files from disk (handle already-deleted gracefully), deletes DB rows, returns count. Wire APScheduler `AsyncIOScheduler` in lifespan — add cron job if `config.purge.enabled`. Add `POST /api/admin/purge` endpoint (requires admin) for manual trigger. Write tests: purge deletes old completed files, skips active jobs, handles missing files, counts correctly.
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_purge.py -v`
  - Done when: Scheduled purge runs on cron, manual purge via API works, active jobs protected

- [x] **T03: Cookie auth upload + file serving + unsupported URL logging** `est:45m`
  - Why: Closes R008 (cookie auth), R018 (link sharing), R015 (unsupported URL logging) — the remaining supporting features.
  - Files: `backend/app/routers/cookies.py`, `backend/app/routers/files.py`, `backend/app/core/database.py`, `backend/app/main.py`, `backend/tests/test_cookies.py`, `backend/tests/test_file_serving.py`
  - Do: Cookie upload: `POST /api/cookies` accepts multipart file, saves to `data/sessions/{session_id}/cookies.txt`, normalizes CRLF→LF. `DELETE /api/cookies` removes the file. Wire cookie path into DownloadService ydl_opts when present. File serving: mount `/downloads` as StaticFiles for completed file access (R018). Unsupported URL logging: on extraction failure, insert into `unsupported_urls` table. Admin endpoint `GET /api/admin/unsupported-urls` returns the log. Write tests for each.
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_cookies.py tests/test_file_serving.py -v`
  - Done when: Cookie upload scoped to session, files served at predictable URLs, unsupported URLs logged

- [x] **T04: Admin API endpoints (sessions, storage, config)** `est:30m`
  - Why: Admin panel needs data to display — session list, storage usage, live config.
  - Files: `backend/app/routers/admin.py`, `backend/app/core/database.py`, `backend/tests/test_admin_api.py`
  - Do: `GET /api/admin/sessions` — list all sessions with job counts, last_seen. `GET /api/admin/storage` — disk usage of output_dir (total, used, free), job count by status. `GET /api/admin/unsupported-urls` — paginated list from unsupported_urls table. All require admin auth. Write tests.
  - Verify: `cd backend && .venv/Scripts/python -m pytest tests/test_admin_api.py -v`
  - Done when: All admin data endpoints return correct data behind auth

- [x] **T05: Admin frontend panel** `est:1h`
  - Why: Operators need a UI, not raw API calls. Closes the admin UX loop.
  - Files: `frontend/src/components/AdminPanel.vue`, `frontend/src/components/AdminLogin.vue`, `frontend/src/stores/admin.ts`, `frontend/src/App.vue`
  - Do: Add vue-router with routes: `/` (main app), `/admin` (admin panel). AdminLogin.vue: username/password form, stores credentials for Basic auth header. AdminPanel.vue: tabbed view with Sessions, Storage, Purge, Unsupported URLs sections. Wire admin store for API calls with Basic auth. Add nav link to admin panel (visible only when admin.enabled in public config). Write vitest tests for admin store.
  - Verify: `cd frontend && npm run build && npx vitest run`
  - Done when: Admin panel accessible at /admin with login, shows sessions/storage/purge

## Files Likely Touched

- `backend/app/dependencies.py` — require_admin
- `backend/app/services/purge.py` — new
- `backend/app/routers/admin.py` — new
- `backend/app/routers/cookies.py` — new
- `backend/app/routers/files.py` — new
- `backend/app/core/database.py` — unsupported URL CRUD, session list with counts
- `backend/app/main.py` — APScheduler, new routers, TLS warning
- `backend/tests/test_admin_auth.py` — new
- `backend/tests/test_purge.py` — new
- `backend/tests/test_cookies.py` — new
- `backend/tests/test_file_serving.py` — new
- `backend/tests/test_admin_api.py` — new
- `frontend/src/stores/admin.ts` — new
- `frontend/src/components/AdminPanel.vue` — new
- `frontend/src/components/AdminLogin.vue` — new
- `frontend/src/App.vue` — add router
- `frontend/package.json` — add vue-router
