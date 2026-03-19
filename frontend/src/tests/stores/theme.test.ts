import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore } from '@/stores/theme'

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

// Mock document.documentElement.setAttribute
const setAttributeMock = vi.fn()
Object.defineProperty(globalThis, 'document', {
  value: {
    documentElement: {
      setAttribute: setAttributeMock,
    },
    getElementById: vi.fn(() => null),
    createElement: vi.fn(() => ({ id: '', textContent: '' })),
    head: { appendChild: vi.fn() },
  },
})

describe('theme store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorageMock.clear()
    setAttributeMock.mockClear()
  })

  it('initializes with cyberpunk as default', () => {
    const store = useThemeStore()
    store.init()
    expect(store.currentTheme).toBe('cyberpunk')
    expect(setAttributeMock).toHaveBeenCalledWith('data-theme', 'cyberpunk')
  })

  it('restores saved theme from localStorage', () => {
    localStorageMock.setItem('mrip-theme', 'dark')
    const store = useThemeStore()
    store.init()
    expect(store.currentTheme).toBe('dark')
    expect(setAttributeMock).toHaveBeenCalledWith('data-theme', 'dark')
  })

  it('falls back to cyberpunk for invalid saved theme', () => {
    localStorageMock.setItem('mrip-theme', 'nonexistent')
    const store = useThemeStore()
    store.init()
    expect(store.currentTheme).toBe('cyberpunk')
  })

  it('setTheme updates state, localStorage, and DOM', () => {
    const store = useThemeStore()
    store.init()
    store.setTheme('light')
    expect(store.currentTheme).toBe('light')
    expect(localStorageMock.setItem).toHaveBeenCalledWith('mrip-theme', 'light')
    expect(setAttributeMock).toHaveBeenCalledWith('data-theme', 'light')
  })

  it('setTheme ignores unknown theme IDs', () => {
    const store = useThemeStore()
    store.init()
    store.setTheme('doesnotexist')
    expect(store.currentTheme).toBe('cyberpunk')
  })

  it('lists 3 built-in themes', () => {
    const store = useThemeStore()
    expect(store.allThemes).toHaveLength(3)
    expect(store.allThemes.map(t => t.id)).toEqual(['cyberpunk', 'dark', 'light'])
  })

  it('all built-in themes are marked builtin: true', () => {
    const store = useThemeStore()
    expect(store.allThemes.every(t => t.builtin)).toBe(true)
  })

  it('currentMeta returns metadata for active theme', () => {
    const store = useThemeStore()
    store.init()
    expect(store.currentMeta?.id).toBe('cyberpunk')
    expect(store.currentMeta?.name).toBe('Cyberpunk')
  })
})
