# S03: Mobile + Integration Polish

**Goal:** Ensure mobile view works cleanly with the new table-based queue, add a welcome message editor in the admin panel, and verify all flows end-to-end.
**Demo:** Mobile user can submit downloads and view the queue table. Admin can edit the welcome message text from the admin panel Settings tab. All navigation flows work.

## Must-Haves

- Mobile queue table is usable (tested at 390px viewport)
- Admin panel has a "Settings" tab with welcome message text editor
- Admin settings tab saves welcome_message via backend API
- All end-to-end flows verified in browser (desktop + mobile)
- No test regressions

## Verification

- `cd frontend && npx vitest run` — all tests pass
- `cd backend && source .venv/Scripts/activate && python -m pytest tests/ -q -m "not integration"` — no regressions
- Browser (desktop): full download lifecycle works
- Browser (mobile 390px): submit + queue table renders, actions work
- Browser: admin panel Settings tab → edit welcome message → saves

## Tasks

- [x] **T01: Admin welcome message editor** `est:30m`
  - Why: Operators need to customize the welcome message without editing config files
  - Files: `frontend/src/components/AdminPanel.vue`, `frontend/src/stores/admin.ts`, `backend/app/routers/admin.py`
  - Do: Add a "Settings" tab to admin panel with a textarea for welcome message. Load current value from `/api/config/public`. Add PUT `/api/admin/settings` endpoint that updates the config's welcome_message in memory (runtime override — persisting to YAML is out of scope for this milestone). Add `updateSettings(data)` to admin store. Show save confirmation.
  - Verify: Login to admin → Settings tab → edit message → save → reload main page → new message visible
  - Done when: Welcome message is editable from admin panel

- [x] **T02: Mobile polish and end-to-end verification** `est:30m`
  - Why: Table-based queue may have issues at narrow viewports. Need to verify all flows.
  - Files: Various frontend components (fixes only as needed)
  - Do: Test at 390px viewport width. Fix any overflow, truncation, or touch target issues. Verify: submit download, view queue, cancel download, completed actions, dark/light toggle, footer. Fix any issues found.
  - Verify: All flows work at mobile viewport. No horizontal overflow on queue table.
  - Done when: Mobile experience is functional and clean

- [x] **T03: Final test run and cleanup** `est:15m`
  - Why: Ensure no regressions across the full M002 milestone
  - Files: Test files, cleanup any unused components
  - Do: Run full test suites. Remove ThemePicker.vue if no longer imported. Remove DownloadItem.vue if no longer imported. Clean up any dead imports.
  - Verify: All tests pass, no unused component files, no dead imports
  - Done when: Clean codebase, all tests green

## Files Likely Touched

- `frontend/src/components/AdminPanel.vue` (add Settings tab)
- `frontend/src/stores/admin.ts` (add updateSettings)
- `backend/app/routers/admin.py` (add PUT /admin/settings)
- Various frontend components (mobile fixes as needed)
- `frontend/src/components/ThemePicker.vue` (remove if unused)
- `frontend/src/components/DownloadItem.vue` (remove if unused)
