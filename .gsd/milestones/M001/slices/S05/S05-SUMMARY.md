---
id: S05
milestone: M001
status: complete
tasks_completed: 5
tasks_total: 5
test_count_backend: 182
test_count_frontend: 29
started_at: 2026-03-18
completed_at: 2026-03-18
---

# S05: Theme System — Summary

**Delivered the CSS variable contract as a stable public API, 3 built-in themes (cyberpunk, dark, light), a theme picker in the header, and a backend custom theme loader with API. 182 backend tests + 29 frontend tests pass.**

## What Was Built

### CSS Variable Contract (T01)
- `base.css` expanded to 50+ documented tokens across 12 categories
- Token groups: background/surface, text, accent, status, typography, font sizes, spacing, radius, shadows, effects, layout, transitions
- Deprecated aliases for S03 compat (`--header-height` → `--layout-header-height`)
- Body `::before`/`::after` pseudo-elements for scanline + grid overlays (controlled by `--effect-*` tokens)
- Full header documentation block explaining custom theme creation

### Cyberpunk Theme (T01)
- Flagship theme: #00a8ff electric blue + #ff6b2b molten orange
- JetBrains Mono for `--font-display`
- Scanline overlay (CRT effect), grid background, glow on focus
- Heavily commented as documentation for custom theme authors

### Dark Theme (T02)
- Neutral grays (#121212 base), purple accent (#a78bfa)
- All effects disabled (`--effect-scanlines: none`, etc.)
- System font stack throughout

### Light Theme (T02)
- Inverted palette (#f5f5f7 bg, #1a1a2e text)
- Blue accent (#2563eb) for light-background contrast
- Soft shadows, no effects

### Theme Store + Picker (T03)
- Pinia store: `init()` reads localStorage, `setTheme()` applies `data-theme` attribute
- Default: cyberpunk. Persists selection via `mrip-theme` localStorage key
- `loadCustomThemes()` fetches backend manifest for drop-in themes
- Custom CSS injection via dynamic `<style>` elements
- ThemePicker component: preview dots with theme accent colors, mobile-responsive
- 8 vitest tests covering init, save, restore, invalid fallback, unknown theme rejection

### Backend Theme Loader + API (T04)
- `scan_themes()`: discovers theme packs (metadata.json + theme.css) from directory
- `get_theme_css()`: reads CSS with path traversal protection
- Handles: missing metadata, missing CSS, invalid JSON, preview.png detection
- API: `GET /api/themes` (manifest), `GET /api/themes/{id}/theme.css` (CSS)
- `themes_dir` config field (default: `./themes`)
- 18 tests: 9 scanner, 3 CSS retrieval, 6 API endpoint tests

## Requirements Addressed

| Req | Description | Status |
|-----|------------|--------|
| R010 | Three built-in themes | Proven — cyberpunk, dark, light all define full token set |
| R011 | Drop-in custom theme system | Proven — scanner + API + frontend loader chain works |
| R012 | CSS variable contract | Proven — 50+ tokens documented in base.css as stable API |

## Verification

- `pytest tests/ -v` — 182/182 passed (18 new)
- `npx vitest run` — 29/29 passed (8 new)
- `vue-tsc --noEmit` — zero type errors
- `npm run build` — clean with code splitting

## Files Created/Modified

- `frontend/src/assets/base.css` — full variable contract (complete rewrite)
- `frontend/src/themes/cyberpunk.css` — cyberpunk theme
- `frontend/src/themes/dark.css` — dark theme
- `frontend/src/themes/light.css` — light theme
- `frontend/src/stores/theme.ts` — theme Pinia store
- `frontend/src/components/ThemePicker.vue` — theme picker
- `frontend/src/components/AppHeader.vue` — added ThemePicker + --font-display
- `frontend/src/App.vue` — theme imports + init
- `frontend/src/tests/stores/theme.test.ts` — 8 theme store tests
- `backend/app/core/config.py` — added themes_dir field
- `backend/app/services/theme_loader.py` — theme scanner
- `backend/app/routers/themes.py` — theme API
- `backend/app/main.py` — registered themes router
- `backend/tests/test_themes.py` — 18 theme tests
- `backend/tests/conftest.py` — registered themes router
