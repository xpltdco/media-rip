<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { api } from '@/api/client'
import AdminLogin from './AdminLogin.vue'

const store = useAdminStore()
const activeTab = ref<'sessions' | 'storage' | 'purge' | 'settings'>('sessions')

// Settings state
const welcomeMessage = ref('')
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
    } catch {
      // Keep current value
    }
  }
}

async function saveSettings() {
  settingsSaved.value = false
  const ok = await store.updateSettings({ welcome_message: welcomeMessage.value })
  if (ok) {
    settingsSaved.value = true
    setTimeout(() => { settingsSaved.value = false }, 3000)
  }
}
</script>

<template>
  <div class="admin-panel">
    <AdminLogin v-if="!store.isAuthenticated" />

    <template v-else>
      <div class="admin-header">
        <h2>Admin Panel</h2>
        <button class="btn-logout" @click="store.logout()">Logout</button>
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
              <th>Session ID</th>
              <th>Last Seen</th>
              <th>Jobs</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in store.sessions" :key="s.id">
              <td class="mono">{{ s.id.slice(0, 8) }}…</td>
              <td>{{ new Date(s.last_seen).toLocaleString() }}</td>
              <td>{{ s.job_count }}</td>
            </tr>
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
</style>
