<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import ProgressBar from './ProgressBar.vue'
import type { Job, JobStatus } from '@/api/types'

const props = defineProps<{
  job: Job
}>()

const store = useDownloadsStore()

const isActive = computed(() => !store.isTerminal(props.job.status))

const statusClass = computed(() => {
  const map: Record<string, string> = {
    queued: 'status-queued',
    extracting: 'status-extracting',
    downloading: 'status-downloading',
    completed: 'status-completed',
    failed: 'status-failed',
    expired: 'status-expired',
  }
  return map[props.job.status] || ''
})

const displayName = computed(() => {
  if (props.job.filename) {
    // Show just the filename, not the full path
    const parts = props.job.filename.replace(/\\/g, '/').split('/')
    return parts[parts.length - 1]
  }
  // Truncate URL for display
  try {
    const u = new URL(props.job.url)
    return `${u.hostname}${u.pathname}`.slice(0, 60)
  } catch {
    return props.job.url.slice(0, 60)
  }
})

const showProgress = computed(() =>
  props.job.status === 'downloading' || props.job.status === 'extracting',
)

const cancelling = ref(false)

async function cancel(): Promise<void> {
  if (cancelling.value) return
  cancelling.value = true
  try {
    await store.cancelDownload(props.job.id)
  } catch (err) {
    console.error('[DownloadItem] Cancel failed:', err)
  } finally {
    cancelling.value = false
  }
}
</script>

<template>
  <div class="download-item" :class="statusClass">
    <div class="item-header">
      <span class="item-name" :title="job.url">{{ displayName }}</span>
      <span class="item-status">{{ job.status }}</span>
    </div>

    <ProgressBar
      v-if="showProgress"
      :percent="job.progress_percent"
    />

    <div class="item-details">
      <span v-if="job.speed" class="detail-speed">{{ job.speed }}</span>
      <span v-if="job.eta" class="detail-eta">ETA: {{ job.eta }}</span>
      <span v-if="job.error_message" class="detail-error">{{ job.error_message }}</span>
    </div>

    <div class="item-actions">
      <button
        v-if="isActive"
        class="btn-cancel"
        :class="{ cancelling }"
        :disabled="cancelling"
        @click.stop="cancel"
        title="Cancel download"
      >
        {{ cancelling ? '…' : '✕' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.download-item {
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-rows: auto auto auto;
  gap: var(--space-xs) var(--space-sm);
  padding: var(--space-md);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-border);
}

.download-item.status-queued { border-left-color: var(--color-text-muted); }
.download-item.status-extracting { border-left-color: var(--color-warning); }
.download-item.status-downloading { border-left-color: var(--color-accent); }
.download-item.status-completed { border-left-color: var(--color-success); }
.download-item.status-failed { border-left-color: var(--color-error); }
.download-item.status-expired { border-left-color: var(--color-text-muted); }

.item-header {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-sm);
}

.item-name {
  font-size: var(--font-size-base);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.item-status {
  font-size: var(--font-size-sm);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  white-space: nowrap;
}

.item-details {
  grid-column: 1;
  display: flex;
  gap: var(--space-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.detail-error {
  color: var(--color-error);
  font-family: var(--font-ui);
}

.item-actions {
  grid-column: 2;
  grid-row: 2 / -1;
  display: flex;
  align-items: center;
}

.btn-cancel {
  width: var(--touch-min);
  height: var(--touch-min);
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-lg);
  padding: 0;
}

.btn-cancel:hover {
  color: var(--color-error);
  border-color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
}
</style>
