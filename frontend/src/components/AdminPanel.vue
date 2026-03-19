<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import { useConfigStore } from '@/stores/config'
import { api } from '@/api/client'
import AdminLogin from './AdminLogin.vue'

const store = useAdminStore()
const configStore = useConfigStore()
const router = useRouter()
const activeTab = ref<'sessions' | 'storage' | 'purge' | 'settings'>('sessions')

// Session expansion state
const expandedSessions = ref<Set<string>>(new Set())
const sessionJobs = ref<Record<string, any[]>>({})
const loadingJobs = ref<Set<string>>(new Set())

// Settings state
const welcomeMessage = ref('')
const defaultVideoFormat = ref('auto')
const defaultAudioFormat = ref('auto')
const settingsSaved = ref(false)

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

async function switchTab(tab: typeof activeTab.value) {
  activeTab.value = tab
  settingsSaved.value = false
  if (tab === 'sessions') await store.loadSessions()
  if (tab === 'storage') await store.loadStorage()
  if (tab === 'settings') {
    try {
      const config = await api.getPublicConfig()
      welcomeMessage.value = config.welcome_message
      defaultVideoFormat.value = config.default_video_format || 'auto'
      defaultAudioFormat.value = config.default_audio_format || 'auto'
    } catch {
      // Keep current value
    }
  }
}

async function saveSettings() {
  settingsSaved.value = false
  const ok = await store.updateSettings({
    welcome_message: welcomeMessage.value,
    default_video_format: defaultVideoFormat.value,
    default_audio_format: defaultAudioFormat.value,
  })
  if (ok) {
    // Reload public config so main page picks up new defaults
    await configStore.loadConfig()
    settingsSaved.value = true
    setTimeout(() => { settingsSaved.value = false }, 3000)
  }
}

async function toggleSession(sessionId: string) {
  if (expandedSessions.value.has(sessionId)) {
    expandedSessions.value.delete(sessionId)
    return
  }
  expandedSessions.value.add(sessionId)
  if (!sessionJobs.value[sessionId]) {
    loadingJobs.value.add(sessionId)
    try {
      const res = await fetch(`/api/admin/sessions/${sessionId}/jobs`, {
        headers: { Authorization: `Basic ${btoa(`${store.username}:${store.password}`)}` },
      })
      if (res.ok) {
        const data = await res.json()
        sessionJobs.value[sessionId] = data.jobs
      }
    } catch { /* ignore */ }
    loadingJobs.value.delete(sessionId)
  }
}

function jobFilename(job: any): string {
  if (!job.filename) return '—'
  const parts = job.filename.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1]
}

function formatFilesize(bytes: number | null): string {
  if (!bytes) return '—'
  return formatBytes(bytes)
}
</script>

