<script setup lang="ts">
import AppLayout from '@/components/AppLayout.vue'
import WelcomeMessage from '@/components/WelcomeMessage.vue'
import UrlInput from '@/components/UrlInput.vue'
import DownloadQueue from '@/components/DownloadQueue.vue'
</script>

<template>
  <AppLayout>
    <template #url-input>
      <WelcomeMessage />
      <UrlInput />
    </template>
    <template #queue>
      <DownloadQueue />
    </template>
  </AppLayout>
</template>
