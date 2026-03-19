<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'

const message = ref('Paste any video or audio URL. We rip it, you download it. No accounts, no tracking.')
const visible = ref(true)

onMounted(async () => {
  try {
    const config = await api.getPublicConfig()
    if (config.welcome_message !== undefined && config.welcome_message !== null) {
      if (config.welcome_message === '') {
        visible.value = false
      } else {
        message.value = config.welcome_message
      }
    }
  } catch {
    // Use default message on error
  }
})
</script>

<template>
  <div v-if="visible" class="welcome-message">
    <p>{{ message }}</p>
  </div>
</template>

<style scoped>
.welcome-message {
  text-align: center;
  padding: var(--space-md) var(--space-lg);
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
  line-height: 1.6;
  max-width: 600px;
  margin: 0 auto;
}

.welcome-message p {
  margin: 0;
}
</style>
