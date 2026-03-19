# S01: Bug Fixes + Header/Footer Rework

**Goal:** Fix the cancel download bug, rework the header (remove tabs, add welcome message, simplify theme toggle to sun/moon), add version footer, and hide the SSE status dot in production.
**Demo:** User sees a clean header with logo + sun/moon toggle, welcome message block above URL input, version footer at bottom. Cancel button on active downloads fires the DELETE request and removes the item.

## Must-Haves

- Cancel button on active downloads actually cancels (fires DELETE request, item removed)
- Header has no DOWNLOADS/ADMIN tabs
- Sun/moon toggle replaces 3-theme picker (switches current theme between its dark and light variant)
- Welcome message block above URL input with sensible default text
- Footer shows app version, yt-dlp version, GitHub link (pipe-delimited)
- SSE green dot hidden (dev-mode only)
- Admin panel still accessible at `/admin` but no nav link from main app

## Verification

- `cd frontend && npx vitest run` — all tests pass (update theme tests for new toggle behavior)
- `cd backend && python -m pytest tests/ -q -m "not integration"` — no regressions
- Browser: cancel button on active download fires network request and item disappears
- Browser: header shows logo + sun/moon toggle, no tabs, no green dot
- Browser: welcome message visible above URL input
- Browser: footer visible with version info
- Browser: `/admin` still loads the login form

## Tasks

- [x] **T01: Fix cancel download bug** `est:30m`
  - Why: Cancel button clicks don't fire a network request — functional blocker
  - Files: `frontend/src/components/DownloadItem.vue`, `frontend/src/components/DownloadQueue.vue`
  - Do: Investigate why the cancel button click doesn't reach the handler. Check for event propagation issues in the grid layout, z-index conflicts, or pointer-events CSS. Verify the DELETE endpoint works via curl. Fix the event wiring. Add `@click.stop` if needed.
  - Verify: Start a download, click cancel, confirm DELETE request in network tab, item disappears from queue
  - Done when: Cancel button reliably cancels active downloads

- [x] **T02: Rework header — remove tabs, simplify theme toggle** `est:45m`
  - Why: DOWNLOADS/ADMIN tabs are unnecessary (admin moves to URL-only access). Theme picker needs to be a simple sun/moon toggle instead of 3 radio buttons.
  - Files: `frontend/src/components/AppHeader.vue`, `frontend/src/components/ThemePicker.vue`, `frontend/src/stores/theme.ts`, `frontend/src/components/AppLayout.vue`, `frontend/src/App.vue`, `frontend/src/router.ts`
  - Do: Remove the nav tab bar from AppLayout/MainView. Replace ThemePicker with a DarkModeToggle component — a sun/moon icon button that toggles between the current theme's dark and light variants. For cyberpunk, "light" mode uses the light theme CSS. Remove the SSE status dot from the header (or gate behind a `DEV` flag). Keep `/admin` route in router but remove any nav link to it. Update theme store: `toggleDarkMode()` method that swaps between `cyberpunk`↔`light` (or `dark`↔`light`).
  - Verify: Header shows only logo + sun/moon toggle. Clicking toggle switches between dark/light appearance. No tabs visible. Green dot hidden.
  - Done when: Header is clean with logo left, sun/moon toggle right, nothing else

- [x] **T03: Add welcome message block** `est:30m`
  - Why: Users need context about what the app does when they first land
  - Files: `frontend/src/components/WelcomeMessage.vue` (new), `frontend/src/components/MainView.vue`, `backend/app/routers/system.py`
  - Do: Create WelcomeMessage component that displays a styled text block above the URL input. Default text: "Paste any video or audio URL. We rip it, you download it. No accounts, no tracking." Make it read from the public config endpoint. Add `welcome_message` field to the public config response (with default value). Style it to integrate cleanly — not a banner, but a subtle informational block with proper typography.
  - Verify: Welcome message visible above URL input on page load. Text matches default or config override.
  - Done when: Welcome message block renders with default text, reads from config

- [x] **T04: Add version footer** `est:20m`
  - Why: Users/operators want to see app version, yt-dlp version, and find the GitHub repo
  - Files: `frontend/src/components/AppFooter.vue` (new), `frontend/src/App.vue`
  - Do: Create AppFooter component. Fetch version data from `/api/health` on mount. Display: `media.rip() v0.1.0 | yt-dlp 2026.03.17 | GitHub`. GitHub links to repo. Pipe-delimited, centered, subtle typography matching the theme. Place it at the bottom of the page (not fixed — scrolls with content).
  - Verify: Footer visible at bottom of page with correct version numbers. GitHub link works.
  - Done when: Footer renders with live version data from health endpoint

- [x] **T05: Update tests and verify** `est:20m`
  - Why: Theme store tests need updating for the new toggle behavior. Ensure no regressions.
  - Files: `frontend/src/tests/stores/theme.test.ts`, `frontend/src/tests/stores/downloads.test.ts`
  - Do: Update theme store tests to reflect new `toggleDarkMode()` method. Remove tests for 3-theme picker behavior. Add test for dark/light toggle. Run full test suites for both frontend and backend.
  - Verify: `npx vitest run` all pass, `python -m pytest tests/ -q -m "not integration"` all pass
  - Done when: All tests green, no regressions

## Files Likely Touched

- `frontend/src/components/AppHeader.vue`
- `frontend/src/components/ThemePicker.vue` (replaced by DarkModeToggle)
- `frontend/src/components/DarkModeToggle.vue` (new)
- `frontend/src/components/WelcomeMessage.vue` (new)
- `frontend/src/components/AppFooter.vue` (new)
- `frontend/src/components/AppLayout.vue`
- `frontend/src/components/MainView.vue`
- `frontend/src/App.vue`
- `frontend/src/stores/theme.ts`
- `frontend/src/tests/stores/theme.test.ts`
- `backend/app/routers/system.py`
- `backend/app/core/config.py`
