<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import ProgressBar from './ProgressBar.vue'
import type { Job } from '@/api/types'

const props = defineProps<{
  jobs: Job[]
}>()

const store = useDownloadsStore()

// Toast notification
const toast = ref<string | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(message: string): void {
  toast.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 2000)
}

// Sort state
type SortKey = 'name' | 'status' | 'progress' | 'speed' | 'eta'
const sortBy = ref<SortKey>('name')
const sortDir = ref<'asc' | 'desc'>('asc')

function toggleSort(key: SortKey): void {
  if (sortBy.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = key
    sortDir.value = key === 'progress' ? 'desc' : 'asc'
  }
}

function sortIndicator(key: SortKey): string {
  if (sortBy.value !== key) return ''
  return sortDir.value === 'asc' ? ' ▲' : ' ▼'
}

const sortedJobs = computed<Job[]>(() => {
  const list = [...props.jobs]
  const dir = sortDir.value === 'asc' ? 1 : -1

  list.sort((a, b) => {
    switch (sortBy.value) {
      case 'name':
        return dir * displayName(a).localeCompare(displayName(b))
      case 'status':
        return dir * a.status.localeCompare(b.status)
      case 'progress':
        return dir * (a.progress_percent - b.progress_percent)
      case 'speed':
        return dir * (parseSpeed(a.speed) - parseSpeed(b.speed))
      case 'eta':
        return dir * (parseEta(a.eta) - parseEta(b.eta))
      default:
        return 0
    }
  })
  return list
})

function displayName(job: Job): string {
  if (job.filename) {
    const parts = job.filename.replace(/\\/g, '/').split('/')
    const name = parts[parts.length - 1]
    // Ensure extension is visible: if name is long, truncate the middle
    if (name.length > 60) {
      const ext = name.lastIndexOf('.')
      if (ext > 0) {
        const extension = name.slice(ext)
        const base = name.slice(0, 55 - extension.length)
        return `${base}…${extension}`
      }
    }
    return name
  }
  try {
    const u = new URL(job.url)
    return `${u.hostname}${u.pathname}`.slice(0, 80)
  } catch {
    return job.url.slice(0, 80)
  }
}

function parseSpeed(speed: string | null): number {
  if (!speed) return 0
  const match = speed.match(/([\d.]+)\s*(B|KiB|MiB|GiB)/)
  if (!match) return 0
  const val = parseFloat(match[1])
  const unit = match[2]
  const multipliers: Record<string, number> = { B: 1, KiB: 1024, MiB: 1048576, GiB: 1073741824 }
  return val * (multipliers[unit] || 1)
}

function parseEta(eta: string | null): number {
  if (!eta) return Infinity
  // yt-dlp formats ETA as HH:MM:SS or MM:SS or SS
  const parts = eta.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return parts[0] || Infinity
}

function isActive(job: Job): boolean {
  return !store.isTerminal(job.status)
}

function isCompleted(job: Job): boolean {
  return job.status === 'completed'
}

/** Infer whether the job is audio or video from quality/filename. */
function isAudioJob(job: Job): boolean {
  if (job.quality === 'bestaudio') return true
  if (job.filename) {
    const ext = job.filename.split('.').pop()?.toLowerCase() || ''
    if (['mp3', 'wav', 'flac', 'opus', 'm4a', 'aac', 'ogg', 'wma'].includes(ext)) return true
  }
  return false
}

// File download URL — filename is relative to the output directory
// (normalized by the backend). May contain subdirectories for source templates.
function downloadUrl(job: Job): string {
  if (!job.filename) return '#'
  const normalized = job.filename.replace(/\\/g, '/')
  // Encode each path segment separately to preserve directory structure
  return `/api/downloads/${normalized.split('/').map(encodeURIComponent).join('/')}`
}

