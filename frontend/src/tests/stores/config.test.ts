import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useConfigStore } from '@/stores/config'

// Mock the api module
vi.mock('@/api/client', () => ({
  api: {
    getPublicConfig: vi.fn(),
  },
}))

import { api } from '@/api/client'

describe('config store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('starts with null config', () => {
    const store = useConfigStore()
    expect(store.config).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('loads config successfully', async () => {
    const mockConfig = {
      session_mode: 'isolated',
      default_theme: 'dark',
      welcome_message: 'Test welcome',
      purge_enabled: false,
      max_concurrent_downloads: 3,
    }
    vi.mocked(api.getPublicConfig).mockResolvedValue(mockConfig)

    const store = useConfigStore()
    await store.loadConfig()

    expect(store.config).toEqual(mockConfig)
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('handles load error', async () => {
    vi.mocked(api.getPublicConfig).mockRejectedValue(new Error('Network error'))

    const store = useConfigStore()
    await store.loadConfig()

    expect(store.config).toBeNull()
    expect(store.error).toBe('Network error')
    expect(store.isLoading).toBe(false)
  })
})
