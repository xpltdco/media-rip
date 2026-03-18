# Pitfalls Research

**Domain:** yt-dlp web frontend — FastAPI + Vue 3 + SSE + SQLite + Docker
**Researched:** 2026-03-17
**Confidence:** HIGH (critical pitfalls verified via official yt-dlp issues, sse-starlette docs, CVE advisories; MEDIUM for performance traps and Docker sizing which rely on community sources)

---

## Critical Pitfalls

### Pitfall 1: Using a Single YoutubeDL Instance for Concurrent Downloads

**What goes wrong:**
Multiple in-flight downloads share one `YoutubeDL` instance. Instance state (cookies, temp files, internal logger, download archive state) is mutated per-download, causing downloads to corrupt each other's progress data, swap cookies, or raise `TypeError` on `None` fields when hooks fire out of order.

**Why it happens:**
yt-dlp is documented as a library by example (`with YoutubeDL(opts) as ydl: ydl.download([url])`), which looks reusable. There is no explicit "not thread-safe" warning in the README. Developers assume the object is stateless between calls.

**How to avoid:**
Create a fresh `YoutubeDL` instance per download job, inside the worker function. Never share an instance across concurrent threads or tasks:

```python
def _run_download(job_id: str, url: str, opts: dict):
    with YoutubeDL({**opts, "progress_hooks": [make_hook(job_id)]}) as ydl:
        ydl.download([url])
```

Run this inside `loop.run_in_executor(thread_pool, _run_download, ...)` so the FastAPI event loop is not blocked. The YoutubeDL object never crosses the thread boundary.

