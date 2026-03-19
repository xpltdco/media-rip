/**
 * Admin Pinia store — manages admin authentication and API calls.
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { PublicConfig } from '@/api/types'

interface AdminSession {
  id: string
  created_at: string
  last_seen: string
  job_count: number
}

interface StorageInfo {
  disk: { total: number; used: number; free: number }
  jobs_by_status: Record<string, number>
}

interface PurgeResult {
  rows_deleted: number
  files_deleted: number
  files_missing: number
  active_skipped: number
}

export const useAdminStore = defineStore('admin', () => {
  const username = ref('')
  const password = ref('')
  const isAuthenticated = ref(false)
  const authError = ref<string | null>(null)
  const sessions = ref<AdminSession[]>([])
  const storage = ref<StorageInfo | null>(null)
  const purgeResult = ref<PurgeResult | null>(null)
  const isLoading = ref(false)

  function _authHeaders(): Record<string, string> {
    const encoded = btoa(`${username.value}:${password.value}`)
    return { Authorization: `Basic ${encoded}` }
  }

  async function login(user: string, pass: string): Promise<boolean> {
    username.value = user
    password.value = pass
    authError.value = null

    try {
      const res = await fetch('/api/admin/sessions', {
        headers: _authHeaders(),
      })
      if (res.ok) {
        isAuthenticated.value = true
        const data = await res.json()
        sessions.value = data.sessions
        return true
      } else if (res.status === 401) {
        authError.value = 'Invalid credentials'
        isAuthenticated.value = false
        return false
      } else if (res.status === 404) {
        authError.value = 'Admin panel is not enabled'
        isAuthenticated.value = false
        return false
      }
      authError.value = `Unexpected error: ${res.status}`
      return false
    } catch (err: any) {
      authError.value = err.message || 'Network error'
      return false
    }
  }

  function logout(): void {
    username.value = ''
    password.value = ''
    isAuthenticated.value = false
    sessions.value = []
    storage.value = null
    purgeResult.value = null
  }

  async function loadSessions(): Promise<void> {
    const res = await fetch('/api/admin/sessions', { headers: _authHeaders() })
    if (res.ok) {
      const data = await res.json()
      sessions.value = data.sessions
    }
  }

  async function loadStorage(): Promise<void> {
    const res = await fetch('/api/admin/storage', { headers: _authHeaders() })
    if (res.ok) {
      storage.value = await res.json()
    }
  }

  async function triggerPurge(): Promise<void> {
    isLoading.value = true
    try {
      const res = await fetch('/api/admin/purge', {
        method: 'POST',
        headers: _authHeaders(),
      })
      if (res.ok) {
        purgeResult.value = await res.json()
      }
    } finally {
      isLoading.value = false
    }
  }

  return {
    username,
    isAuthenticated,
    authError,
    sessions,
    storage,
    purgeResult,
    isLoading,
    login,
    logout,
    loadSessions,
    loadStorage,
    triggerPurge,
  }
})
