<script setup lang="ts">
import { ref } from 'vue'

type MobileTab = 'submit' | 'queue'
const activeTab = ref<MobileTab>('submit')
</script>

<template>
  <div class="app-layout">
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
        <span class="nav-icon">☰</span>
        <span class="nav-label">Queue</span>
      </button>
    </nav>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - var(--header-height));
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
}

.section-submit,
.section-queue {
  width: 100%;
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
}
</style>
