<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import DownloadTable from './DownloadTable.vue'

type Filter = 'all' | 'active' | 'completed' | 'failed'

const store = useDownloadsStore()
const activeFilter = ref<Filter>('all')

const filteredJobs = computed(() => {
  switch (activeFilter.value) {
    case 'active':
      return store.activeJobs
    case 'completed':
      return store.completedJobs
    case 'failed':
      return store.failedJobs
    default:
      return store.jobList
  }
})

const filterCounts = computed(() => ({
  all: store.jobList.length,
  active: store.activeJobs.length,
  completed: store.completedJobs.length,
  failed: store.failedJobs.length,
}))

function setFilter(f: Filter): void {
  activeFilter.value = f
}

// Download All
const completedWithFiles = computed(() =>
  store.completedJobs.filter(j => j.filename)
)

function downloadAll(): void {
  const jobs = completedWithFiles.value
  if (!jobs.length) return
  jobs.forEach((job, i) => {
    setTimeout(() => {
      const a = document.createElement('a')
      a.href = `/api/downloads/${encodeURIComponent(job.filename!)}`
      a.download = ''
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }, i * 300)
  })
}

// Clear completed + failed
const clearState = ref<'idle' | 'confirm'>('idle')
let clearTimer: ReturnType<typeof setTimeout> | null = null

const clearableJobs = computed(() =>
  store.jobList.filter(j => j.status === 'completed' || j.status === 'failed')
)

function handleClear(): void {
  if (clearState.value === 'idle') {
    clearState.value = 'confirm'
    clearTimer = setTimeout(() => { clearState.value = 'idle' }, 3000)
  } else {
    if (clearTimer) clearTimeout(clearTimer)
    clearState.value = 'idle'
    for (const job of clearableJobs.value) {
      store.cancelDownload(job.id)
    }
  }
}
</script>

<template>
  <div class="download-queue">
    <div class="queue-toolbar">
      <div class="queue-filters">
        <button
          v-for="f in (['all', 'active', 'completed', 'failed'] as Filter[])"
          :key="f"
          class="filter-btn"
          :class="{ active: activeFilter === f }"
          @click="setFilter(f)"
        >
          {{ f }}
          <span class="filter-count" v-if="filterCounts[f] > 0">({{ filterCounts[f] }})</span>
        </button>
      </div>
      <div class="queue-actions" v-if="store.jobList.length > 0">
        <button
          v-if="completedWithFiles.length > 1"
          class="btn-download-all"
          @click="downloadAll"
          title="Download all completed files"
        >
          ⬇ Download All ({{ completedWithFiles.length }})
        </button>
        <button
          v-if="clearableJobs.length > 0"
          class="btn-clear"
          :class="{ confirming: clearState === 'confirm' }"
          @click="handleClear"
          :title="clearState === 'confirm' ? 'Click again to clear' : 'Clear completed and failed downloads'"
        >
          {{ clearState === 'confirm' ? 'Sure?' : 'Clear' }}
        </button>
      </div>
    </div>

    <div v-if="filteredJobs.length === 0" class="queue-empty">
      <template v-if="activeFilter === 'all'">
        No downloads yet. Paste a URL above to get started.
      </template>
      <template v-else>
        No {{ activeFilter }} downloads.
      </template>
    </div>

    <DownloadTable v-else :jobs="filteredJobs" />
  </div>
</template>

<style scoped>
.download-queue {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.queue-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.queue-filters {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.queue-actions {
  display: flex;
  gap: var(--space-xs);
  align-items: center;
}

.filter-btn {
  padding: var(--space-xs) var(--space-md);
  min-height: 36px;
  background: var(--color-surface);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  text-transform: capitalize;
}

.filter-btn:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.filter-btn.active {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.filter-count {
  opacity: 0.7;
}

.btn-download-all {
  min-height: 36px;
  font-size: var(--font-size-sm);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-accent);
  color: var(--color-bg);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 600;
  transition: background-color 0.15s;
}

.btn-download-all:hover {
  background: var(--color-accent-hover);
}

.btn-clear {
  min-height: 36px;
  min-width: 70px;
  font-size: var(--font-size-sm);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-surface);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-clear:hover {
  border-color: var(--color-error);
  color: var(--color-error);
}

.btn-clear.confirming {
  background: var(--color-error);
  border-color: var(--color-error);
  color: var(--color-bg);
  font-weight: 600;
}

.btn-clear.confirming:hover {
  background: color-mix(in srgb, var(--color-error) 85%, black);
}

.queue-empty {
  padding: var(--space-xl);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

/* Mobile: full-width filters */
@media (max-width: 767px) {
  .queue-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-sm);
  }

  .queue-filters {
    display: flex;
    gap: var(--space-xs);
    overflow-x: auto;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
  }

  .queue-actions {
    display: flex;
    gap: var(--space-xs);
  }

  .queue-actions .btn-download-all,
  .queue-actions .btn-clear {
    flex: 1;
    min-height: var(--touch-min);
    justify-content: center;
  }

  .filter-btn {
    min-height: var(--touch-min);
    flex-shrink: 0;
  }
}
</style>
