<script setup lang="ts">
import { ref, computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useDownloadsStore } from '@/stores/downloads'
import WireframeBackground from './WireframeBackground.vue'

const themeStore = useThemeStore()
const downloadsStore = useDownloadsStore()
const showWireframe = computed(() => themeStore.currentTheme === 'cyberpunk')

type MobileTab = 'submit' | 'queue'
const activeTab = ref<MobileTab>('submit')

/** Number of active (non-terminal) jobs — shown as badge on Queue tab */
const queueBadge = computed(() => {
  let count = 0
  for (const job of downloadsStore.jobs.values()) {
    if (job.status === 'queued' || job.status === 'downloading' || job.status === 'extracting') {
      count++
    }
  }
  return count
})
</script>

<template>
  <div class="app-layout">
    <WireframeBackground v-if="showWireframe" />
    <!-- Desktop: single scrollable view -->
    <main class="layout-main">
      <!-- URL input section -->
      <section class="section-submit" :class="{ 'mobile-hidden': activeTab !== 'submit' }">
        <slot name="url-input"></slot>
      </section>

      <!-- Download queue section -->
      <section class="section-queue" :class="{ 'mobile-hidden': activeTab !== 'queue' }">
        <slot name="queue"></slot>
      </section>
    </main>

    <!-- Mobile bottom tab bar -->
    <nav class="mobile-nav">
      <button
        class="nav-tab"
        :class="{ active: activeTab === 'submit' }"
        @click="activeTab = 'submit'"
      >
        <span class="nav-icon">⬇</span>
        <span class="nav-label">Submit</span>
      </button>
      <button
        class="nav-tab"
        :class="{ active: activeTab === 'queue' }"
        @click="activeTab = 'queue'"
      >
        <span class="nav-icon-wrap">
          <span class="nav-icon">☰</span>
          <span v-if="queueBadge > 0 && activeTab !== 'queue'" class="nav-badge">{{ queueBadge > 9 ? '9+' : queueBadge }}</span>
        </span>
        <span class="nav-label">Queue</span>
      </button>
    </nav>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.layout-main {
  flex: 1;
  max-width: var(--content-max-width);
  width: 100%;
  margin: 0 auto;
  padding: var(--space-lg) var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
  position: relative;
  z-index: 1;
}

.section-submit,
.section-queue {
  width: 100%;
  min-width: 0;
}

/* Mobile navigation */
.mobile-nav {
  display: none;
}

/* Mobile: show bottom nav, toggle sections */
@media (max-width: 767px) {
  .layout-main {
    padding: var(--space-md);
    padding-bottom: calc(var(--mobile-nav-height) + var(--space-md));
    gap: var(--space-md);
  }

  .mobile-hidden {
    display: none;
  }

  .mobile-nav {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: var(--mobile-nav-height);
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
    z-index: 100;
  }

  .nav-tab {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    background: transparent;
    color: var(--color-text-muted);
    border: none;
    border-radius: 0;
    min-height: var(--mobile-nav-height);
    padding: var(--space-xs);
    font-size: var(--font-size-sm);
  }

  .nav-tab.active {
    color: var(--color-accent);
  }

  .nav-tab:hover {
    background: var(--color-surface-hover);
  }

  .nav-icon {
    font-size: 1.25rem;
  }

  .nav-label {
    font-size: 0.6875rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .nav-icon-wrap {
    position: relative;
    display: inline-flex;
  }

  .nav-badge {
    position: absolute;
    top: -6px;
    right: -10px;
    background: var(--color-accent);
    color: var(--color-bg);
    font-size: 0.6rem;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    line-height: 16px;
    text-align: center;
    border-radius: var(--radius-full);
    padding: 0 3px;
  }
}
</style>