// Copy download link to clipboard
async function copyLink(job: Job): Promise<void> {
  const url = `${window.location.origin}${downloadUrl(job)}`
  try {
    await navigator.clipboard.writeText(url)
    showToast('Link copied to clipboard')
  } catch {
    // Fallback — clipboard API may fail in non-secure contexts
    showToast('Copy failed — clipboard unavailable')
  }
}

const cancelling = ref<Set<string>>(new Set())

async function cancel(jobId: string): Promise<void> {
  if (cancelling.value.has(jobId)) return
  cancelling.value.add(jobId)
  try {
    await store.cancelDownload(jobId)
  } catch (err) {
    console.error('[DownloadTable] Cancel failed:', err)
  } finally {
    cancelling.value.delete(jobId)
  }
}

async function clearJob(jobId: string): Promise<void> {
  try {
    await store.cancelDownload(jobId)
  } catch {
    // If DELETE fails (already gone), just remove locally
    store.handleJobRemoved(jobId)
  }
}
</script>

<template>
  <div class="download-table-wrap">
    <table class="download-table">
      <thead>
        <tr>
          <th class="col-name sortable" @click="toggleSort('name')">
            Name{{ sortIndicator('name') }}
          </th>
          <th class="col-status sortable" @click="toggleSort('status')">
            Status{{ sortIndicator('status') }}
          </th>
          <th class="col-progress sortable" @click="toggleSort('progress')">
            Progress{{ sortIndicator('progress') }}
          </th>
          <th class="col-speed sortable hide-mobile" @click="toggleSort('speed')">
            Speed{{ sortIndicator('speed') }}
          </th>
          <th class="col-eta sortable hide-mobile" @click="toggleSort('eta')">
            ETA{{ sortIndicator('eta') }}
          </th>
          <th class="col-actions">Actions</th>
        </tr>
      </thead>
      <TransitionGroup name="table-row" tag="tbody">
        <tr v-for="job in sortedJobs" :key="job.id" :class="'row-' + job.status">
          <td class="col-name" :title="job.url">
            <span class="name-with-icon">
              <!-- Media type icon -->
              <svg v-if="isAudioJob(job)" class="media-icon audio-icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
              <svg v-else class="media-icon video-icon" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
              <span class="name-text">{{ displayName(job) }}</span>
            </span>
          </td>
          <td class="col-status">
            <span class="status-badge" :class="'badge-' + job.status">
              {{ job.status }}
            </span>
          </td>
          <td class="col-progress">
            <ProgressBar
              v-if="job.status === 'downloading' || job.status === 'extracting'"
              :percent="job.progress_percent"
            />
            <span v-else-if="isCompleted(job)" class="progress-done">Done</span>
            <span v-else-if="job.error_message" class="progress-error" :title="job.error_message">
              {{ job.error_message.slice(0, 40) }}
            </span>
            <span v-else class="progress-na">—</span>
          </td>
          <td class="col-speed hide-mobile">
            <span v-if="job.speed" class="mono">{{ job.speed }}</span>
            <span v-else class="text-muted">—</span>
          </td>
          <td class="col-eta hide-mobile">
            <span v-if="job.eta" class="mono">{{ job.eta }}</span>
            <span v-else class="text-muted">—</span>
          </td>
          <td class="col-actions">
            <div class="action-group">
              <!-- Completed: download, copy link, clear -->
              <template v-if="isCompleted(job)">
                <a
                  :href="downloadUrl(job)"
                  class="action-btn action-download"
                  title="Download file"
                  download
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </a>
                <button
                  class="action-btn action-copy"
                  title="Copy download link"
                  @click="copyLink(job)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                </button>
                <button
                  class="action-btn action-clear"
                  title="Remove from list"
                  @click="clearJob(job.id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </template>
              <!-- Active: cancel -->
              <template v-else-if="isActive(job)">
                <button
                  class="action-btn action-cancel"
                  :disabled="cancelling.has(job.id)"
                  title="Cancel download"
                  @click.stop="cancel(job.id)"
                >
                  <svg v-if="!cancelling.has(job.id)" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  <span v-else class="spinner-sm"></span>
                </button>
              </template>
              <!-- Failed/expired: clear -->
              <template v-else>
                <button
                  class="action-btn action-clear"
                  title="Remove from list"
                  @click="clearJob(job.id)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </template>
            </div>
          </td>
        </tr>
      </TransitionGroup>
    </table>
    <!-- Toast notification -->
    <Transition name="toast">
      <div v-if="toast" class="toast-notification">
        {{ toast }}
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.download-table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}

