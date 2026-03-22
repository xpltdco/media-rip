<script setup lang="ts">
import { useRouter } from 'vue-router'
import DarkModeToggle from '@/components/DarkModeToggle.vue'

const router = useRouter()

function goHome(): void {
  router.push('/')
}
</script>

<template>
  <header class="app-header">
    <div class="header-content">
      <h1 class="header-title" @click="goHome" role="link" tabindex="0" @keydown.enter="goHome" title="Back to downloads">
        <span class="title-media">media</span><span class="title-dot">.</span><span class="title-rip">rip</span><span class="title-parens">()</span>
      </h1>
      <div class="header-right">
        <DarkModeToggle />
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 100;
  width: 100%;
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

@media (max-width: 767px) {
  .header-content {
    max-width: none;
  }
}

.header-title {
  font-size: var(--font-size-xl);
  font-weight: 700;
  font-family: var(--font-display);
  letter-spacing: -0.02em;
  cursor: pointer;
  user-select: none;
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
</style>
