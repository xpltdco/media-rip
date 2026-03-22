/**
 * Theme Pinia store — manages theme selection and application.
 *
 * Admin sets: which dark theme, which light theme, and default mode (dark/light).
 * Visitors: see the admin default, can toggle dark/light via header icon.
 * Visitor preference stored in cookie (session-scoped persistence).
 *
 * Built-in themes: 5 dark + 4 light = 9 total.
 * Custom themes: loaded via /api/themes manifest at runtime.
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useConfigStore } from './config'

export interface ThemeMeta {
  id: string
  name: string
  author?: string
  description?: string
  builtin: boolean
  variant: 'dark' | 'light'
}

const COOKIE_KEY = 'mrip-mode'

const BUILTIN_THEMES: ThemeMeta[] = [
  // Dark themes
  { id: 'cyberpunk', name: 'Cyberpunk', author: 'media.rip()', description: 'Electric blue + orange, scanlines, grid overlay', builtin: true, variant: 'dark' },
  { id: 'dark', name: 'Dark', author: 'media.rip()', description: 'Clean neutral dark theme', builtin: true, variant: 'dark' },
  { id: 'midnight', name: 'Midnight', author: 'media.rip()', description: 'Ultra-minimal, near-black, zero effects', builtin: true, variant: 'dark' },
  { id: 'hacker', name: 'Hacker', author: 'media.rip()', description: 'Green-on-black terminal aesthetic', builtin: true, variant: 'dark' },
  { id: 'neon', name: 'Neon', author: 'media.rip()', description: 'Hot pink + cyan on deep purple, synthwave vibes', builtin: true, variant: 'dark' },
  // Light themes
  { id: 'light', name: 'Light', author: 'media.rip()', description: 'Clean light theme for daylight use', builtin: true, variant: 'light' },
  { id: 'paper', name: 'Paper', author: 'media.rip()', description: 'Warm cream and sepia, book-like', builtin: true, variant: 'light' },
  { id: 'arctic', name: 'Arctic', author: 'media.rip()', description: 'Cool whites and icy blues, crisp and sharp', builtin: true, variant: 'light' },
  { id: 'solarized', name: 'Solarized', author: 'media.rip()', description: 'Solarized Light — easy on the eyes', builtin: true, variant: 'light' },
]

export const useThemeStore = defineStore('theme', () => {
  const currentTheme = ref('cyberpunk')
  const currentMode = ref<'dark' | 'light'>('dark')
  const customThemes = ref<ThemeMeta[]>([])
  const customThemeCSS = ref<Map<string, string>>(new Map())

  // Admin-configured theme pair (loaded from public config)
  const adminDarkTheme = ref('cyberpunk')
  const adminLightTheme = ref('light')
  const adminDefaultMode = ref<'dark' | 'light'>('dark')

  const isDark = computed(() => currentMode.value === 'dark')

  const allThemes = computed<ThemeMeta[]>(() => [
    ...BUILTIN_THEMES,
    ...customThemes.value,
  ])

  const darkThemes = computed(() => allThemes.value.filter(t => t.variant === 'dark'))
  const lightThemes = computed(() => allThemes.value.filter(t => t.variant === 'light'))

  const currentMeta = computed<ThemeMeta | undefined>(() =>
    allThemes.value.find(t => t.id === currentTheme.value)
  )

  /**
   * Initialize — reads admin config, then checks for visitor cookie override.
   */
  function init(): void {
    const configStore = useConfigStore()
    const cfg = configStore.config

    if (cfg) {
      adminDarkTheme.value = cfg.theme_dark || 'cyberpunk'
      adminLightTheme.value = cfg.theme_light || 'light'
      adminDefaultMode.value = (cfg.theme_default_mode as 'dark' | 'light') || 'dark'
    }

    // Check visitor cookie for mode override
    const savedMode = _getCookie(COOKIE_KEY) as 'dark' | 'light' | null
    currentMode.value = savedMode || adminDefaultMode.value

    // Apply the right theme for the current mode
    const themeId = currentMode.value === 'dark' ? adminDarkTheme.value : adminLightTheme.value
    currentTheme.value = themeId
    _apply(themeId)
  }

  /**
   * Toggle between dark and light mode. Saves preference to cookie.
   */
  function toggleDarkMode(): void {
    if (isDark.value) {
      currentMode.value = 'light'
      currentTheme.value = adminLightTheme.value
    } else {
      currentMode.value = 'dark'
      currentTheme.value = adminDarkTheme.value
    }
    _setCookie(COOKIE_KEY, currentMode.value, 365)
    _apply(currentTheme.value)
  }

  /**
   * Set a specific theme by ID — used by admin preview.
   */
  function setTheme(themeId: string): void {
    const found = allThemes.value.find(t => t.id === themeId)
    if (!found) return

    currentTheme.value = themeId
    currentMode.value = found.variant
    _setCookie(COOKIE_KEY, currentMode.value, 365)
    _apply(themeId)
  }

  /**
   * Update admin theme config (called after saving settings).
   */
  function updateAdminConfig(darkTheme: string, lightTheme: string, defaultMode: 'dark' | 'light'): void {
    adminDarkTheme.value = darkTheme
    adminLightTheme.value = lightTheme
    adminDefaultMode.value = defaultMode
  }

  /**
   * Load custom themes from backend manifest.
   */
  async function loadCustomThemes(): Promise<void> {
    try {
      const res = await fetch('/api/themes')
      if (!res.ok) return

      const data = await res.json()
      if (Array.isArray(data.themes)) {
        customThemes.value = data.themes.map((t: any) => ({
          id: t.id,
          name: t.name,
          author: t.author,
          description: t.description,
          builtin: false,
          variant: t.variant || 'dark',
        }))

        // Apply custom theme CSS if current is custom
        if (!BUILTIN_THEMES.some(t => t.id === currentTheme.value)) {
          await _loadCustomCSS(currentTheme.value)
        }
      }
    } catch {
      // Custom themes unavailable
    }
  }

  async function _loadCustomCSS(themeId: string): Promise<void> {
    if (customThemeCSS.value.has(themeId)) {
      _injectCustomCSS(themeId, customThemeCSS.value.get(themeId)!)
      return
    }
    try {
      const res = await fetch(`/api/themes/${themeId}/theme.css`)
      if (!res.ok) return
      const css = await res.text()
      customThemeCSS.value.set(themeId, css)
      _injectCustomCSS(themeId, css)
    } catch { /* */ }
  }

  function _injectCustomCSS(themeId: string, css: string): void {
    const id = `custom-theme-${themeId}`
    let el = document.getElementById(id)
    if (!el) {
      el = document.createElement('style')
      el.id = id
      document.head.appendChild(el)
    }
    el.textContent = css
  }

  function _apply(themeId: string): void {
    document.documentElement.setAttribute('data-theme', themeId)
  }

  function _getCookie(name: string): string | null {
    const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
    return match ? decodeURIComponent(match[1]) : null
  }

  function _setCookie(name: string, value: string, days: number): void {
    const expires = new Date(Date.now() + days * 86400000).toUTCString()
    document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`
  }

  return {
    currentTheme,
    currentMode,
    customThemes,
    allThemes,
    darkThemes,
    lightThemes,
    currentMeta,
    isDark,
    adminDarkTheme,
    adminLightTheme,
    adminDefaultMode,
    init,
    setTheme,
    toggleDarkMode,
    updateAdminConfig,
    loadCustomThemes,
  }
})
