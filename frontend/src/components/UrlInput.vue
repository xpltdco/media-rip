<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api/client'
import { useDownloadsStore } from '@/stores/downloads'
import FormatPicker from './FormatPicker.vue'
import type { FormatInfo } from '@/api/types'

const store = useDownloadsStore()

const url = ref('')
const formats = ref<FormatInfo[]>([])
const selectedFormatId = ref<string | null>(null)
const isExtracting = ref(false)
const extractError = ref<string | null>(null)
const showFormats = ref(false)

async function extractFormats(): Promise<void> {
  const trimmed = url.value.trim()
  if (!trimmed) return

  isExtracting.value = true
  extractError.value = null
  formats.value = []
  showFormats.value = false
  selectedFormatId.value = null

  try {
    formats.value = await api.getFormats(trimmed)
    showFormats.value = true
  } catch (err: any) {
    extractError.value = err.message || 'Failed to extract formats'
  } finally {
    isExtracting.value = false
  }
}

async function submitDownload(): Promise<void> {
  const trimmed = url.value.trim()
  if (!trimmed) return

  try {
    await store.submitDownload({
      url: trimmed,
      format_id: selectedFormatId.value,
    })
    // Reset form on success
    url.value = ''
    formats.value = []
    showFormats.value = false
    selectedFormatId.value = null
    extractError.value = null
  } catch {
    // Error already in store.submitError
  }
}

function onFormatSelect(formatId: string | null): void {
  selectedFormatId.value = formatId
}

function handlePaste(): void {
  // Auto-extract on paste after a tick (value not yet updated in paste event)
  setTimeout(() => {
    if (url.value.trim()) {
      extractFormats()
    }
  }, 50)
}
</script>

<template>
  <div class="url-input">
    <div class="input-row">
      <input
        v-model="url"
        type="url"
        placeholder="Paste a URL to download…"
        class="url-field"
        @paste="handlePaste"
        @keydown.enter="showFormats ? submitDownload() : extractFormats()"
        :disabled="isExtracting"
      />
      <button
        v-if="!showFormats"
        class="btn-extract"
        @click="extractFormats"
        :disabled="!url.trim() || isExtracting"
      >
        {{ isExtracting ? 'Extracting…' : 'Get Formats' }}
      </button>
      <button
        v-else
        class="btn-download"
        @click="submitDownload"
        :disabled="store.isSubmitting"
      >
        {{ store.isSubmitting ? 'Submitting…' : 'Download' }}
      </button>
    </div>

    <div v-if="isExtracting" class="extract-loading">
      <span class="spinner"></span>
      Extracting available formats…
    </div>

    <div v-if="extractError" class="extract-error">
      {{ extractError }}
    </div>

    <div v-if="store.submitError" class="extract-error">
      {{ store.submitError }}
    </div>

    <FormatPicker
      v-if="showFormats"
      :formats="formats"
      @select="onFormatSelect"
    />
  </div>
</template>

<style scoped>
.url-input {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  width: 100%;
}

.input-row {
  display: flex;
  gap: var(--space-sm);
}

.url-field {
  flex: 1;
  font-size: var(--font-size-base);
}

.btn-extract,
.btn-download {
  white-space: nowrap;
  padding: var(--space-sm) var(--space-lg);
  font-weight: 600;
}

.btn-extract {
  background: var(--color-surface);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
}

.btn-extract:hover:not(:disabled) {
  background: color-mix(in srgb, var(--color-accent) 15%, transparent);
}

.btn-download {
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

.extract-loading {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  padding: var(--space-sm);
}

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

/* Mobile: stack vertically */
@media (max-width: 767px) {
  .input-row {
    flex-direction: column;
  }

  .btn-extract,
  .btn-download {
    width: 100%;
  }
}
</style>
