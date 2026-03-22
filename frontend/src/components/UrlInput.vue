<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/api/client'
import { useDownloadsStore } from '@/stores/downloads'
import { useConfigStore } from '@/stores/config'
import FormatPicker from './FormatPicker.vue'
import type { FormatInfo, UrlInfo } from '@/api/types'

const store = useDownloadsStore()
const configStore = useConfigStore()

const url = ref('')
const formats = ref<FormatInfo[]>([])
const selectedFormatId = ref<string | null>(null)
const extractError = ref<string | null>(null)
const showOptions = ref(false)

// URL preview state
const urlInfo = ref<UrlInfo | null>(null)
const audioLocked = ref(false)  // true when source is audio-only

// Unified loading state for URL check + format extraction
const isAnalyzing = ref(false)
const analyzePhase = ref<string>('')
const analyzeError = ref<string | null>(null)
const phaseMessages = [
  'Scanning the airwaves…',
  'Negotiating with the server…',
  'Cracking the codec…',
  'Reading the fine print…',
  'Locking on target…',
]
let phaseTimer: ReturnType<typeof setInterval> | null = null

function startAnalyzePhase(): void {
  let idx = 0
  analyzePhase.value = phaseMessages[0]
  phaseTimer = setInterval(() => {
    idx = Math.min(idx + 1, phaseMessages.length - 1)
    analyzePhase.value = phaseMessages[idx]
  }, 1500)
}

function stopAnalyzePhase(): void {
  if (phaseTimer) {
    clearInterval(phaseTimer)
    phaseTimer = null
  }
  analyzePhase.value = ''
}

type MediaType = 'video' | 'audio'
const mediaType = ref<MediaType>(
  (localStorage.getItem('mediarip:mediaType') as MediaType) || 'video'
)
const outputFormat = ref<string>(
  localStorage.getItem('mediarip:outputFormat') || 'auto'
)

const audioFormats = ['auto', 'mp3', 'wav', 'm4a', 'flac', 'opus'] as const
const videoFormats = ['auto', 'mp4', 'webm'] as const

const availableFormats = computed(() =>
  mediaType.value === 'audio' ? audioFormats : videoFormats
)

/** Resolve the actual output format to send to the backend.
 *  If 'auto' and admin has set a default, use that instead of null.
 */
const effectiveOutputFormat = computed(() => {
  if (outputFormat.value !== 'auto') return outputFormat.value
  const cfg = configStore.config
  if (!cfg) return null
  const adminDefault = mediaType.value === 'audio'
    ? cfg.default_audio_format
    : cfg.default_video_format
  return adminDefault && adminDefault !== 'auto' ? adminDefault : null
})

// Persist preferences and reset output format when switching media type
watch(mediaType, (val) => {
  localStorage.setItem('mediarip:mediaType', val)
  outputFormat.value = 'auto'
})
watch(outputFormat, (val) => {
  localStorage.setItem('mediarip:outputFormat', val)
})

// Clear preview and formats when URL is emptied or changed manually
let lastFetchedUrl = ''
watch(url, (newUrl) => {
  const trimmed = newUrl.trim()
  if (!trimmed) {
    // URL cleared — reset everything
    urlInfo.value = null
    formats.value = []
    selectedFormatId.value = null
    extractError.value = null
    analyzeError.value = null
    audioLocked.value = false
    showOptions.value = false
    selectedEntries.value = new Set()
  } else if (trimmed !== lastFetchedUrl) {
    // URL changed to something different — clear stale preview
    urlInfo.value = null
    formats.value = []
    selectedFormatId.value = null
    extractError.value = null
    analyzeError.value = null
    audioLocked.value = false
    selectedEntries.value = new Set()
  }
})

// Playlist entry selection state
const selectedEntries = ref<Set<number>>(new Set())

/** Whether formats have been fetched for the current URL. */
const formatsReady = computed(() => formats.value.length > 0)

/** URL has been analyzed and content was found. */
const urlReady = computed(() =>
  !!urlInfo.value && urlInfo.value.type !== 'unknown'
)

async function extractFormats(): Promise<void> {
  const trimmed = url.value.trim()
  if (!trimmed) return

  extractError.value = null
  formats.value = []
  selectedFormatId.value = null

  try {
    formats.value = await api.getFormats(trimmed)
  } catch (err: any) {
    extractError.value = err.message || 'Failed to extract formats'
  }
}

