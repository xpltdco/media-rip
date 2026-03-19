<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import { useConfigStore } from '@/stores/config'
import { api } from '@/api/client'
import AdminLogin from './AdminLogin.vue'

const store = useAdminStore()
const configStore = useConfigStore()
const router = useRouter()
const activeTab = ref<'sessions' | 'storage' | 'errors' | 'settings'>('sessions')

// Session expansion state
const expandedSessions = ref<Set<string>>(new Set())
const sessionJobs = ref<Record<string, any[]>>({})
const loadingJobs = ref<Set<string>>(new Set())

// Settings state
const welcomeMessage = ref('')
const defaultVideoFormat = ref('auto')
const defaultAudioFormat = ref('auto')
const settingsSaved = ref(false)
const privacyMode = ref(false)
const privacyRetentionHours = ref(24)
const purgeConfirming = ref(false)
let purgeConfirmTimer: ReturnType<typeof setTimeout> | null = null

// New persisted settings
const maxConcurrent = ref(3)
const sessionMode = ref('isolated')
const sessionTimeoutHours = ref(72)
const adminUsername = ref('admin')
const purgeEnabled = ref(false)
const purgeMaxAgeHours = ref(168)

// Change password state
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const changingPassword = ref(false)
const passwordChanged = ref(false)
const passwordError = ref<string | null>(null)

const canChangePassword = computed(() =>
  currentPassword.value.length > 0 &&
  newPassword.value.length >= 4 &&
  newPassword.value === confirmPassword.value
)

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
  if (tab === 'errors') await store.loadErrorLog()
  if (tab === 'settings') {
    try {
      const res = await fetch('/api/admin/settings', {
        headers: { Authorization: `Basic ${btoa(`${store.username}:${store.password}`)}` },
      })
      if (res.ok) {
        const data = await res.json()
        welcomeMessage.value = data.welcome_message ?? ''
        defaultVideoFormat.value = data.default_video_format || 'auto'
        defaultAudioFormat.value = data.default_audio_format || 'auto'
        privacyMode.value = data.privacy_mode ?? false
        privacyRetentionHours.value = data.privacy_retention_hours ?? 24
        maxConcurrent.value = data.max_concurrent ?? 3
        sessionMode.value = data.session_mode ?? 'isolated'
        sessionTimeoutHours.value = data.session_timeout_hours ?? 72
        adminUsername.value = data.admin_username ?? 'admin'
        purgeEnabled.value = data.purge_enabled ?? false
        purgeMaxAgeHours.value = data.purge_max_age_hours ?? 168
      }
    } catch {
      // Keep current values
    }
  }
}

async function saveAllSettings() {
  settingsSaved.value = false
  const ok = await store.updateSettings({
    welcome_message: welcomeMessage.value,
    default_video_format: defaultVideoFormat.value,
    default_audio_format: defaultAudioFormat.value,
    privacy_mode: privacyMode.value,
    privacy_retention_hours: privacyRetentionHours.value,
    max_concurrent: maxConcurrent.value,
    session_mode: sessionMode.value,
    session_timeout_hours: sessionTimeoutHours.value,
    admin_username: adminUsername.value,
    purge_enabled: purgeEnabled.value,
    purge_max_age_hours: purgeMaxAgeHours.value,
  })
  if (ok) {
    await configStore.loadConfig()
    settingsSaved.value = true
    setTimeout(() => { settingsSaved.value = false }, 3000)
  }
}

function handlePurgeClick() {
  if (purgeConfirming.value) {
    purgeConfirming.value = false
    if (purgeConfirmTimer) clearTimeout(purgeConfirmTimer)
    store.triggerPurge()
  } else {
    purgeConfirming.value = true
    purgeConfirmTimer = setTimeout(() => { purgeConfirming.value = false }, 3000)
  }
}

