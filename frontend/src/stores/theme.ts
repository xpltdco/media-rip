/**
 * Theme Pinia store — manages theme selection and application.
 *
 * Built-in themes: cyberpunk (default), dark, light
 * Custom themes: loaded via /api/themes manifest at runtime
 *
 * Persistence: localStorage key 'mrip-theme'
 * Application: sets data-theme attribute on <html> element
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export interface ThemeMeta {
  id: string
  name: string
  author?: string
  description?: string
  builtin: boolean
  variant: 'dark' | 'light'
}

const STORAGE_KEY = 'mrip-theme'
const DEFAULT_THEME = 'cyberpunk'

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
  const currentTheme = ref(DEFAULT_THEME)
  const customThemes = ref<ThemeMeta[]>([])
  const customThemeCSS = ref<Map<string, string>>(new Map())

  /** Whether the current theme is a dark variant. */
  const isDark = computed(() => {
    const meta = allThemes.value.find(t => t.id === currentTheme.value)
    return meta ? meta.variant === 'dark' : true
  })

  const darkThemes = computed(() => allThemes.value.filter(t => t.variant === 'dark'))
  const lightThemes = computed(() => allThemes.value.filter(t => t.variant === 'light'))

  const allThemes = computed<ThemeMeta[]>(() => [
    ...BUILTIN_THEMES,
    ...customThemes.value,
  ])

  const currentMeta = computed<ThemeMeta | undefined>(() =>
    allThemes.value.find(t => t.id === currentTheme.value)
  )

  /**
   * Initialize the theme store — reads from localStorage and applies.
   */
  function init(): void {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved && BUILTIN_THEMES.some(t => t.id === saved)) {
      currentTheme.value = saved
    } else {
      currentTheme.value = DEFAULT_THEME
    }
    _apply(currentTheme.value)
  }

  /**
   * Toggle between the current theme's dark and light variant.
   * Cyberpunk (default) ↔ Light. Dark ↔ Light.
   */
  function toggleDarkMode(): void {
    if (isDark.value) {
      // Switch to last used light theme, or first available
      const lastLight = localStorage.getItem(STORAGE_KEY + '-light') || 'light'
      setTheme(lastLight)
    } else {
      // Return to the last dark theme, defaulting to cyberpunk
      const lastDark = localStorage.getItem(STORAGE_KEY + '-dark') || DEFAULT_THEME
      setTheme(lastDark)
    }
  }

  /**
   * Switch to a theme by ID. Saves to localStorage and applies immediately.
   */
  function setTheme(themeId: string): void {
    const found = allThemes.value.find(t => t.id === themeId)
    if (!found) return

    currentTheme.value = themeId
    localStorage.setItem(STORAGE_KEY, themeId)
    // Remember the last dark theme for toggle
    const meta = allThemes.value.find(t => t.id === themeId)
    if (meta?.variant === 'dark') {
      localStorage.setItem(STORAGE_KEY + '-dark', themeId)
    } else {
      localStorage.setItem(STORAGE_KEY + '-light', themeId)
    }
    _apply(themeId)
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
          variant: t.variant || 'dark',  // default custom themes to dark
        }))

        // If saved theme is a custom theme, validate it still exists
        const saved = localStorage.getItem(STORAGE_KEY)
        if (saved && !allThemes.value.some(t => t.id === saved)) {
          setTheme(DEFAULT_THEME)
        }

        // Apply custom theme CSS if current is custom
        if (!BUILTIN_THEMES.some(t => t.id === currentTheme.value)) {
          await _loadCustomCSS(currentTheme.value)
        }
      }
    } catch {
      // Custom themes unavailable — use built-ins only
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
    } catch {
      // Failed to load custom CSS
    }
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

  return {
    currentTheme,
    customThemes,
    allThemes,
    darkThemes,
    lightThemes,
    currentMeta,
    isDark,
    init,
    setTheme,
    toggleDarkMode,
    loadCustomThemes,
  }
})
