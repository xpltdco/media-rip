/**
 * Config Pinia store — loads and caches public configuration.
 */

import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/api/client'
import type { PublicConfig } from '@/api/types'

export const useConfigStore = defineStore('config', () => {
  const config = ref<PublicConfig | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function loadConfig(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      config.value = await api.getPublicConfig()
    } catch (err: any) {
      error.value = err.message || 'Failed to load configuration'
    } finally {
      isLoading.value = false
    }
  }

  return {
    config,
    isLoading,
    error,
    loadConfig,
  }
})