.download-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-sm);
}

.download-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
}

.download-table th {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  font-weight: 600;
  font-size: var(--font-size-sm);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
  background: var(--color-surface);
  border-bottom: 2px solid var(--color-border);
  white-space: nowrap;
  user-select: none;
}

.download-table th.sortable {
  cursor: pointer;
}

.download-table th.sortable:hover {
  color: var(--color-accent);
}

.download-table td {
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.download-table tbody tr {
  transition: background-color 0.15s ease;
}

.download-table tbody tr:hover {
  background: var(--color-surface-hover);
}

/* Column widths */
.col-name {
  min-width: 200px;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.name-with-icon {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  overflow: hidden;
}

.media-icon {
  flex-shrink: 0;
  color: var(--color-text-muted);
  opacity: 0.7;
}

.name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-status { width: 100px; }
.col-progress { width: 180px; min-width: 120px; }
.col-speed { width: 100px; }
.col-eta { width: 80px; }
.col-actions { width: 110px; }

/* Status badges */
.status-badge {
  display: inline-block;
  padding: 2px var(--space-sm);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}

.badge-queued {
  background: color-mix(in srgb, var(--color-text-muted) 15%, transparent);
  color: var(--color-text-muted);
}
.badge-extracting {
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
}
.badge-downloading {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
}
.badge-completed {
  background: color-mix(in srgb, var(--color-success) 15%, transparent);
  color: var(--color-success);
}
.badge-failed {
  background: color-mix(in srgb, var(--color-error) 15%, transparent);
  color: var(--color-error);
}
.badge-expired {
  background: color-mix(in srgb, var(--color-text-muted) 15%, transparent);
  color: var(--color-text-muted);
}

/* Progress cell */
.progress-done {
  color: var(--color-success);
  font-weight: 500;
}
.progress-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
}
.progress-na {
  color: var(--color-text-muted);
}

/* Utility */
.mono {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}
.text-muted {
  color: var(--color-text-muted);
}

/* Actions */
.action-group {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  background: transparent;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  text-decoration: none;
}

.action-btn:hover {
  background: var(--color-surface-hover);
}

.action-download:hover {
  color: var(--color-success);
  border-color: var(--color-success);
}

.action-copy:hover {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.action-cancel:hover,
.action-clear:hover {
  color: var(--color-error);
  border-color: var(--color-error);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner-sm {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Table row transitions */
.table-row-enter-active,
.table-row-leave-active {
  transition: all 0.3s ease;
}

.table-row-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}

.table-row-leave-to {
  opacity: 0;
}

/* Mobile: hide speed and ETA columns */
@media (max-width: 639px) {
  .hide-mobile {
    display: none;
  }

  .col-name {
    min-width: 120px;
    max-width: 200px;
  }

  .col-progress {
    min-width: 80px;
    width: 100px;
  }

  .col-actions {
    width: 80px;
  }

  .download-table th,
  .download-table td {
    padding: var(--space-xs) var(--space-sm);
  }
}

/* Toast notification */
.toast-notification {
  position: fixed;
  bottom: calc(var(--header-height) + var(--space-md));
  left: 50%;
  transform: translateX(-50%);
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  padding: var(--space-sm) var(--space-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  pointer-events: none;
}

.toast-enter-active {
  transition: all 0.2s ease-out;
}

.toast-leave-active {
  transition: all 0.15s ease-in;
}

.toast-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}

.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-4px);
}
</style>