async function submitDownload(): Promise<void> {
  const trimmed = url.value.trim()
  if (!trimmed) return

  try {
    // If playlist with selection, submit only selected entries
    if (urlInfo.value?.type === 'playlist' && urlInfo.value.entries.length > 0) {
      const selected = urlInfo.value.entries.filter((_, i) => selectedEntries.value.has(i))
      for (const entry of selected) {
        await store.submitDownload({
          url: entry.url,
          format_id: selectedFormatId.value,
          quality: mediaType.value === 'audio' && !selectedFormatId.value ? 'bestaudio' : null,
          media_type: mediaType.value,
          output_format: effectiveOutputFormat.value,
        })
      }
    } else {
      await store.submitDownload({
        url: trimmed,
        format_id: selectedFormatId.value,
        quality: mediaType.value === 'audio' && !selectedFormatId.value ? 'bestaudio' : null,
        media_type: mediaType.value,
        output_format: effectiveOutputFormat.value,
      })
    }
    // Reset form on success
    url.value = ''
    formats.value = []
    showOptions.value = false
    selectedFormatId.value = null
    extractError.value = null
    urlInfo.value = null
    audioLocked.value = false
    selectedEntries.value = new Set()
    lastFetchedUrl = ''
  } catch {
    // Error already in store.submitError
  }
}

function onFormatSelect(formatId: string | null): void {
  selectedFormatId.value = formatId
}

function handlePaste(): void {
  // Auto-extract on paste — unified loading state
  setTimeout(async () => {
    if (url.value.trim()) {
      isAnalyzing.value = true
      analyzeError.value = null
      startAnalyzePhase()
      try {
        await Promise.all([extractFormats(), fetchUrlInfo()])
        // Check if URL yielded anything useful
        if (urlInfo.value?.type === 'unknown') {
          analyzeError.value = (urlInfo.value as any)?.hint
            || 'No downloadable media found at this URL.'
          urlInfo.value = null
        } else if (!urlInfo.value && !extractError.value) {
          analyzeError.value = 'Could not reach this URL. Check the address and try again.'
        }
      } finally {
        isAnalyzing.value = false
        stopAnalyzePhase()
      }
    }
  }, 50)
}

async function fetchUrlInfo(): Promise<void> {
  const trimmed = url.value.trim()
  if (!trimmed) return
  urlInfo.value = null
  audioLocked.value = false
  selectedEntries.value = new Set()
  try {
    const info = await api.getUrlInfo(trimmed)
    urlInfo.value = info
    lastFetchedUrl = trimmed
    // Auto-switch to audio if the source is audio-only
    if (info.is_audio_only) {
      mediaType.value = 'audio'
      audioLocked.value = true
    }
    // Select all playlist entries by default
    if (info.type === 'playlist' && info.entries.length) {
      selectedEntries.value = new Set(info.entries.map((_, i) => i))
    }
  } catch {
    // Non-critical — preview is optional
  }
}

function toggleEntry(index: number): void {
  const s = new Set(selectedEntries.value)
  if (s.has(index)) {
    s.delete(index)
  } else {
    s.add(index)
  }
  selectedEntries.value = s
}

function selectAllEntries(): void {
  if (!urlInfo.value) return
  selectedEntries.value = new Set(urlInfo.value.entries.map((_, i) => i))
}

function selectNoneEntries(): void {
  selectedEntries.value = new Set()
}

const allEntriesSelected = computed(() =>
  urlInfo.value ? selectedEntries.value.size === urlInfo.value.entries.length : false
)
const someEntriesSelected = computed(() => selectedEntries.value.size > 0)

