<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()
</script>

<template>
  <div class="theme-picker">
    <button
      v-for="t in theme.allThemes"
      :key="t.id"
      :class="['theme-btn', { active: theme.currentTheme === t.id }]"
      :title="t.description || t.name"
      @click="theme.setTheme(t.id)"
    >
      <span class="theme-dot" :data-preview="t.id"></span>
      <span class="theme-name">{{ t.name }}</span>
    </button>
  </div>
</template>

<style scoped>
.theme-picker {
  display: flex;
  gap: var(--space-xs);
}

.theme-btn {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-sm);
  min-height: 32px;
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: all var(--transition-normal);
}

.theme-btn:hover {
  color: var(--color-text);
  border-color: var(--color-border);
}

.theme-btn.active {
  color: var(--color-accent);
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 8%, transparent);
}

.theme-dot {
  width: 12px;
  height: 12px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  flex-shrink: 0;
}

/* Preview dots show the theme's accent color */
.theme-dot[data-preview="cyberpunk"] {
  background: #00a8ff;
  border-color: #00a8ff;
}

.theme-dot[data-preview="dark"] {
  background: #a78bfa;
  border-color: #a78bfa;
}

.theme-dot[data-preview="light"] {
  background: #2563eb;
  border-color: #2563eb;
}

/* Custom theme dots fall back to a generic style */
.theme-dot:not([data-preview="cyberpunk"]):not([data-preview="dark"]):not([data-preview="light"]) {
  background: var(--color-text-muted);
}

.theme-name {
  white-space: nowrap;
}

/* On mobile, hide theme names — show only dots */
@media (max-width: 768px) {
  .theme-name {
    display: none;
  }

  .theme-btn {
    padding: var(--space-xs);
    min-height: var(--touch-min);
    min-width: var(--touch-min);
    justify-content: center;
  }

  .theme-dot {
    width: 16px;
    height: 16px;
  }
}
</style>
