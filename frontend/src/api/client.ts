/**
 * Fetch-based API client for the media.rip() backend.
 *
 * All routes are relative — the Vite dev proxy handles /api → backend.
 * In production, the SPA is served by the same FastAPI process, so
 * relative paths work without configuration.
 */

import type { Job, JobCreate, FormatInfo, PublicConfig, HealthStatus, UrlInfo } from './types'

class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: string,
  ) {
    super(`API error ${status}: ${statusText}`)
    this.name = 'ApiError'
  }
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...options?.headers,
    },
  })

  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, res.statusText, body)
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T
  }

  return res.json()
}

export const api = {
  /** Fetch all downloads for the current session. */
  async getDownloads(): Promise<Job[]> {
    return request<Job[]>('/api/downloads')
  },

  /** Submit a new download. */
  async createDownload(payload: JobCreate): Promise<Job> {
    return request<Job>('/api/downloads', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  /** Cancel / remove a download. */
  async deleteDownload(id: string): Promise<void> {
    return request<void>(`/api/downloads/${id}`, {
      method: 'DELETE',
    })
  },

  /** Extract available formats for a URL. */
  async getFormats(url: string): Promise<FormatInfo[]> {
    const encoded = encodeURIComponent(url)
    return request<FormatInfo[]>(`/api/formats?url=${encoded}`)
  },

  /** Load public (non-sensitive) configuration. */
  async getPublicConfig(): Promise<PublicConfig> {
    return request<PublicConfig>('/api/config/public')
  },

  /** Health check. */
  async getHealth(): Promise<HealthStatus> {
    return request<HealthStatus>('/api/health')
  },

  /** Get URL metadata (title, playlist detection, audio-only detection). */
  async getUrlInfo(url: string): Promise<UrlInfo> {
    return request<UrlInfo>('/api/url-info', {
      method: 'POST',
      body: JSON.stringify({ url }),
    })
  },
}

export { ApiError }
