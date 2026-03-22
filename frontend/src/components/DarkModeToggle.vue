<script setup lang="ts">
import { ref } from 'vue'
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()
const showPicker = ref(false)

function selectTheme(id: string) {
  theme.setTheme(id)
  showPicker.value = false
}

function closePicker() {
  showPicker.value = false
}
</script>

<template>
  <div class="theme-picker-wrapper" @mouseleave="closePicker">
    <button
      class="theme-toggle-btn"
      :title="'Theme: ' + (theme.currentMeta?.name || theme.currentTheme)"
      @click="showPicker = !showPicker"
      aria-label="Theme picker"
    >
      <!-- Sun icon (dark mode active) -->
      <svg v-if="theme.isDark" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/>
        <line x1="12" y1="1" x2="12" y2="3"/>
        <line x1="12" y1="21" x2="12" y2="23"/>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
        <line x1="1" y1="12" x2="3" y2="12"/>
        <line x1="21" y1="12" x2="23" y2="12"/>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
      </svg>
      <!-- Moon icon (light mode active) -->
      <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
      </svg>
    </button>

    <Transition name="fade">
      <div v-if="showPicker" class="theme-dropdown">
        <div class="theme-group">
          <div class="theme-group-label">Dark</div>
          <button
            v-for="t in theme.darkThemes"
            :key="t.id"
            class="theme-option"
            :class="{ active: theme.currentTheme === t.id }"
            @click="selectTheme(t.id)"
            :title="t.description"
          >
            <span class="theme-name">{{ t.name }}</span>
            <span v-if="theme.currentTheme === t.id" class="theme-check">✓</span>
          </button>
        </div>
        <div class="theme-divider"></div>
        <div class="theme-group">
          <div class="theme-group-label">Light</div>
          <button
            v-for="t in theme.lightThemes"
            :key="t.id"
            class="theme-option"
            :class="{ active: theme.currentTheme === t.id }"
            @click="selectTheme(t.id)"
            :title="t.description"
          >
            <span class="theme-name">{{ t.name }}</span>
            <span v-if="theme.currentTheme === t.id" class="theme-check">✓</span>
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.theme-picker-wrapper {
  position: relative;
}

.theme-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: transparent;
  color: var(--color-text-muted);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--transition-normal);
  padding: 0;
}

.theme-toggle-btn:hover {
  color: var(--color-accent);
}

.theme-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  min-width: 180px;
  z-index: 100;
  overflow: hidden;
}

.theme-group-label {
  padding: 8px 14px 4px;
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.theme-divider {
  height: 1px;
  background: var(--color-border);
  margin: 4px 0;
}

.theme-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 14px;
  background: transparent;
  color: var(--color-text);
  border: none;
  cursor: pointer;
  font-size: var(--font-size-sm);
  font-family: var(--font-ui);
  text-align: left;
  transition: background var(--transition-fast);
}

.theme-option:hover {
  background: var(--color-surface-hover);
}

.theme-option.active {
  color: var(--color-accent);
}

.theme-check {
  color: var(--color-accent);
  font-weight: bold;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