async function changePassword() {
  if (!canChangePassword.value) return
  changingPassword.value = true
  passwordChanged.value = false
  passwordError.value = null

  try {
    const res = await fetch('/api/admin/password', {
      method: 'PUT',
      headers: {
        'Authorization': 'Basic ' + btoa(store.username + ':' + store.password),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        current_password: currentPassword.value,
        new_password: newPassword.value,
      }),
    })

    if (res.ok) {
      passwordChanged.value = true
      currentPassword.value = ''
      newPassword.value = ''
      confirmPassword.value = ''
      // Auto-logout after 1.5s so user sees the success message
      setTimeout(() => {
        store.logout()
        router.push('/')
      }, 1500)
    } else {
      const data = await res.json()
      passwordError.value = data.detail || 'Failed to change password'
    }
  } catch {
    passwordError.value = 'Network error'
  } finally {
    changingPassword.value = false
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
          v-for="tab in (['sessions', 'storage', 'errors', 'settings'] as const)"
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

      <!-- Errors tab -->
      <div v-if="activeTab === 'errors'" class="tab-content">
        <div class="error-log-header">
          <p class="field-hint" style="margin: 0;">
            Failed downloads are logged here with enough detail to diagnose domain-specific issues.
          </p>
          <button
            v-if="store.errorLog.length"
            @click="store.clearErrorLog()"
            :disabled="store.isLoading"
            class="btn-clear-log"
          >
            Clear Log
          </button>
        </div>
        <div v-if="store.errorLog.length" class="error-log">
          <div v-for="entry in store.errorLog" :key="entry.id" class="error-entry">
            <div class="error-entry-header">
              <span class="error-domain">{{ entry.domain }}</span>
              <span class="error-time">{{ new Date(entry.created_at).toLocaleString() }}</span>
            </div>
            <div class="error-url mono">{{ entry.url }}</div>
            <div class="error-message">{{ entry.error }}</div>
            <div v-if="entry.format_id || entry.media_type" class="error-meta">
              <span v-if="entry.media_type">{{ entry.media_type }}</span>
              <span v-if="entry.format_id">format: {{ entry.format_id }}</span>
            </div>
          </div>
        </div>
        <p v-else class="empty">No errors logged.</p>
      </div>

      <!-- Settings tab -->
      <div v-if="activeTab === 'settings'" class="tab-content">
        <!-- All configurable settings in one form -->
        <div class="settings-form">
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

          <div class="settings-field">
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

          <div class="settings-field">
            <label class="toggle-label">
              <span>Privacy Mode</span>
              <label class="toggle-switch">
                <input type="checkbox" v-model="privacyMode" />
                <span class="toggle-slider"></span>
              </label>
            </label>
            <p class="field-hint">
              Automatically purge download history, files, and session data
              after the retention period.
            </p>
            <div v-if="privacyMode" class="retention-setting">
              <label class="retention-label">Retention period</label>
              <div class="retention-input-row">
                <input
                  type="number"
                  v-model.number="privacyRetentionHours"
                  min="1"
                  max="8760"
                  class="settings-input retention-input"
                />
                <span class="retention-unit">hours</span>
              </div>
              <p class="field-hint">
                Data older than this is automatically purged (default: 24 hours).
              </p>
            </div>
          </div>

          <!-- Server settings -->
          <div class="settings-field">
            <label>Max Concurrent Downloads</label>
            <p class="field-hint">How many downloads can run in parallel (1–10).</p>
            <input
              type="number"
              v-model.number="maxConcurrent"
              min="1"
              max="10"
              class="settings-input"
              style="width: 80px;"
            />
          </div>

          <div class="settings-field">
            <label>Session Mode</label>
            <p class="field-hint">Controls download queue visibility between browser sessions.</p>
            <select v-model="sessionMode" class="settings-select">
              <option value="isolated">Isolated — each browser has its own queue</option>
              <option value="shared">Shared — all users see all downloads</option>
              <option value="open">Open — no session tracking</option>
            </select>
          </div>

          <div class="settings-field">
            <label>Session Timeout</label>
            <p class="field-hint">Hours before an inactive session cookie expires (1–8760).</p>
            <div class="retention-input-row">
              <input
                type="number"
                v-model.number="sessionTimeoutHours"
                min="1"
                max="8760"
                class="settings-input retention-input"
              />
              <span class="retention-unit">hours</span>
            </div>
          </div>

          <div class="settings-field">
            <label>Admin Username</label>
            <p class="field-hint">Username for admin panel login.</p>
            <input
              type="text"
              v-model="adminUsername"
              class="settings-input"
              style="max-width: 200px;"
              autocomplete="username"
            />
          </div>

          <div class="settings-field">
            <label class="toggle-label">
              <span>Auto-Purge</span>
              <label class="toggle-switch">
                <input type="checkbox" v-model="purgeEnabled" />
                <span class="toggle-slider"></span>
              </label>
            </label>
            <p class="field-hint">
              Automatically delete completed/failed downloads on a schedule.
            </p>
            <div v-if="purgeEnabled" class="retention-setting">
              <label class="retention-label">Delete downloads older than</label>
              <div class="retention-input-row">
                <input
                  type="number"
                  v-model.number="purgeMaxAgeHours"
                  min="1"
                  max="87600"
                  class="settings-input retention-input"
                />
                <span class="retention-unit">hours</span>
              </div>
            </div>
          </div>

          <div class="settings-actions settings-save-row">
            <button @click="saveAllSettings" :disabled="store.isLoading" class="btn-save">
              {{ store.isLoading ? 'Saving…' : 'Save Settings' }}
            </button>
            <span v-if="settingsSaved" class="save-confirm">✓ Saved</span>
          </div>
          <p class="field-hint">
            Settings are saved to the database and persist across restarts.
          </p>
        </div>

        <hr class="settings-divider" />

        <!-- Actions (not "settings" — these are immediate operations) -->
        <div class="settings-field">
          <label>Manual Purge</label>
          <p class="field-hint">
            Immediately clear all completed and failed downloads — removes
            database records, files from disk, and orphaned sessions.
            Active downloads are never affected.
          </p>
          <button
            @click="handlePurgeClick"
            :disabled="store.isLoading"
            class="btn-purge"
            :class="{ 'btn-confirm': purgeConfirming }"
          >
            {{ store.isLoading ? 'Purging…' : purgeConfirming ? 'Sure?' : 'Run Purge Now' }}
          </button>
          <div v-if="store.purgeResult" class="purge-result">
            <p>{{ store.purgeResult.rows_deleted }} jobs removed</p>
            <p>{{ store.purgeResult.files_deleted }} files deleted</p>
            <p v-if="store.purgeResult.sessions_deleted">{{ store.purgeResult.sessions_deleted }} sessions cleared</p>
            <p v-if="store.purgeResult.active_skipped">{{ store.purgeResult.active_skipped }} active jobs skipped</p>
          </div>
        </div>

        <hr class="settings-divider" />

        <div class="settings-field">
          <label>Change Password</label>
          <p class="field-hint">Takes effect immediately. Set via MEDIARIP__ADMIN__PASSWORD_HASH env var for initial deployment.</p>
          <div class="password-fields">
            <input
              v-model="currentPassword"
              type="password"
              placeholder="Current password"
              autocomplete="current-password"
              class="settings-input"
            />
            <input
              v-model="newPassword"
              type="password"
              placeholder="New password"
              autocomplete="new-password"
              class="settings-input"
            />
            <input
              v-model="confirmPassword"
              type="password"
              placeholder="Confirm new password"
              autocomplete="new-password"
              class="settings-input"
              @keydown.enter="changePassword"
            />
            <span
              v-if="confirmPassword && newPassword && confirmPassword !== newPassword"
              class="password-mismatch"
            >
              Passwords don't match
            </span>
          </div>
          <div class="settings-actions" style="margin-top: var(--space-sm);">
            <button
              @click="changePassword"
              :disabled="!canChangePassword || changingPassword"
              class="btn-save"
            >
              {{ changingPassword ? 'Changing…' : 'Change Password' }}
            </button>
            <span v-if="passwordChanged" class="save-confirm">✓ Password changed</span>
            <span v-if="passwordError" class="password-error">{{ passwordError }}</span>
          </div>
        </div>
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
  min-width: 130px;
  transition: background-color 0.15s;
}

