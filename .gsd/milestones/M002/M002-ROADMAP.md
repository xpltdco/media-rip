# M002: UI/UX Polish — Ship-Ready Frontend

**Vision:** Transform the functional-but-rough v1 frontend into a polished, intuitive experience. Fix functional bugs, rework the download flow, redesign the queue display, and clean up navigation so the app feels intentional rather than assembled.

## Success Criteria

- User can paste a URL and download with one click (best quality auto-selected)
- Completed downloads show download/copy-link/clear actions as intuitive glyphs
- Cancel button on active downloads actually cancels
- Download queue displays as a styled table with sorting by ETA, %, name, status
- Welcome message is visible above the URL input and configurable by admin
- Theme toggle is a sun/moon icon (light/dark mode), not a 3-option picker
- Admin panel is only accessible at `/admin` — no link from main app
- Footer shows app version, yt-dlp version, and GitHub link
- Mobile view remains functional after desktop changes

## Key Risks / Unknowns

- Cancel bug root cause — could be event propagation, could be deeper API issue
- Table-style queue on mobile — may need a different layout strategy below 768px
- Theme light/dark variant architecture — each theme needs a light mode modifier

## Proof Strategy

- Cancel bug → retire in S01 by verifying network request fires and download stops
- Table mobile layout → retire in S03 by visual verification on mobile viewport

## Verification Classes

- Contract verification: frontend tests (vitest), backend tests (pytest) for any API changes
- Integration verification: live browser verification of all changed UI flows
- Operational verification: none (no backend architecture changes)
- UAT / human verification: walkthrough with user after S03

## Milestone Definition of Done

This milestone is complete only when all are true:

- All UI changes are implemented and visually verified in browser
- Cancel downloads works end-to-end
- Download flow (paste → download → completed → download file) works
- Mobile view is functional
- Frontend tests pass
- Backend tests pass (no regressions)
- User walkthrough confirms satisfaction

## Requirement Coverage

- Covers: R005 (queue view), R013 (mobile responsive), R018 (link sharing)
- Partially covers: R010 (themes — light/dark toggle rework), R014 (admin panel — welcome message config)
- Leaves for later: R017 (session export/import UI), R011 (custom theme system — admin theme picker)
- Orphan risks: none

## Slices

- [x] **S01: Bug Fixes + Header/Footer Rework** `risk:high` `depends:[]`
  > After this: Cancel button works, header has no tabs, footer shows version info, welcome message block is visible with default text, theme is sun/moon toggle

- [x] **S02: Download Flow + Queue Redesign** `risk:medium` `depends:[S01]`
  > After this: Single "Download" button with optional format picker, audio/video toggle, queue displays as styled table with sorting, completed items show download/copy/clear glyphs

- [ ] **S03: Mobile + Integration Polish** `risk:low` `depends:[S02]`
  > After this: Mobile layout works with new table design, admin welcome message editor functional, all flows verified end-to-end

## Boundary Map

### S01 → S02

Produces:
- Simplified header component (no tabs, sun/moon toggle)
- Footer component with version data from `/api/health`
- Welcome message block component reading from `/api/config/public` 
- Working cancel endpoint (DELETE `/api/downloads/{id}` verified)
- `--color-bg-light` / `--color-text-light` CSS variable pattern for light mode

Consumes:
- nothing (first slice)

### S02 → S03

Produces:
- Refactored UrlInput with "Download" primary action + collapsible format picker
- Audio/video toggle component
- Table-based DownloadQueue with sortable columns
- Action glyph components (download, copy-link, clear)

Consumes:
- S01 header/footer/welcome components stable
- S01 cancel bug fixed
