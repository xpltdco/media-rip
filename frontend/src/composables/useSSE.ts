/**
 * SSE composable — manages EventSource lifecycle and dispatches events
 * to the downloads Pinia store.
 *
 * Features:
 * - Automatic reconnect with exponential backoff (1s → 2s → 4s → … max 30s)
 * - Connection status exposed as a reactive ref
 * - Dispatches init, job_update, job_removed events to the downloads store
 * - Cleanup on unmount (composable disposal)
 */

import { ref, onUnmounted } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import type { SSEInitEvent, ProgressEvent, SSEJobRemovedEvent } from '@/api/types'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

const SSE_URL = '/api/events'
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30000

export function useSSE() {
  const store = useDownloadsStore()
  const connectionStatus = ref<ConnectionStatus>('disconnected')
  const reconnectCount = ref(0)

  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect(): void {
    cleanup()

    connectionStatus.value = reconnectCount.value > 0 ? 'reconnecting' : 'connecting'

    eventSource = new EventSource(SSE_URL)

    eventSource.onopen = () => {
      connectionStatus.value = 'connected'
      reconnectCount.value = 0
    }

    // Named event handlers
    eventSource.addEventListener('init', (e: MessageEvent) => {
      try {
        const data: SSEInitEvent = JSON.parse(e.data)
        store.handleInit(data.jobs)
      } catch (err) {
        console.error('[SSE] Failed to parse init event:', err)
      }
    })

    eventSource.addEventListener('job_update', (e: MessageEvent) => {
      try {
        const data: ProgressEvent = JSON.parse(e.data)
        console.log('[SSE] job_update:', data.job_id, data.status, data.percent)
        store.handleJobUpdate(data)
      } catch (err) {
        console.error('[SSE] Failed to parse job_update event:', err)
      }
    })

    eventSource.addEventListener('job_removed', (e: MessageEvent) => {
      try {
        const data: SSEJobRemovedEvent = JSON.parse(e.data)
        store.handleJobRemoved(data.job_id)
      } catch (err) {
        console.error('[SSE] Failed to parse job_removed event:', err)
      }
    })

    // ping events are keepalive — no action needed

    eventSource.onerror = () => {
      // EventSource auto-closes on error; we handle reconnect ourselves
      connectionStatus.value = 'disconnected'
      eventSource?.close()
      eventSource = null
      scheduleReconnect()
    }
  }

  function scheduleReconnect(): void {
    reconnectCount.value++
    const delay = Math.min(
      RECONNECT_BASE_MS * Math.pow(2, reconnectCount.value - 1),
      RECONNECT_MAX_MS,
    )
    console.log(`[SSE] Reconnecting in ${delay}ms (attempt ${reconnectCount.value})`)
    reconnectTimer = setTimeout(connect, delay)
  }

  function disconnect(): void {
    cleanup()
    connectionStatus.value = 'disconnected'
    reconnectCount.value = 0
  }

  function cleanup(): void {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (eventSource !== null) {
      eventSource.close()
      eventSource = null
    }
  }

  // Auto-cleanup on component unmount
  onUnmounted(() => {
    disconnect()
  })

  return {
    connectionStatus,
    reconnectCount,
    connect,
    disconnect,
  }
}