.btn-purge:hover:not(:disabled) {
  background: var(--color-error);
}

.btn-purge.btn-confirm {
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

.settings-section {
  margin-bottom: var(--space-sm);
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.settings-form .settings-field {
  padding-bottom: var(--space-md);
  border-bottom: 1px solid var(--color-border);
}

.settings-form .settings-field:last-of-type {
  border-bottom: none;
  padding-bottom: 0;
}

.settings-save-row {
  padding-top: var(--space-sm);
}

.section-heading {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 var(--space-md) 0;
  letter-spacing: 0.02em;
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

.settings-divider {
  border: none;
  border-top: 1px solid var(--color-border);
  margin: var(--space-lg) 0;
}

/* Toggle switch */
.toggle-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background-color: var(--color-border);
  border-radius: 24px;
  transition: background-color 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: var(--color-bg);
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-switch input:checked + .toggle-slider {
  background-color: var(--color-accent-primary, #00a8ff);
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* Retention input */
.retention-setting {
  margin-top: var(--space-sm);
  padding-left: var(--space-sm);
  border-left: 2px solid var(--color-accent-primary, #00a8ff);
}

.retention-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  margin-bottom: var(--space-xs);
}

.retention-input-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.retention-input {
  width: 80px !important;
  text-align: center;
}

.retention-unit {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.password-fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
  max-width: 320px;
}

.settings-input {
  padding: var(--space-sm);
  background: var(--color-bg);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: var(--font-size-sm);
}

.settings-input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.password-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  font-weight: 500;
}

.password-mismatch {
  color: var(--color-warning);
  font-size: var(--font-size-sm);
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

/* Error log */
.error-log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.btn-clear-log {
  background: var(--color-bg-elevated);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  padding: var(--space-xs) var(--space-md);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-sm);
  white-space: nowrap;
}

.btn-clear-log:hover {
  color: var(--color-error);
  border-color: var(--color-error);
}

.error-log {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.error-entry {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-error);
  border-radius: var(--radius-sm);
  padding: var(--space-sm) var(--space-md);
}

.error-entry-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs);
}

.error-domain {
  font-weight: 600;
  color: var(--color-text);
}

.error-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.error-url {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
  word-break: break-all;
  margin-bottom: var(--space-xs);
}

.error-message {
  font-size: var(--font-size-sm);
  color: var(--color-error);
  white-space: pre-wrap;
  word-break: break-word;
}

.error-meta {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-xs);
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}
</style>