<template>
  <div class="admin-panel">
    <AdminLogin v-if="!store.isAuthenticated" />

    <template v-else>
      <div class="admin-header">
        <h2>Admin Panel</h2>
        <button class="btn-logout" @click="store.logout(); router.push('/')">Logout</button>
      </div>

      <div class="admin-tabs">
        <button
          v-for="tab in (['sessions', 'storage', 'purge', 'settings'] as const)"
          :key="tab"
          :class="{ active: activeTab === tab }"
          @click="switchTab(tab)"
        >
          {{ tab }}
        </button>
      </div>

      <!-- Sessions tab -->
      <div v-if="activeTab === 'sessions'" class="tab-content">
        <table class="admin-table" v-if="store.sessions.length">
          <thead>
            <tr>
              <th></th>
              <th>Session ID</th>
              <th>Last Seen</th>
              <th>Jobs</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="s in store.sessions" :key="s.id">
              <tr
                class="session-row"
                :class="{ expanded: expandedSessions.has(s.id), clickable: s.job_count > 0 }"
                @click="s.job_count > 0 && toggleSession(s.id)"
              >
                <td class="col-expand">
                  <span v-if="s.job_count > 0" class="expand-icon">{{ expandedSessions.has(s.id) ? '▼' : '▶' }}</span>
                </td>
                <td class="mono">{{ s.id.slice(0, 8) }}…</td>
                <td>{{ new Date(s.last_seen).toLocaleString() }}</td>
                <td>{{ s.job_count }}</td>
              </tr>
              <tr v-if="expandedSessions.has(s.id)" class="jobs-detail-row">
                <td colspan="4">
                  <div v-if="loadingJobs.has(s.id)" class="jobs-loading">Loading…</div>
                  <div v-else-if="sessionJobs[s.id]?.length" class="jobs-detail">
                    <div v-for="job in sessionJobs[s.id]" :key="job.id" class="job-item">
                      <span class="job-filename">{{ jobFilename(job) }}</span>
                      <span class="job-size">{{ formatFilesize(job.filesize) }}</span>
                      <span class="job-status badge-sm" :class="'badge-' + job.status">{{ job.status }}</span>
                      <span class="job-time">{{ new Date(job.created_at).toLocaleString() }}</span>
                      <a v-if="job.url" class="job-url" :href="job.url" target="_blank" rel="noopener" :title="job.url">↗</a>
                    </div>
                  </div>
                  <div v-else class="jobs-empty">No jobs found.</div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <p v-else class="empty">No sessions found.</p>
      </div>

      <!-- Storage tab -->
      <div v-if="activeTab === 'storage'" class="tab-content">
        <div v-if="store.storage" class="storage-info">
          <div class="stat">
            <span class="stat-label">Total</span>
            <span class="stat-value">{{ formatBytes(store.storage.disk.total) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Used</span>
            <span class="stat-value">{{ formatBytes(store.storage.disk.used) }}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Free</span>
            <span class="stat-value">{{ formatBytes(store.storage.disk.free) }}</span>
          </div>
          <h3>Jobs by Status</h3>
          <div v-for="(count, status) in store.storage.jobs_by_status" :key="status" class="stat">
            <span class="stat-label">{{ status }}</span>
            <span class="stat-value">{{ count }}</span>
          </div>
        </div>
        <p v-else class="empty">Loading…</p>
      </div>

      <!-- Purge tab -->
      <div v-if="activeTab === 'purge'" class="tab-content">
        <p>Manually trigger a purge of expired downloads.</p>
        <button
          @click="store.triggerPurge()"
          :disabled="store.isLoading"
          class="btn-purge"
        >
          {{ store.isLoading ? 'Purging…' : 'Run Purge' }}
        </button>
        <div v-if="store.purgeResult" class="purge-result">
          <p>Rows deleted: {{ store.purgeResult.rows_deleted }}</p>
          <p>Files deleted: {{ store.purgeResult.files_deleted }}</p>
          <p>Files already gone: {{ store.purgeResult.files_missing }}</p>
          <p>Active jobs skipped: {{ store.purgeResult.active_skipped }}</p>
        </div>
      </div>

      <!-- Settings tab -->
      <div v-if="activeTab === 'settings'" class="tab-content">
        <div class="settings-field">
          <label for="welcome-msg">Welcome Message</label>
          <p class="field-hint">Displayed above the URL input on the main page. Leave empty to hide.</p>
          <textarea
            id="welcome-msg"
            v-model="welcomeMessage"
            rows="3"
            class="settings-textarea"
            placeholder="Enter a welcome message…"
          ></textarea>
        </div>

        <div class="settings-field" style="margin-top: var(--space-lg);">
          <label>Default Output Formats</label>
          <p class="field-hint">When "Auto" is selected, files are converted to these formats instead of the native container.</p>
          <div class="format-defaults">
            <div class="format-default-row">
              <span class="format-default-label">Video</span>
              <select v-model="defaultVideoFormat" class="settings-select">
                <option value="auto">Auto (native container)</option>
                <option value="mp4">MP4</option>
                <option value="webm">WebM</option>
              </select>
            </div>
            <div class="format-default-row">
              <span class="format-default-label">Audio</span>
              <select v-model="defaultAudioFormat" class="settings-select">
                <option value="auto">Auto (native container)</option>
                <option value="mp3">MP3</option>
                <option value="m4a">M4A (AAC)</option>
                <option value="flac">FLAC</option>
                <option value="wav">WAV</option>
                <option value="opus">Opus</option>
              </select>
            </div>
          </div>
        </div>

        <div class="settings-actions">
          <button
            @click="saveSettings"
            :disabled="store.isLoading"
            class="btn-save"
          >
            {{ store.isLoading ? 'Saving…' : 'Save Settings' }}
          </button>
          <span v-if="settingsSaved" class="save-confirm">✓ Saved</span>
        </div>
        <p class="field-hint" style="margin-top: var(--space-md);">
          Changes are applied immediately but reset on server restart.
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.admin-panel {
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--space-lg) var(--space-md);
}

.admin-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-lg);
}

