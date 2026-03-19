<script setup lang="ts">
import AppLayout from '@/components/AppLayout.vue'
import UrlInput from '@/components/UrlInput.vue'
import DownloadQueue from '@/components/DownloadQueue.vue'
</script>

<template>
  <AppLayout connection-status="connected">
    <template #url-input>
      <UrlInput />
    </template>
    <template #queue>
      <DownloadQueue />
    </template>
  </AppLayout>
</template>
