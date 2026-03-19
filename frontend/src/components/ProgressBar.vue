<script setup lang="ts">
const props = defineProps<{
  percent: number
}>()
</script>

<template>
  <div class="progress-bar">
    <div
      class="progress-fill"
      :style="{ width: `${Math.min(percent, 100)}%` }"
      :class="{
        complete: percent >= 100,
        indeterminate: percent <= 0,
      }"
    ></div>
    <span class="progress-text">{{ percent.toFixed(1) }}%</span>
  </div>
</template>

<style scoped>
.progress-bar {
  position: relative;
  height: 24px;
  background: var(--color-surface);
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--color-border);
}

.progress-fill {
  height: 100%;
  background: var(--color-accent);
  border-radius: var(--radius-sm);
  transition: width 0.3s ease;
}

.progress-fill.complete {
  background: var(--color-success);
}

.progress-fill.indeterminate {
  width: 30% !important;
  animation: indeterminate 1.5s ease-in-out infinite;
}

@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

.progress-text {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: var(--font-size-sm);
  font-family: var(--font-mono);
  color: var(--color-text);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
}
</style>
