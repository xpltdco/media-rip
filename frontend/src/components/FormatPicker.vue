<script setup lang="ts">
import { ref, computed } from 'vue'
import type { FormatInfo } from '@/api/types'

const props = defineProps<{
  formats: FormatInfo[]
  mediaType?: 'video' | 'audio'
}>()

const emit = defineEmits<{
  select: [formatId: string | null]
}>()

const selectedId = ref<string | null>(null)

// Group formats: video+audio, video-only, audio-only
const videoFormats = computed(() =>
  props.formats.filter(
    (f) => f.vcodec && f.vcodec !== 'none' && f.acodec && f.acodec !== 'none',
  ),
)

const videoOnlyFormats = computed(() =>
  props.formats.filter(
    (f) => f.vcodec && f.vcodec !== 'none' && (!f.acodec || f.acodec === 'none'),
  ),
)

const audioFormats = computed(() =>
  props.formats.filter(
    (f) => (!f.vcodec || f.vcodec === 'none') && f.acodec && f.acodec !== 'none',
  ),
)

// Filter visibility based on mediaType prop
const showVideo = computed(() => !props.mediaType || props.mediaType === 'video')
const showAudio = computed(() => !props.mediaType || props.mediaType === 'audio')

function formatLabel(f: FormatInfo): string {
  const parts: string[] = []
  if (f.resolution) parts.push(f.resolution)
  if (f.ext) parts.push(f.ext)
  if (f.format_note) parts.push(f.format_note)
  if (f.filesize) parts.push(formatBytes(f.filesize))
  return parts.join(' · ') || f.format_id
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function selectFormat(id: string | null): void {
  selectedId.value = id
  emit('select', id)
}
</script>

<template>
  <div class="format-picker">
    <div class="format-option" :class="{ selected: selectedId === null }" @click="selectFormat(null)">
      <span class="format-label">Best available</span>
      <span class="format-hint">Let yt-dlp choose the best quality</span>
    </div>

    <template v-if="showVideo && videoFormats.length > 0">
      <div class="format-group-label">Video + Audio</div>
      <div
        v-for="f in videoFormats"
        :key="f.format_id"
        class="format-option"
        :class="{ selected: selectedId === f.format_id }"
        @click="selectFormat(f.format_id)"
      >
        <span class="format-label">{{ formatLabel(f) }}</span>
        <span class="format-codecs">{{ f.vcodec }} + {{ f.acodec }}</span>
      </div>
    </template>

    <template v-if="showVideo && videoOnlyFormats.length > 0">
      <div class="format-group-label">Video only</div>
      <div
        v-for="f in videoOnlyFormats"
        :key="f.format_id"
        class="format-option"
        :class="{ selected: selectedId === f.format_id }"
        @click="selectFormat(f.format_id)"
      >
        <span class="format-label">{{ formatLabel(f) }}</span>
        <span class="format-codecs">{{ f.vcodec }}</span>
      </div>
    </template>

    <template v-if="showAudio && audioFormats.length > 0">
      <div class="format-group-label">Audio only</div>
      <div
        v-for="f in audioFormats"
        :key="f.format_id"
        class="format-option"
        :class="{ selected: selectedId === f.format_id }"
        @click="selectFormat(f.format_id)"
      >
        <span class="format-label">{{ formatLabel(f) }}</span>
        <span class="format-codecs">{{ f.acodec }}</span>
      </div>
    </template>

    <div v-if="formats.length === 0" class="format-empty">
      No specific formats available — best quality will be used.
    </div>
  </div>
</template>

<style scoped>
.format-picker {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  max-height: 300px;
  overflow-y: auto;
  padding: var(--space-sm);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.format-group-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: var(--space-sm) var(--space-sm) var(--space-xs);
  margin-top: var(--space-sm);
}

.format-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-sm);
  cursor: pointer;
  min-height: var(--touch-min);
  transition: background-color 0.15s ease;
}

.format-option:hover {
  background: var(--color-surface-hover);
}

.format-option.selected {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  outline: 1px solid var(--color-accent);
}

.format-label {
  font-size: var(--font-size-base);
}

.format-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.format-codecs {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.format-empty {
  padding: var(--space-md);
  color: var(--color-text-muted);
  text-align: center;
  font-size: var(--font-size-sm);
}
</style>
