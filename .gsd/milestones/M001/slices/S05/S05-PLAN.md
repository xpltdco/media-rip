# S05: Theme System

**Goal:** Establish the CSS variable contract as a stable public API, deliver 3 built-in themes (cyberpunk default, dark, light), add a theme picker to the UI, and enable drop-in custom themes via volume mount with backend scanning + manifest API.
**Demo:** Change theme in the picker → all colors/fonts/effects update instantly. Drop a custom theme folder into /themes → restart → appears in picker → applies correctly. Built-in themes are heavily commented as documentation for custom theme authors.

## Must-Haves

- CSS variable contract documented in base.css with all tokens components reference
- Cyberpunk theme: #00a8ff/#ff6b2b accent, JetBrains Mono, scanline overlay, grid background
- Dark theme: clean neutral palette, no effects
- Light theme: inverted for daylight use
- Theme picker in header that persists selection in localStorage
- Backend theme loader: scans /themes volume, serves manifest + CSS
- Custom theme pack structure: theme.css + metadata.json + optional preview.png
- Built-in themes heavily commented for custom theme authors

## Proof Level

- This slice proves: integration (theme switching end-to-end, custom theme loading)
- Real runtime required: yes (visual verification)
- Human/UAT required: yes (theme visual quality)

## Verification

- `cd frontend && npx vitest run` — theme store tests pass
- `cd backend && .venv/Scripts/python -m pytest tests/test_themes.py -v` — theme loader tests pass
- `cd frontend && npx vue-tsc --noEmit && npm run build` — clean build
- Browser verify: switch between all 3 themes, confirm visual changes
- Browser verify: cyberpunk has scanline/grid effects

## Tasks

- [x] **T01: CSS variable contract + cyberpunk theme** `est:45m`
  - Why: Establishes the stable public API for all themes. Cyberpunk is the default and flagship.
  - Files: `frontend/src/assets/base.css`, `frontend/src/themes/cyberpunk.css`
  - Do: Expand base.css with full token set (colors, typography, spacing, borders, shadows, effects, layout). Create cyberpunk.css with scanline/grid overlays, JetBrains Mono import, orange+blue accent palette. Document every token group with comments explaining what each controls. Add CSS class application mechanism (`data-theme` on html element).
  - Verify: Build passes, tokens documented
  - Done when: base.css is the complete variable contract, cyberpunk.css overrides all tokens

- [x] **T02: Dark + light themes** `est:20m`
  - Why: Two clean alternatives to cyberpunk. Proves the variable contract works for different palettes.
  - Files: `frontend/src/themes/dark.css`, `frontend/src/themes/light.css`
  - Do: Dark theme: neutral grays, no effects, same font stack. Light theme: inverted bg/text, soft shadows, muted accent. Both heavily commented.
  - Verify: Build passes
  - Done when: Both themes define all contract tokens

- [x] **T03: Theme store + picker component** `est:30m`
  - Why: Users need to switch themes. Picker persists selection across sessions.
  - Files: `frontend/src/stores/theme.ts`, `frontend/src/components/ThemePicker.vue`, `frontend/src/App.vue`
  - Do: Pinia store: loads from localStorage, sets `data-theme` attribute on `<html>`, lists available themes. ThemePicker: dropdown/button group in header. Import all 3 built-in CSS files. Write vitest tests for theme store.
  - Verify: `npx vitest run` — theme store tests pass
  - Done when: Theme switches apply instantly, selection persists across page reload

- [x] **T04: Backend theme loader + API** `est:30m`
  - Why: Custom themes need to be discovered from /themes volume and served to the frontend.
  - Files: `backend/app/services/theme_loader.py`, `backend/app/routers/themes.py`, `backend/app/main.py`
  - Do: ThemeLoader: scans a directory for theme packs (theme.css + metadata.json). Router: GET /api/themes returns manifest, GET /api/themes/{name}/theme.css serves CSS. Register in main.py. Write pytest tests.
  - Verify: `pytest tests/test_themes.py -v` — passes
  - Done when: Custom theme folders are discovered and served via API

- [x] **T05: Integration + visual verification** `est:20m`
  - Why: End-to-end proof that theme switching works with real UI, including custom theme loading.
  - Files: `frontend/src/stores/theme.ts`, `frontend/src/App.vue`
  - Do: Connect theme store to backend manifest for custom themes. Verify all 3 built-in themes in browser. Verify cyberpunk effects (scanlines, grid). Full regression: all tests pass.
  - Verify: Browser visual check, `pytest tests/ -v`, `npx vitest run`, `npm run build`
  - Done when: All 3 themes render correctly in browser, build clean, all tests pass

## Files Likely Touched

- `frontend/src/assets/base.css`
- `frontend/src/themes/cyberpunk.css`
- `frontend/src/themes/dark.css`
- `frontend/src/themes/light.css`
- `frontend/src/stores/theme.ts`
- `frontend/src/components/ThemePicker.vue`
- `frontend/src/components/AppHeader.vue`
- `frontend/src/App.vue`
- `backend/app/services/theme_loader.py`
- `backend/app/routers/themes.py`
- `backend/app/main.py`
- `backend/tests/test_themes.py`
- `frontend/src/tests/stores/theme.test.ts`