function formatDuration(seconds: number | null): string {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function toggleOptions(): void {
  showOptions.value = !showOptions.value
  // Extract formats when opening options if we haven't yet
  if (showOptions.value && !formatsReady.value && url.value.trim() && !isAnalyzing.value) {
    extractFormats()
  }
}

function formatLabel(fmt: string): string {
  if (fmt === 'auto') {
    // Show what format will actually be used
    const effective = effectiveOutputFormat.value
    if (effective) {
      return `Auto (.${effective})`
    }
    if (urlInfo.value?.default_ext) {
      return `Auto (.${urlInfo.value.default_ext})`
    }
    return 'Auto'
  }
  return fmt.toUpperCase()
}

function formatTooltip(fmt: string): string {
  if (fmt !== 'auto') return `Convert to ${fmt.toUpperCase()}`
  return ''
}
</script>

<template>
  <div class="url-input">
    <!-- URL field -->
    <input
      v-model="url"
      type="url"
      placeholder="Paste a URL to download…"
      class="url-field"
      @paste="handlePaste"
      @keydown.enter="submitDownload"
      :disabled="isAnalyzing || store.isSubmitting"
    />

    <!-- Action row: gear, media toggle, download button -->
    <div class="action-row">
      <button
        class="btn-options"
        :class="{ active: showOptions }"
        @click="toggleOptions"
        :disabled="!url.trim()"
        title="Format options"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      </button>

      <div class="media-toggle">
        <button
          class="toggle-pill"
          :class="{ active: mediaType === 'video', disabled: audioLocked }"
          @click="!audioLocked && (mediaType = 'video')"
          :title="audioLocked ? 'Source contains audio only' : 'Video'"
          :disabled="audioLocked"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>
          <span class="toggle-label">Video</span>
        </button>
        <button
          class="toggle-pill"
          :class="{ active: mediaType === 'audio' }"
          @click="mediaType = 'audio'"
          :title="'Audio'"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
          <span class="toggle-label">Audio</span>
        </button>
      </div>

      <button
        class="btn-download"
        @click="submitDownload"
        :disabled="!urlReady || isAnalyzing || store.isSubmitting"
      >
        {{ store.isSubmitting ? 'Submitting…' : 'Download' }}
      </button>
    </div>

    <!-- Unified analyzing state -->
    <div v-if="isAnalyzing" class="url-preview loading">
      <span class="spinner"></span>
      {{ analyzePhase }}
    </div>

    <!-- URL preview: show what will be downloaded -->
    <div v-else-if="urlInfo" class="url-preview">
      <div class="preview-header">
        <span v-if="urlInfo.type === 'playlist'" class="preview-badge playlist">Playlist · {{ urlInfo.count }} items</span>
        <span v-else class="preview-badge single">{{ audioLocked ? 'Track' : 'Video' }}</span>
        <span v-if="audioLocked" class="preview-badge audio-only">Audio only</span>
        <span v-if="urlInfo.title" class="preview-title">{{ urlInfo.title }}</span>
        <span v-if="urlInfo.type === 'single' && urlInfo.duration" class="preview-duration">({{ formatDuration(urlInfo.duration ?? null) }})</span>
      </div>
      <div v-if="urlInfo.type === 'playlist' && urlInfo.entries.length" class="preview-entries">
        <div class="preview-controls">
          <label class="select-all-check" @click.prevent="allEntriesSelected ? selectNoneEntries() : selectAllEntries()">
            <span class="check-box" :class="{ checked: allEntriesSelected, partial: !allEntriesSelected && someEntriesSelected }">
              {{ allEntriesSelected ? '✓' : (!allEntriesSelected && someEntriesSelected ? '–' : '') }}
            </span>
            <span class="select-label">{{ allEntriesSelected ? 'Deselect all' : 'Select all' }}</span>
          </label>
          <span class="selected-count">{{ selectedEntries.size }} of {{ urlInfo.entries.length }} selected</span>
        </div>
        <div
          v-for="(entry, i) in urlInfo.entries.slice(0, 20)"
          :key="i"
          class="preview-entry"
          @click="toggleEntry(i)"
        >
          <span class="check-box" :class="{ checked: selectedEntries.has(i) }">
            {{ selectedEntries.has(i) ? '✓' : '' }}
          </span>
          <span class="entry-num">{{ i + 1 }}.</span>
          <span class="entry-title">{{ entry.title }}</span>
          <span v-if="entry.duration" class="entry-duration">({{ formatDuration(entry.duration) }})</span>
        </div>
        <div v-if="urlInfo.entries.length > 20" class="preview-more">
          …and {{ urlInfo.entries.length - 20 }} more
        </div>
        <div v-if="urlInfo.unavailable_count" class="preview-warning">
          ⚠ {{ urlInfo.unavailable_count }} private/unavailable item{{ urlInfo.unavailable_count > 1 ? 's' : '' }} skipped
        </div>
      </div>
    </div>

    <!-- Error feedback — shown in preview area style -->
    <div v-if="analyzeError && !isAnalyzing" class="url-preview error-preview">
      {{ analyzeError }}
    </div>

    <div v-if="extractError" class="extract-error">
      {{ extractError }}
    </div>

    <div v-if="store.submitError" class="extract-error">
      {{ store.submitError }}
    </div>

    <!-- Collapsible options panel (hidden when URL is invalid) -->
    <Transition name="options-slide">
      <div v-if="showOptions && !analyzeError" class="options-panel">
        <!-- Output format selector -->
        <div class="format-selector">
          <label class="format-label">Output format</label>
          <div class="format-chips">
            <button
              v-for="fmt in availableFormats"
              :key="fmt"
              class="format-chip"
              :class="{ active: outputFormat === fmt }"
              :title="formatTooltip(fmt)"
              @click="outputFormat = fmt"
            >
              {{ formatLabel(fmt) }}
            </button>
          </div>
        </div>

        <!-- Advanced format picker from yt-dlp extract_info -->
        <FormatPicker
          v-if="formatsReady"
          :formats="formats"
          :media-type="mediaType"
          @select="onFormatSelect"
        />
        <div v-else-if="!isAnalyzing" class="options-hint">
          Paste a URL and formats will load automatically.
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.url-input {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  width: 100%;
}

.url-field {
  width: 100%;
  font-size: var(--font-size-base);
}

/* Action row: gear | toggle | download */
.action-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.btn-options {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  padding: 0;
  flex-shrink: 0;
  background: var(--color-surface);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: all 0.15s ease;
}

.btn-options:hover:not(:disabled) {
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.btn-options.active {
  color: var(--color-accent);
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.media-toggle {
  display: flex;
  gap: 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}

.toggle-pill {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-surface);
  color: var(--color-text-muted);
  border: none;
  border-radius: 0;
  font-size: var(--font-size-sm);
  min-height: 38px;
  transition: all 0.15s ease;
}

.toggle-pill:not(:last-child) {
  border-right: 1px solid var(--color-border);
}

.toggle-pill:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.toggle-pill.active {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
}

.toggle-label {
  /* Visible by default, hidden at narrow widths */
}

.btn-download {
  flex: 1;
  white-space: nowrap;
  padding: var(--space-sm) var(--space-lg);
  font-weight: 600;
  min-height: 38px;
  background: var(--color-accent);
  color: var(--color-bg);
}

.btn-download:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Loading / errors */
.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.extract-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  padding: var(--space-sm);
}

/* Options panel */
.options-panel {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.format-selector {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-sm) 0;
}

.format-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.format-chips {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.format-chip {
  padding: var(--space-xs) var(--space-md);
  font-size: var(--font-size-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
  min-height: 30px;
}

.format-chip:hover {
  color: var(--color-text);
  border-color: var(--color-text-muted);
}

.format-chip.active {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.options-slide-enter-active,
.options-slide-leave-active {
  transition: all 0.25s ease;
}

.options-slide-enter-from,
.options-slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.options-slide-enter-to,
.options-slide-leave-from {
  opacity: 1;
  max-height: 400px;
}

.options-hint {
  padding: var(--space-md);
  text-align: center;
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

/* URL preview */
.url-preview {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
}

.url-preview.loading {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-muted);
}

.url-preview.error-preview {
  color: var(--color-error);
  font-size: var(--font-size-sm);
}

.preview-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  flex-wrap: wrap;
}

.preview-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  white-space: nowrap;
}

.preview-badge.playlist {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
  color: var(--color-accent);
}

.preview-badge.single {
  background: color-mix(in srgb, var(--color-text-muted) 15%, transparent);
  color: var(--color-text-muted);
}

.preview-badge.audio-only {
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
}

.preview-title {
  color: var(--color-text);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-entries {
  margin-top: var(--space-xs);
  display: flex;
  flex-direction: column;
  gap: 1px;
  max-height: 260px;
  overflow-y: auto;
}

.preview-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-xs) 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: var(--space-xs);
}

.select-all-check {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  cursor: pointer;
  user-select: none;
}

.select-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.selected-count {
  font-size: 11px;
  color: var(--color-text-muted);
}

.check-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--color-border);
  border-radius: 3px;
  font-size: 11px;
  color: var(--color-bg);
  flex-shrink: 0;
  transition: all 0.15s;
}

.check-box.checked {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.check-box.partial {
  background: var(--color-text-muted);
  border-color: var(--color-text-muted);
}

.preview-entry {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 3px 0;
  color: var(--color-text-muted);
  cursor: pointer;
  user-select: none;
}

.preview-entry:hover {
  color: var(--color-text);
}

.entry-num {
  min-width: 24px;
  text-align: right;
  color: var(--color-text-muted);
  opacity: 0.6;
}

.entry-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-duration {
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  opacity: 0.6;
}

.preview-more {
  padding: var(--space-xs) 0;
  color: var(--color-text-muted);
  font-style: italic;
}

.preview-warning {
  padding: var(--space-xs) var(--space-sm);
  margin-top: var(--space-xs);
  color: var(--color-warning);
  font-size: var(--font-size-sm);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border-radius: var(--radius-sm);
}

.toggle-pill.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Narrow viewports: hide toggle labels, keep icons only */
@media (max-width: 540px) {
  .toggle-label {
    display: none;
  }

  .toggle-pill {
    padding: var(--space-xs) var(--space-sm);
  }
}

/* Mobile */
@media (max-width: 767px) {
  .btn-download {
    padding: var(--space-sm) var(--space-md);
  }
}
</style>
