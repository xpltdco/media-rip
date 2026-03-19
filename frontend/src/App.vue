<script setup lang="ts">
import { onMounted } from 'vue'
import { useSSE } from '@/composables/useSSE'
import { useConfigStore } from '@/stores/config'
import { useThemeStore } from '@/stores/theme'
import AppHeader from '@/components/AppHeader.vue'

const configStore = useConfigStore()
const themeStore = useThemeStore()
const { connectionStatus, connect } = useSSE()

onMounted(async () => {
  themeStore.init()
  await configStore.loadConfig()
  await themeStore.loadCustomThemes()
  connect()
})
</script>

<template>
  <AppHeader :connection-status="connectionStatus" />
  <nav class="app-nav">
    <router-link to="/">Downloads</router-link>
    <router-link to="/admin">Admin</router-link>
  </nav>
  <router-view />
</template>

<style scoped>
.app-nav {
  display: flex;
  gap: var(--space-md);
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid var(--color-border);
}

.app-nav a {
  padding: var(--space-xs) var(--space-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.app-nav a.router-link-active {
  color: var(--color-accent);
  border-bottom: 2px solid var(--color-accent);
}
</style>