**Warning signs:**
- Progress percentages jump between unrelated jobs
- Two downloads finish at the same time and one reports 0% or corrupted size
- `TypeError: '>' not supported between 'NoneType' and 'int'` in progress hook (a known issue when hook receives stale None from another job's state)

**Phase to address:**
Core download engine (Phase 1 / foundation). This is the fundamental architecture decision — get it right before building progress reporting on top of it.

---

### Pitfall 2: Calling asyncio Primitives from a yt-dlp Progress Hook

**What goes wrong:**
The progress hook fires inside the `ThreadPoolExecutor` worker thread, not on the asyncio event loop. Calling `asyncio.Queue.put()`, `asyncio.Event.set()`, or any awaitable directly from the hook raises `RuntimeError: no running event loop` or silently does nothing.

**Why it happens:**
Progress hooks feel like callbacks, and callbacks in async Python code are usually called on the event loop. But yt-dlp is synchronous — its hooks fire on whichever OS thread is running the download. `loop.run_in_executor` moves the whole call to a thread pool; the hook fires inside that thread.

**How to avoid:**
Use `loop.call_soon_threadsafe()` to bridge the thread back to the event loop:

```python
def make_hook(job_id: str, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
    def hook(d: dict):
        # Called from thread — must not await or call asyncio directly
        loop.call_soon_threadsafe(queue.put_nowait, {
            "job_id": job_id,
            "status": d.get("status"),
            "downloaded": d.get("downloaded_bytes"),
            "total": d.get("total_bytes"),
        })
    return hook
```

Capture `asyncio.get_event_loop()` in the FastAPI startup context (before executor threads start) and pass it into the hook factory.

**Warning signs:**
- SSE stream connects but never receives progress updates
- `RuntimeError: no running event loop` in thread worker logs
- Progress updates arrive in large batches rather than incrementally (queued but not flushed)

**Phase to address:**
Core download engine (Phase 1). The hook bridging must be wired before SSE progress streaming is built.

---

### Pitfall 3: SSE Connection Leak from Swallowed CancelledError

**What goes wrong:**
When a client disconnects, `sse-starlette` raises `asyncio.CancelledError` in the generator coroutine. If the generator catches it without re-raising (common in `try/except Exception` blocks), the task group never terminates: the ping task, the disconnect listener, and the downstream SSE write loop all become zombie tasks. Over time, the server accumulates connection handles, event queues, and memory.

**Why it happens:**
`except Exception` catches `CancelledError` in Python 3.7 (it inherits from `BaseException` as of 3.8, but code written for 3.7 patterns is still common). Developers add broad exception handlers to "safely" clean up resources, not realizing they're suppressing the cancellation signal.

**How to avoid:**
Always use `try/finally` for cleanup and never use bare `except Exception` around SSE generator bodies:

```python
async def event_generator(request: Request, session_id: str):
    try:
        async for event in _stream_events(session_id):
            if await request.is_disconnected():
                break
            yield event
    except asyncio.CancelledError:
        # Clean up queues, unsubscribe session
        _cleanup_session_stream(session_id)
        raise  # ALWAYS re-raise
    finally:
        _cleanup_session_stream(session_id)
```

**Warning signs:**
- Server memory grows slowly over time even with low active user count
- `asyncio.all_tasks()` shows growing number of `sse_starlette` tasks
- CPU spikes at idle as zombie ping tasks fire continuously

**Phase to address:**
SSE streaming (Phase 2). Must be enforced before load testing; the leak is invisible at low connection counts and only surfaces under sustained use.

---

### Pitfall 4: Purge Job Deleting Files for Active Downloads

**What goes wrong:**
The APScheduler purge job queries jobs older than TTL and deletes their files. If a download is actively writing to disk when the purge runs, the file is deleted mid-write. The download worker then fails with `FileNotFoundError` or produces a zero-byte file. The job status in SQLite may be stuck in `downloading` forever.

**Why it happens:**
Purge logic typically queries by `created_at < now() - TTL` or `completed_at < now() - TTL`. If `completed_at` is NULL for an active download, range logic can accidentally include it depending on NULL handling in the SQL query. Additionally, "complete" status transitions may lag: a job is marked `completed` in the DB a moment after the file is fully written, leaving a window.

**How to avoid:**
Add an explicit `status != 'downloading'` filter to every purge query — never rely on timestamp alone:

```sql
DELETE FROM jobs
WHERE status IN ('completed', 'failed', 'cancelled')
  AND completed_at < :cutoff_ts
```

Also: before deleting a file path, verify the corresponding job row has a terminal status. Write a test that starts a slow download (sleep in a test hook) and triggers purge mid-download — verify the file is not touched.

**Warning signs:**
- Downloads succeed in tests but randomly fail in production under load
- Jobs stuck in `downloading` status in DB with no active worker
- Zero-byte files in the download directory

**Phase to address:**
Purge/session management (Phase 3). Write the status-guard test as part of the purge implementation, not after.

---

### Pitfall 5: SSE Reconnect Storm on Page Reload

**What goes wrong:**
When `EventSource` loses connection (server restart, tab backgrounded, network blip), the browser immediately retries every 3 seconds by default. If the frontend does not track `Last-Event-ID` and the server does not replay recent events, every reconnect gets a blank slate — the UI shows empty progress or "unknown" status for all in-progress downloads. Users refresh repeatedly, multiplying connections. On slow networks, multiple tabs from the same session each open their own SSE connection, exhausting the 6-connection-per-domain HTTP/1.1 limit.

**Why it happens:**
SSE reconnect is automatic and invisible — developers build the happy path but don't test what happens after a reconnect. `Last-Event-ID` support requires the server to track sent event IDs and replay them, which is non-trivial to implement late.

**How to avoid:**
- Assign an incrementing `event_id` to every SSE message from day one (can be a job-scoped counter or a global sequence).
- On reconnect, read `Last-Event-ID` header and replay all events for the session that occurred after that ID.
- Replay only the current state snapshot (latest status per job), not the full event log — prevents replay storms.
- Set `retry: 5000` in the SSE stream to slow down reconnect attempts.
- Use HTTP/2 in the Docker container (serve via `uvicorn --http h2` or behind nginx/caddy) to lift the 6-connection limit.

**Warning signs:**
- After page reload, download cards show "Unknown" or empty progress
- Browser devtools Network tab shows rapid repeated connections to `/api/events`
- Multiple tabs stop receiving updates (one tab's connection blocks others on HTTP/1.1)

**Phase to address:**
SSE streaming (Phase 2). Must be designed in from the start — adding `Last-Event-ID` replay retroactively requires event log storage.

---

### Pitfall 6: cookies.txt File Leakage via Redirect Attack (CVE-2023-35934)

**What goes wrong:**
yt-dlp passes uploaded cookies as a `Cookie` header to the file downloader for every request, including redirects. A malicious URL can redirect to an attacker-controlled host, leaking the user's session cookies for the original site. In a multi-user deployment, one user's cookies for YouTube, Vimeo, or Patreon are sent to any host that redirects the download.

**Why it happens:**
yt-dlp versions before 2023-07-06 do not scope cookies to the origin domain at the file download stage. The CVE affects youtube-dl (all versions) and all yt-dlp versions before the fix. The attack requires no exploit — it is the normal redirect behavior, just exploited.

**How to avoid:**
- Pin yt-dlp to >= 2023-07-06 (the patched version). Verify in `requirements.txt` and Docker build.
- Store cookies.txt files with per-session isolation: `data/sessions/{session_id}/cookies.txt` — never share files across sessions.
- Delete cookies.txt after the download job completes (or on session purge) so they do not persist on disk.
- Never log the cookies.txt path in any publicly readable log.
- In the security model: treat uploaded cookies as highly sensitive credentials, equivalent to a login token.

**Warning signs:**
- yt-dlp version pinned to a pre-2023-07-06 version
- cookies.txt stored in a shared directory (e.g., `/data/cookies.txt` instead of per-session paths)
- cookies.txt files not cleaned up after job completion

**Phase to address:**
Cookie auth feature (Phase 2 or whenever cookies.txt upload is implemented). Pin the version constraint immediately in Phase 1 setup.

---

### Pitfall 7: SQLite Write Contention Without WAL Mode

**What goes wrong:**
Multiple concurrent download workers write job status updates (progress %, `downloaded_bytes`, status transitions) to SQLite through aiosqlite. Without WAL mode, SQLite uses a database-level exclusive lock for every write: writer 1 locks, writers 2–N receive `SQLITE_BUSY` and fail (or retry until timeout). Under 3+ simultaneous downloads, status updates are dropped, progress bars freeze, and failed retries surface as 500 errors.

**Why it happens:**
The default SQLite journal mode (`DELETE`) serializes all writers. aiosqlite runs all operations in a background thread, but the locking is at the database layer, not the Python layer. Developers test with one download at a time and never see contention.

**How to avoid:**
Enable WAL mode at application startup before any writes:

```python
async def setup_db(conn):
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA busy_timeout=5000")
    await conn.commit()
```

`busy_timeout=5000` gives waiting writers up to 5 seconds to retry before failing, absorbing brief contention spikes. WAL allows concurrent readers alongside a single writer, which is exactly the access pattern for a download queue.

**Warning signs:**
- `sqlite3.OperationalError: database is locked` in logs under concurrent downloads
- Progress bars stall on multiple simultaneous jobs but work fine one at a time
- aiosqlite 0.20.0+ connection thread behavior change causing hangs (ensure connections are properly closed with `async with`)

**Phase to address:**
Core database setup (Phase 1). Set WAL mode in the database initialization function before any other schema work.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single shared aiosqlite connection | Simpler code | Write serialization; connection-level lock defeats WAL concurrency | Never — use a connection pool or per-request connections |
| Hardcoded yt-dlp version (`yt-dlp==2024.x.x`) | Reproducibility | Site extractors break as YouTube/Vimeo update APIs; users report "can't download X" | Acceptable for initial release; add update strategy in v1.1 |
| Storing cookies.txt in a shared `/data/cookies/` directory | Simpler path management | Session A can access session B's cookies if path logic bugs; CVE-2023-35934 surface increases | Never — always per-session isolation |
| Running yt-dlp in the FastAPI process thread pool | No IPC complexity | One hanging download blocks a thread pool slot; OOM in one download can take down the whole process | Acceptable for v1.0 at self-hosted scale; document limit |
| Not implementing `Last-Event-ID` replay at launch | Simpler SSE handler | Every reconnect shows stale/blank UI; impossible to add replay cleanly without event log | Acceptable only if SSE is designed with event IDs from day one so replay can be added later without schema migration |
| `except Exception: pass` in SSE generators | Prevents crashes | Swallows `CancelledError`, creating zombie connections | Never |
| No busy_timeout on SQLite | Fewer config lines | Silent dropped writes under concurrent downloads | Never — always set busy_timeout |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| yt-dlp + asyncio | `await loop.run_in_executor(None, ydl.download, [url])` — blocks on `ydl` shared instance | Create `YoutubeDL` inside the worker function; pass only plain data (job_id, url, opts dict) across thread boundary |
| yt-dlp progress hook + event loop | `asyncio.Queue.put_nowait(data)` directly in hook | `loop.call_soon_threadsafe(queue.put_nowait, data)` — capture loop reference before entering executor |
| yt-dlp + ProcessPoolExecutor | Pass `YoutubeDL` instance to process pool | `YoutubeDL` is not picklable (contains file handles); use `ThreadPoolExecutor` only, or create instance inside worker |
| yt-dlp info extraction + download | Call `extract_info` and `download` in same executor call | Fine for ThreadPoolExecutor; `sanitize_info()` required if result crosses process boundary |
| sse-starlette + cleanup | `except Exception as e: cleanup(); pass` | `except asyncio.CancelledError: cleanup(); raise` — never swallow CancelledError |
| aiosqlite 0.20.0+ | `connection.daemon = True` (no longer a thread) | Use `async with aiosqlite.connect()` context manager; verify connection lifecycle in migration from older versions |
| cookies.txt + yt-dlp | Global cookies file path in `YDL_OPTS` shared across requests | Per-session path: `opts["cookiefile"] = f"data/sessions/{session_id}/cookies.txt"` |
| APScheduler + FastAPI lifespan | Starting scheduler outside `@asynccontextmanager lifespan` | Initialize and start scheduler inside the lifespan context manager to ensure clean shutdown |
| Vue 3 EventSource + HTTP/1.1 | Multiple browser tabs each open SSE connection | Serve over HTTP/2 (nginx/caddy in front of uvicorn) to lift 6-connection-per-domain limit |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Progress hook writing to DB on every hook call | DB write rate exceeds 10/sec per download; downloads slow down | Throttle DB writes: update DB only when `downloaded_bytes` changes by >1MB or status changes | 3+ simultaneous downloads with fast connections |
| SSE endpoint holding open connection per download per session | Memory grows linearly with active sessions × downloads | One SSE connection per session (multiplexed events), not one per job | 10+ concurrent sessions |
| yt-dlp `extract_info` for URL auto-detection on every keystroke | Rapid URL paste triggers multiple concurrent `extract_info` calls; thread pool saturates | Debounce URL input (500ms) before triggering extraction; cancel in-flight extraction on new input | Immediately, if users paste multi-word text before settling on a URL |
| Docker COPY of entire project directory before pip install | Every code change invalidates pip cache layer | Order Dockerfile: copy `requirements.txt` first → `pip install` → copy app code | Every build during active development |
| aiosqlite without connection pool | Each request opens/closes its own connection; overhead accumulates | Use a single long-lived connection with WAL mode, or `aiosqlitepool` for high throughput | 50+ req/sec (well above self-hosted target, but good practice) |
| Purge scanning entire jobs table without index | Admin-triggered purge takes seconds to complete, blocks event loop if not offloaded | Index `(session_id, status, completed_at)` from the start | 10,000+ job rows |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Cookies.txt stored beyond job lifetime | User's site credentials persist on disk; accessible if container is compromised or volume is shared | Delete on job completion; delete on session purge; include in purge scope always |
| Admin password transmitted without HTTPS | Credentials intercepted on network | Enforce HTTPS in Docker deployment docs; add `SECURE_COOKIES=true` check in startup that warns loudly if running over HTTP |
| Session cookie without `HttpOnly` + `SameSite=Lax` | Cookie accessible via XSS; CSRF possible against download endpoints | Set `response.set_cookie("mrip_session", ..., httponly=True, samesite="lax", secure=False)` (secure=True in prod) |
| Session ID that doesn't rotate after login/admin-auth | Session fixation — attacker sets a known session ID before user authenticates | Regenerate session ID on any privilege change (session creation, admin login) |
| Admin credentials stored in plaintext in `config.yaml` | Credential leak if config volume is readable | Store bcrypt hash of admin password, not plaintext; generate a random default on first boot with forced change prompt |
| yt-dlp version < 2023-07-06 | CVE-2023-35934: cookie leak via redirect | Pin `yt-dlp>=2023.07.06` in `requirements.txt`; verify in Docker health check |
| No rate limiting on download submission | Unauthenticated user floods server with download jobs | Session-scoped queue depth limit (e.g., max 5 active jobs per session); configurable by operator |
| Shareable file URLs that expose internal paths | Directory traversal if filename is user-controlled | Serve files via a controlled endpoint (`/api/files/{job_id}/{filename}`) that resolves to an absolute path; never expose filesystem paths |
| Unsupported URL log with `report_full_url: true` default | Full URLs containing tokens/keys logged and downloadable | Default `report_full_url: false`; document clearly in config reference |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| "Download failed" with raw yt-dlp error message | Non-technical users see Python tracebacks or opaque errors | Map common yt-dlp errors to human-readable messages: "This site requires login — upload a cookies.txt file" |
| Progress bar resets to 0% on SSE reconnect | User thinks download restarted; anxiety and confusion | Restore last known progress from DB on SSE reconnect; show "Reconnecting..." state briefly |
| Session expiry with no warning | User returns after 24h to find all downloads gone | Show session TTL countdown in UI; warn at 1h remaining; extend TTL on activity |
| Format picker with raw yt-dlp format strings | "bestvideo+bestaudio/best" meaningless to non-technical users | Translate to "Best quality (auto)", "1080p MP4", "Audio only (MP3)"; show file size estimate |
| Playlist shows all items but provides no bulk action | User has to click "start" 40 times for a 40-item playlist | Bulk start at playlist level is required, not optional; implement before any UX testing |
| No feedback when URL auto-detection starts | User pastes URL, nothing visible happens for 2-3 seconds | Show spinner/skeleton immediately on valid URL detection; don't wait for `extract_info` to complete |
| Theme picker that resets on page reload | Users re-select theme every visit | Persist to `localStorage` on selection; read on mount before first render to avoid flash |

---

## "Looks Done But Isn't" Checklist

- [ ] **Download engine:** Progress hook fires and updates DB — verify that it also correctly handles `total_bytes: None` (subtitle downloads, live streams) without `TypeError`
- [ ] **SSE streaming:** Events deliver in real time on initial connection — verify they also replay correctly after a client disconnect and reconnect using `Last-Event-ID`
- [ ] **Session cookie:** Cookie is set on first visit — verify it has `HttpOnly`, `SameSite=Lax`, and the correct domain/path; verify it is NOT `Secure` in local dev (blocks HTTP) but IS `Secure` in prod
- [ ] **Cookies.txt upload:** File is accepted and passed to yt-dlp — verify the file is deleted after the job completes and is not accessible via any API endpoint
- [ ] **Purge job:** Old jobs are deleted — verify the query explicitly filters `status IN ('completed', 'failed', 'cancelled')` and does not touch `status = 'downloading'`
- [ ] **Admin auth:** Login form accepts correct credentials — verify incorrect credentials return 401 with a constant-time comparison (no timing side channel); verify default credentials force a change prompt
- [ ] **Docker image:** Image builds and runs — verify multi-platform: `docker buildx build --platform linux/amd64,linux/arm64` succeeds before tagging v1.0
- [ ] **WAL mode:** SQLite is used — verify `PRAGMA journal_mode` returns `wal` at startup in health check or startup log
- [ ] **yt-dlp version:** Library is installed — verify `yt-dlp.__version__` in `/api/health` response and confirm it is >= 2023.07.06
- [ ] **SSE connection limit:** SSE works in one tab — verify in browser devtools that multiple tabs don't hit HTTP/1.1 6-connection limit (use HTTP/2 or test connection multiplexing)

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| YoutubeDL instance sharing discovered late | MEDIUM | Audit all `YoutubeDL` instantiation sites; refactor to per-job pattern; existing jobs in-flight are safe (no state corruption once they complete) |
| CancelledError swallowing causing connection leak | LOW | Find `except Exception` blocks in SSE generators; add explicit `except asyncio.CancelledError: raise`; restart server to clear zombie connections |
| Purge bug deleted active download files | LOW | Restore file from backup if available; re-queue job; add status guard to purge query and write regression test |
| cookies.txt not being deleted (security incident) | HIGH | Audit `data/sessions/` directory for leftover cookie files; purge all; rotate any credentials whose cookies were uploaded; add deletion to job completion hook |
| SQLite locked under concurrent downloads | LOW | Enable WAL mode and `busy_timeout`; no data loss if writes are retried; restart not required |
| Docker image too large (>1GB) for arm64 users | MEDIUM | Add `.dockerignore` to exclude `node_modules`, `__pycache__`, `.git`; use multi-stage build with slim Python base; use `wader/static-ffmpeg` for static ffmpeg binary |
| yt-dlp extractor broken by upstream site change | LOW-MEDIUM | Update yt-dlp pin in `requirements.txt` and rebuild image; CI smoke test catches this before release; document manual update procedure in README |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| YoutubeDL instance not thread-safe | Phase 1: Core download engine | Test 3 simultaneous downloads; verify no cross-job progress corruption |
| Progress hook not asyncio-safe | Phase 1: Core download engine | Verify SSE receives progress while yt-dlp runs in executor thread |
| SQLite contention without WAL | Phase 1: Database setup | `PRAGMA journal_mode` returns `wal` in startup; no `SQLITE_BUSY` errors under 5 concurrent downloads |
| SSE CancelledError swallowing | Phase 2: SSE streaming | Kill a client mid-stream; verify server task count does not grow over 30 minutes |
| SSE reconnect storm / no replay | Phase 2: SSE streaming | Disconnect and reconnect; verify progress state is restored within 1 SSE cycle |
| cookies.txt leakage | Phase 2: Cookie auth feature | Verify per-session isolation paths; verify file is deleted on job completion |
| Purge deletes active downloads | Phase 3: Purge/session management | Unit test: start slow download, trigger purge, verify file untouched |
| Admin auth security gaps | Phase 3: Admin auth | Verify HttpOnly+SameSite; constant-time password comparison; default password forced change |
| Docker image bloat | Phase 4: Docker distribution | Measure image size post-build: target < 400MB compressed for amd64 |
| yt-dlp version pinning risk | Phase 1: setup + ongoing | `yt-dlp>=2023.07.06` in requirements; health endpoint reports version; CI smoke-test downloads from at least 2 sites |

---

## Sources

- [yt-dlp issue #9487: asyncio + multiprocessing / YoutubeDL not picklable](https://github.com/yt-dlp/yt-dlp/issues/9487)
- [yt-dlp issue #11022: Concurrent URL downloads not supported natively](https://github.com/yt-dlp/yt-dlp/issues/11022)
- [yt-dlp issue #5957: Progress hooks + writesubtitles / None type error + asyncio incompatibility](https://github.com/yt-dlp/yt-dlp/issues/5957)
- [yt-dlp Security Advisory GHSA-v8mc-9377-rwjj: Cookie leak via redirect (CVE-2023-35934)](https://github.com/yt-dlp/yt-dlp/security/advisories/GHSA-v8mc-9377-rwjj)
- [sse-starlette: Client Disconnection Detection — CancelledError must be re-raised](https://deepwiki.com/sysid/sse-starlette/3.5-client-disconnection-detection)
- [MDN: Using server-sent events — reconnect and Last-Event-ID behavior](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [SSE production pitfalls: proxy buffering, reconnect, connection limits](https://dev.to/miketalbot/server-sent-events-are-still-not-production-ready-after-a-decade-a-lesson-for-me-a-warning-for-you-2gie)
- [Concurrency challenges in SQLite — write contention and WAL mode](https://www.slingacademy.com/article/concurrency-challenges-in-sqlite-and-how-to-overcome-them/)
- [aiosqlite 0.22.0 behavior change: connection is no longer a thread](https://github.com/sqlalchemy/sqlalchemy/issues/13039)
- [FastAPI SSE disconnect detection discussion](https://github.com/fastapi/fastapi/discussions/9398)
- [Browser connection limits for SSE: 6 per domain on HTTP/1.1](https://www.javascriptroom.com/blog/server-sent-events-and-browser-limits/)
- [wader/static-ffmpeg: multi-arch static ffmpeg binaries for Docker](https://github.com/wader/static-ffmpeg)

---
*Pitfalls research for: yt-dlp web frontend (media.rip v1.0)*
*Researched: 2026-03-17*