.admin-header h2 {
  color: var(--color-accent);
}

.btn-logout {
  background: transparent;
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
}

.btn-logout:hover {
  color: var(--color-error);
  border-color: var(--color-error);
}

.admin-tabs {
  display: flex;
  gap: var(--space-xs);
  margin-bottom: var(--space-lg);
}

.admin-tabs button {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-surface);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  text-transform: capitalize;
}

.admin-tabs button.active {
  color: var(--color-accent);
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.tab-content {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
}

.admin-table th,
.admin-table td {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.admin-table th {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-transform: uppercase;
}

.mono {
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}

.storage-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.stat {
  display: flex;
  justify-content: space-between;
  padding: var(--space-xs) 0;
}

.stat-label {
  color: var(--color-text-muted);
  text-transform: capitalize;
}

.stat-value {
  font-family: var(--font-mono);
}

h3 {
  margin-top: var(--space-md);
  margin-bottom: var(--space-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  text-transform: uppercase;
}

.btn-purge {
  background: var(--color-warning);
  color: var(--color-bg);
  font-weight: 600;
  margin-top: var(--space-md);
}

.btn-purge:hover:not(:disabled) {
  background: var(--color-error);
}

.purge-result {
  margin-top: var(--space-md);
  padding: var(--space-md);
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
}

.empty {
  color: var(--color-text-muted);
  text-align: center;
}

.settings-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.settings-field label {
  font-weight: 600;
  color: var(--color-text);
}

.field-hint {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin: 0;
}

.settings-textarea {
  width: 100%;
  padding: var(--space-sm);
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: var(--font-size-base);
  resize: vertical;
}

.settings-textarea:focus {
  outline: none;
  border-color: var(--color-accent);
}

.settings-actions {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.btn-save {
  background: var(--color-accent);
  color: var(--color-bg);
  font-weight: 600;
  padding: var(--space-sm) var(--space-lg);
}

.btn-save:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.save-confirm {
  color: var(--color-success);
  font-weight: 500;
  font-size: var(--font-size-sm);
}

.format-defaults {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}

.format-default-row {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.format-default-label {
  min-width: 50px;
  font-weight: 500;
  color: var(--color-text);
}

.settings-select {
  padding: var(--space-xs) var(--space-sm);
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: var(--font-size-sm);
  min-width: 200px;
}

.settings-select:focus {
  outline: none;
  border-color: var(--color-accent);
}

/* Expandable session rows */
.session-row.clickable {
  cursor: pointer;
}

.session-row.clickable:hover {
  background: var(--color-surface-hover);
}

.session-row.expanded {
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
}

.col-expand {
  width: 24px;
  text-align: center;
}

.expand-icon {
  font-size: 10px;
  color: var(--color-text-muted);
}

.jobs-detail-row td {
  padding: 0 var(--space-md) var(--space-md);
  border-bottom: 1px solid var(--color-border);
}

.jobs-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-sm) 0;
}

.job-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-xs) var(--space-sm);
  font-size: var(--font-size-sm);
  border-radius: var(--radius-sm);
  background: var(--color-bg);
}

.job-filename {
  flex: 1;
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 120px;
}

.job-size {
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  white-space: nowrap;
  min-width: 60px;
}

.badge-sm {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  font-weight: 600;
  white-space: nowrap;
}

.badge-completed { background: color-mix(in srgb, var(--color-success) 15%, transparent); color: var(--color-success); }
.badge-failed { background: color-mix(in srgb, var(--color-error) 15%, transparent); color: var(--color-error); }
.badge-downloading { background: color-mix(in srgb, var(--color-accent) 15%, transparent); color: var(--color-accent); }
.badge-queued { background: color-mix(in srgb, var(--color-text-muted) 15%, transparent); color: var(--color-text-muted); }

.job-time {
  color: var(--color-text-muted);
  white-space: nowrap;
  font-size: var(--font-size-sm);
}

.job-url {
  color: var(--color-accent);
  text-decoration: none;
  font-size: var(--font-size-sm);
}

.job-url:hover {
  text-decoration: underline;
}

.jobs-loading, .jobs-empty {
  padding: var(--space-sm);
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  font-style: italic;
}
</style>
