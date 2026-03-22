<script setup lang="ts">
import { onMounted } from 'vue'
import { useSSE } from '@/composables/useSSE'
import { useConfigStore } from '@/stores/config'
import { useDownloadsStore } from '@/stores/downloads'
import { useThemeStore } from '@/stores/theme'
import AppHeader from '@/components/AppHeader.vue'
import AppFooter from '@/components/AppFooter.vue'

const configStore = useConfigStore()
const downloadsStore = useDownloadsStore()
const themeStore = useThemeStore()
const { connect } = useSSE()

onMounted(async () => {
  // Apply theme from cookie immediately to prevent flash-of-wrong-theme
  themeStore.init()
  // Then load server config and re-apply with admin defaults
  await configStore.loadConfig()
  themeStore.init()
  await themeStore.loadCustomThemes()
  await downloadsStore.fetchJobs()
  connect()
})
</script>

<template>
  <div class="app-root">
    <AppHeader />
    <router-view />
    <AppFooter />
  </div>
</template>

<style>
.app-root {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
</style>
