<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDownloadsStore } from '@/stores/downloads'
import DownloadItem from './DownloadItem.vue'

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
</script>

<template>
  <div class="download-queue">
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

    <div v-if="filteredJobs.length === 0" class="queue-empty">
      <template v-if="activeFilter === 'all'">
        No downloads yet. Paste a URL above to get started.
      </template>
      <template v-else>
        No {{ activeFilter }} downloads.
      </template>
    </div>

    <TransitionGroup name="job-list" tag="div" class="queue-list">
      <DownloadItem
        v-for="job in filteredJobs"
        :key="job.id"
        :job="job"
      />
    </TransitionGroup>
  </div>
</template>

<style scoped>
.download-queue {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.queue-filters {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
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

.queue-empty {
  padding: var(--space-xl);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* Transition animations */
.job-list-enter-active,
.job-list-leave-active {
  transition: all 0.3s ease;
}

.job-list-enter-from {
  opacity: 0;
  transform: translateY(-10px);
}

.job-list-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

.job-list-move {
  transition: transform 0.3s ease;
}

/* Mobile: full-width filters */
@media (max-width: 767px) {
  .queue-filters {
    overflow-x: auto;
    flex-wrap: nowrap;
    -webkit-overflow-scrolling: touch;
  }

  .filter-btn {
    min-height: var(--touch-min);
    flex-shrink: 0;
  }
}
</style>
