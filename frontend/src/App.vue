<script setup lang="ts">
import { onMounted } from 'vue'
import { useSSE } from '@/composables/useSSE'
import { useConfigStore } from '@/stores/config'
import { useThemeStore } from '@/stores/theme'
import AppHeader from '@/components/AppHeader.vue'
import AppFooter from '@/components/AppFooter.vue'

const configStore = useConfigStore()
const themeStore = useThemeStore()
const { connect } = useSSE()

onMounted(async () => {
  themeStore.init()
  await configStore.loadConfig()
  await themeStore.loadCustomThemes()
  connect()
})
</script>

<template>
  <AppHeader />
  <router-view />
  <AppFooter />
</template>
