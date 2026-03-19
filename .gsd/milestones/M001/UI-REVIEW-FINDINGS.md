# UI/UX Review Findings — M001 Post-Completion Walkthrough

**Date:** 2026-03-18
**Participants:** User (product owner) + GSD (agent)
**Method:** Live app walkthrough at localhost:5173, guided interview

---

## Summary

M001 is functionally complete (208 tests, all slices done) but the UI needs a significant UX pass before v0.1.0 tag. The app works but doesn't feel polished — unclear affordances, missing user flows, and several functional gaps identified during live testing.

---

## Findings

### 1. Welcome / Informational Block
**Priority: HIGH**
- Add a configurable welcome message block above the URL input
- Default text: "Paste any video or audio URL. We rip it, you download it. No accounts, no tracking. Files auto-purge after 24h." (or similar)
- Admin-configurable from admin panel (can override text or hide entirely)
- Should look clean and integrated, not a banner bar — a styled text block above the input area

### 2. Theme System Rework
**Priority: HIGH**
- **Current:** 3 radio-button dots (Cyberpunk/Dark/Light) in header
- **Target:** Admin sets the theme (cyberpunk default). Users get a sun/moon toggle for light ↔ dark variant only
- Backend implication: each theme needs a light variant, or the light mode is a modifier on any theme
- The "dark" and "light" themes become _modes_ rather than separate themes
- Theme picker (full theme selection) moves to admin panel

### 3. SSE Connection Indicator (Green Dot)
**Priority: LOW**
- Currently unlabeled, looks like a 4th theme option
- **Decision:** Hide in production. Keep available for debug/development mode only

### 4. Remove ADMIN Tab from Main Nav
**Priority: HIGH**
- Admin panel accessible only via `/admin` URL — no visual link from main app
- Security by obscurity layer (auth still required, but no invitation to probe)
- Consequence: since ADMIN tab is removed, the DOWNLOADS tab is also unnecessary (only one view)
- Remove the entire DOWNLOADS/ADMIN tab bar

### 5. Footer with Version Info
**Priority: MEDIUM**
- Centered footer showing: `media.rip() v0.1.0 | yt-dlp 2026.03.17 | GitHub`
- Pipe-delimited, clean typography
- GitHub link goes to repo
- Version info pulled from health endpoint data

### 6. Download Flow Rework
**Priority: HIGH**
- **Current:** URL input → "Get Formats" button → format picker appears → "Download" button
- **Target:** URL input → "Download" button (auto-best quality) with optional format picker as expandable section
- Add audio/video toggle glyph — clean, intuitive icon to switch between audio-only and video download
- Format picker becomes "Advanced" or expandable area, not the primary flow
- Must handle playlist URLs intuitively — multi-file links should dynamically show appropriate UI

### 7. Download Queue → Table-Style Display
**Priority: HIGH**
- **Current:** Card-based list with title, progress bar, speed, ETA, cancel
- **Target:** Table-like display that maintains the card aesthetic (not Excel — keep the cyberpunk vibes)
- Columns to add: started timestamp, file size (if available)
- Admin-configurable visible columns (enable/disable from admin panel)
- Sorting: by ETA, % complete, alphabetical, download status
- Keep filter tabs (All/Active/Completed/Failed) with counts

### 8. Download Item Actions (Glyphs, Not Words)
**Priority: HIGH**
- Use intuitive glyphs/icons instead of text labels
- **Active downloads:** Cancel (✕)
- **Completed downloads:** Download to local machine (↓), Copy share link (🔗), Clear from queue (✕)
- Cancel and clear should use the same position/interface pattern
- Single-click copy for share link

### 9. Cancel Download Bug
**Priority: HIGH (Functional Bug)**
- Cancel button (✕) on active downloads does not work — clicking does not cancel the download
- Network logs show no request is sent when clicking cancel
- Likely a click handler or z-index/event propagation issue in the grid layout
- Must investigate and fix

### 10. Session Management UI Missing
**Priority: MEDIUM**
- R017 (Session export/import) has no visible UI elements
- No export, import, or delete session buttons anywhere in the app
- Needs UI surface — likely in a settings area or as part of the header/footer

### 11. Admin Panel — Deferred to Next Review
**Priority: MEDIUM (deferred)**
- Admin panel needs review after UI changes are applied
- Current state: login form shows even when admin is disabled (no credentials configured)
- New admin features needed: welcome message editor, theme selection, column visibility toggles
- Default credentials / first-boot setup flow needs work
- Will review in next walkthrough round

### 12. Mobile View
**Priority: MEDIUM**
- Bottom tab bar (SUBMIT/QUEUE) appears at <768px
- If table-style download display makes mobile too complex, recommend most elegant fallback
- Needs reassessment after desktop changes land

---

## Bugs Found

| # | Description | Severity |
|---|---|---|
| B1 | Cancel button on active downloads doesn't fire network request | High |
| B2 | Admin login form shown when admin is disabled (no credentials configured) | Medium |
| B3 | Format picker only shows "Completed" text match from filter tab label (false text match, cosmetic) | Low |

---

## Proposed Execution Order

1. **Cancel bug fix** (B1) — functional blocker
2. **Header rework** — remove tabs, add welcome message block, simplify theme to sun/moon toggle
3. **Footer** — version info display
4. **Download flow** — quick download + optional format picker, audio/video toggle
5. **Queue table redesign** — table-style with sorting, timestamps, file size
6. **Action glyphs** — download/copy/clear icons on completed items
7. **Admin panel improvements** — welcome message editor, theme selection, column config
8. **Session management UI** — export/import/delete
9. **Mobile reassessment** — after desktop changes

---

## Out of Scope for This Pass

- Full admin panel redesign (deferred to next review round)
- Playlist-specific UI (parent/child collapse) — will be designed during execution if time permits
- Visual polish / animation refinement
