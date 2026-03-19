<script setup lang="ts">
import type { ConnectionStatus } from '@/composables/useSSE'
import ThemePicker from '@/components/ThemePicker.vue'

const props = defineProps<{
  connectionStatus: ConnectionStatus
}>()

const statusColor: Record<ConnectionStatus, string> = {
  connected: 'var(--color-success)',
  connecting: 'var(--color-warning)',
  reconnecting: 'var(--color-warning)',
  disconnected: 'var(--color-error)',
}
</script>

<template>
  <header class="app-header">
    <div class="header-content">
      <h1 class="header-title">
        <span class="title-media">media</span><span class="title-dot">.</span><span class="title-rip">rip</span><span class="title-parens">()</span>
      </h1>
      <div class="header-right">
        <ThemePicker />
        <div class="header-status" :title="`SSE: ${connectionStatus}`">
          <span
            class="status-dot"
            :style="{ backgroundColor: statusColor[connectionStatus] }"
          ></span>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  height: var(--header-height);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
}

.header-content {
  width: 100%;
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: 0 var(--space-md);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  font-family: var(--font-display);
  letter-spacing: -0.02em;
}

.title-media { color: var(--color-text); }
.title-dot { color: var(--color-accent); }
.title-rip { color: var(--color-accent); }
.title-parens { color: var(--color-text-muted); }

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.header-status {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  transition: background-color 0.3s ease;
}
</style>
