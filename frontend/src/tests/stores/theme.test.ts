import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore } from '@/stores/theme'
import { useConfigStore } from '@/stores/config'

// Mock document
const setAttributeMock = vi.fn()
Object.defineProperty(globalThis, 'document', {
  value: {
    documentElement: {
      setAttribute: setAttributeMock,
    },
    getElementById: vi.fn(() => null),
    createElement: vi.fn(() => ({ id: '', textContent: '' })),
    head: { appendChild: vi.fn() },
    cookie: '',
  },
})

describe('theme store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setAttributeMock.mockClear()
    document.cookie = ''
  })

  it('initializes with cyberpunk as default (dark mode)', () => {
    const store = useThemeStore()
    store.init()
    expect(store.currentTheme).toBe('cyberpunk')
    expect(store.currentMode).toBe('dark')
    expect(store.isDark).toBe(true)
    expect(setAttributeMock).toHaveBeenCalledWith('data-theme', 'cyberpunk')
  })

  it('uses admin config for defaults when available', () => {
    const configStore = useConfigStore()
    configStore.config = {
      theme_dark: 'neon',
      theme_light: 'paper',
      theme_default_mode: 'light',
    } as any

    const store = useThemeStore()
    store.init()
    expect(store.currentTheme).toBe('paper')
    expect(store.currentMode).toBe('light')
    expect(store.isDark).toBe(false)
  })

  it('setTheme updates state and applies to DOM', () => {
    const store = useThemeStore()
    store.init()
    store.setTheme('light')
    expect(store.currentTheme).toBe('light')
    expect(store.currentMode).toBe('light')
    expect(setAttributeMock).toHaveBeenCalledWith('data-theme', 'light')
  })

  it('setTheme ignores unknown theme IDs', () => {
    const store = useThemeStore()
    store.init()
    store.setTheme('doesnotexist')
    expect(store.currentTheme).toBe('cyberpunk')
  })

  it('lists 9 built-in themes', () => {
    const store = useThemeStore()
    expect(store.allThemes).toHaveLength(9)
    expect(store.allThemes.map(t => t.id)).toEqual([
      'cyberpunk', 'dark', 'midnight', 'hacker', 'neon',
      'light', 'paper', 'arctic', 'solarized',
    ])
  })

  it('all built-in themes are marked builtin: true', () => {
    const store = useThemeStore()
    expect(store.allThemes.every(t => t.builtin)).toBe(true)
  })

  it('darkThemes has 5, lightThemes has 4', () => {
    const store = useThemeStore()
    expect(store.darkThemes).toHaveLength(5)
    expect(store.lightThemes).toHaveLength(4)
  })

  it('currentMeta returns metadata for active theme', () => {
    const store = useThemeStore()
    store.init()
    expect(store.currentMeta?.id).toBe('cyberpunk')
    expect(store.currentMeta?.name).toBe('Cyberpunk')
  })

  it('isDark reflects current mode', () => {
    const store = useThemeStore()
    store.init()
    expect(store.isDark).toBe(true)
    store.setTheme('light')
    expect(store.isDark).toBe(false)
    store.setTheme('hacker')
    expect(store.isDark).toBe(true)
  })

  it('toggleDarkMode switches between admin dark and light themes', () => {
    const store = useThemeStore()
    store.init() // cyberpunk (dark)
    store.toggleDarkMode()
    expect(store.currentTheme).toBe('light')
    expect(store.isDark).toBe(false)
    store.toggleDarkMode()
    expect(store.currentTheme).toBe('cyberpunk')
    expect(store.isDark).toBe(true)
  })

  it('toggleDarkMode uses admin-configured themes', () => {
    const configStore = useConfigStore()
    configStore.config = {
      theme_dark: 'neon',
      theme_light: 'arctic',
      theme_default_mode: 'dark',
    } as any

    const store = useThemeStore()
    store.init()
    expect(store.currentTheme).toBe('neon')
    store.toggleDarkMode()
    expect(store.currentTheme).toBe('arctic')
    store.toggleDarkMode()
    expect(store.currentTheme).toBe('neon')
  })

  it('updateAdminConfig changes the theme pair', () => {
    const store = useThemeStore()
    store.init()
    store.updateAdminConfig('midnight', 'solarized', 'light')
    expect(store.adminDarkTheme).toBe('midnight')
    expect(store.adminLightTheme).toBe('solarized')
    expect(store.adminDefaultMode).toBe('light')
  })
})
