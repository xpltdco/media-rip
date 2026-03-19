# S02: Download Flow + Queue Redesign

**Goal:** Simplify the download flow to a single "Download" button (with optional format picker), add an audio/video quick-toggle, convert the queue from cards to a sortable table, and add action glyphs (download file, copy link, clear) for completed items.
**Demo:** User pastes URL → clicks "Download" → item appears in the table queue → completes → user clicks download icon to save file or copy icon to copy the download link. Table columns are sortable by status, name, progress, ETA.

## Must-Haves

- "Download" is the primary button (not "Get Formats") — one-click download with best quality
- Optional format picker accessible via a secondary "⚙ Options" toggle
- Audio/video quick-toggle (video default) that sets appropriate format flags
- Queue rendered as a styled table with columns: Name, Status, Progress, Speed, ETA, Actions
- Table headers are clickable to sort (ascending/descending)
- Completed items show download (⬇), copy-link (🔗), clear (✕) action icons
- Active items show cancel (✕) icon
- Failed items show error message and clear (✕) icon
- Mobile: table degrades gracefully (horizontal scroll or card fallback below 640px)

## Verification

- `cd frontend && npx vitest run` — all tests pass
- `cd backend && source .venv/Scripts/activate && python -m pytest tests/ -q -m "not integration"` — no regressions
- Browser: paste URL → click Download → job appears in table → progresses → completes
- Browser: click download icon on completed item → file downloads
- Browser: click copy-link icon → link copied (or tooltip confirms)
- Browser: sort table by each column header
- Browser: mobile viewport shows readable queue

## Tasks

- [x] **T01: Rework UrlInput — Download-first flow with collapsible options** `est:45m`
  - Why: Current flow forces "Get Formats" before downloading. Most users just want to paste and go.
  - Files: `frontend/src/components/UrlInput.vue`
  - Do: Make "Download" the primary action button. Add a "⚙" toggle button that expands/collapses the format picker section below. Add audio/video toggle pills (Video | Audio) that set a `mediaType` ref. When `mediaType` is "audio", pass `quality: "bestaudio"` to the submit payload. When format picker is open and user selects a format, use that instead. Keep the paste-to-auto-extract behavior but make it extract silently in the background (populate formats without showing picker). "Download" works immediately with or without format selection.
  - Verify: Paste URL → click Download → job starts without format selection. Toggle audio → Download → job starts with audio quality. Click ⚙ → format picker opens → select format → Download.
  - Done when: Download is the primary one-click action, format picker is optional

- [x] **T02: Convert queue to sortable table** `est:60m`
  - Why: Card-based queue doesn't scan well with many items. Table with sorting is standard for download managers.
  - Files: `frontend/src/components/DownloadQueue.vue`, `frontend/src/components/DownloadTable.vue` (new), `frontend/src/components/DownloadItem.vue` (remove or repurpose)
  - Do: Create DownloadTable component with `<table>` markup. Columns: Name (truncated, title=full URL), Status (badge), Progress (inline bar), Speed, ETA, Actions. Add a `sortBy` ref and `sortDir` ref. Clicking a column header toggles sort. Computed `sortedJobs` applies sort. Keep the filter buttons (All/Active/Completed/Failed) above the table. Style the table with theme CSS variables. On mobile (< 640px), hide Speed and ETA columns, or use a responsive approach.
  - Verify: Jobs render as table rows. Click column headers to sort. Filter buttons still work. Mobile view is usable.
  - Done when: Queue is a sortable table with all columns rendering correctly

- [x] **T03: Action glyphs for completed/active/failed items** `est:30m`
  - Why: Users need to download completed files, copy links, and clear items from the queue.
  - Files: `frontend/src/components/DownloadTable.vue`, `frontend/src/stores/downloads.ts`, `frontend/src/api/client.ts`
  - Do: Add action icons in the Actions column. Completed: download file (anchor to `/api/downloads/{filename}`), copy download link (clipboard API), clear from queue (DELETE + remove from store). Active: cancel (existing logic). Failed: clear from queue. Style icons as small inline buttons with hover effects. Add `clearJob(id)` to downloads store that calls DELETE and removes locally.
  - Verify: Click download icon on completed item → browser downloads file. Click copy icon → link in clipboard. Click clear → item removed. Click cancel on active → cancelled.
  - Done when: All action icons work for each status type

- [x] **T04: Update tests** `est:20m`
  - Why: New components and store changes need test coverage. Old DownloadItem tests may need removal/update.
  - Files: `frontend/src/tests/stores/downloads.test.ts`, `frontend/src/tests/components/` (if any)
  - Do: Add tests for the new sort logic (sortBy, sortDir). Test clearJob action in downloads store. Verify existing download store tests still pass. Run full frontend and backend test suites.
  - Verify: `npx vitest run` all pass, `python -m pytest tests/ -q -m "not integration"` all pass
  - Done when: All tests green, no regressions

## Files Likely Touched

- `frontend/src/components/UrlInput.vue` (reworked)
- `frontend/src/components/DownloadQueue.vue` (reworked to use table)
- `frontend/src/components/DownloadTable.vue` (new)
- `frontend/src/components/DownloadItem.vue` (may be removed — logic moves to table rows)
- `frontend/src/components/FormatPicker.vue` (minor — toggled visibility)
- `frontend/src/components/ProgressBar.vue` (minor — may need inline variant)
- `frontend/src/stores/downloads.ts` (add clearJob, sort helpers)
- `frontend/src/api/client.ts` (no changes expected — DELETE already exists)
- `frontend/src/api/types.ts` (no changes expected)
