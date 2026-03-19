<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

const appVersion = ref('')
const ytDlpVersion = ref('')

onMounted(async () => {
  try {
    const health = await api.getHealth()
    appVersion.value = health.version
    ytDlpVersion.value = health.yt_dlp_version
  } catch {
    appVersion.value = '?.?.?'
    ytDlpVersion.value = 'unknown'
  }
})
</script>

<template>
  <footer v-if="appVersion" class="app-footer">
    <span>media.rip() v{{ appVersion }}</span>
    <span class="sep">|</span>
    <span>yt-dlp {{ ytDlpVersion }}</span>
    <span class="sep">|</span>
    <a
      href="https://github.com/jlightner/media-rip"
      target="_blank"
      rel="noopener noreferrer"
    >GitHub</a>
  </footer>
</template>

<style scoped>
.app-footer {
  text-align: center;
  padding: var(--space-lg) var(--space-md);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  opacity: 0.7;
}

.sep {
  margin: 0 var(--space-sm);
  opacity: 0.5;
}

.app-footer a {
  color: var(--color-text-muted);
  text-decoration: none;
  transition: color var(--transition-normal);
}

.app-footer a:hover {
  color: var(--color-accent);
}
</style>
