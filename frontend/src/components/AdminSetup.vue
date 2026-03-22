<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAdminStore } from '@/stores/admin'
import { useConfigStore } from '@/stores/config'
import { clearAdminStatusCache } from '@/router'

const store = useAdminStore()
const configStore = useConfigStore()

const username = ref('admin')
const password = ref('')
const confirmPassword = ref('')
const isSubmitting = ref(false)

const passwordMismatch = computed(() =>
  confirmPassword.value.length > 0 && password.value !== confirmPassword.value
)

const canSubmit = computed(() =>
  username.value.trim().length > 0 &&
  password.value.length >= 4 &&
  password.value === confirmPassword.value &&
  !isSubmitting.value
)

async function handleSetup() {
  if (!canSubmit.value) return
  isSubmitting.value = true
  const ok = await store.setup(username.value.trim(), password.value)
  if (ok) {
    // Clear cached status so router guard knows setup is done
    clearAdminStatusCache()
    // Reload public config so admin_setup_complete updates everywhere
    await configStore.loadConfig()
  }
  isSubmitting.value = false
}
</script>

<template>
  <div class="admin-setup">
    <div class="setup-card">
      <h2>Set Up Admin</h2>
      <p class="setup-hint">
        Create your admin account. You'll use these credentials to access
        the admin panel for managing sessions, settings, and downloads.
      </p>

      <form @submit.prevent="handleSetup" class="setup-form">
        <label>
          <span>Username</span>
          <input
            v-model="username"
            type="text"
            placeholder="admin"
            autocomplete="username"
            autofocus
          />
        </label>

        <label>
          <span>Password</span>
          <input
            v-model="password"
            type="password"
            placeholder="At least 4 characters"
            autocomplete="new-password"
          />
        </label>

        <label>
          <span>Confirm Password</span>
          <input
            v-model="confirmPassword"
            type="password"
            placeholder="Confirm password"
            autocomplete="new-password"
            :class="{ 'input-error': passwordMismatch }"
          />
          <span v-if="passwordMismatch" class="field-error">Passwords don't match</span>
        </label>

        <button type="submit" :disabled="!canSubmit">
          {{ isSubmitting ? 'Creating…' : 'Create Admin Account' }}
        </button>

        <p v-if="store.authError" class="error">{{ store.authError }}</p>
      </form>
    </div>
  </div>
</template>

<style scoped>
.admin-setup {
  max-width: 440px;
  margin: var(--space-xl) auto;
  padding: var(--space-lg);
}

.setup-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-xl);
}

h2 {
  margin-bottom: var(--space-sm);
  color: var(--color-accent);
}

.setup-hint {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-lg);
  line-height: 1.5;
}

.setup-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

label {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

label > span {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text);
}

input {
  padding: var(--space-sm) var(--space-md);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: var(--font-size-base);
}

input:focus {
  outline: none;
  border-color: var(--color-accent);
}

input.input-error {
  border-color: var(--color-error);
}

.field-error {
  color: var(--color-error);
  font-size: var(--font-size-xs);
}

button {
  margin-top: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-accent);
  color: var(--color-bg);
  font-weight: 600;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: var(--font-size-base);
}

button:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  margin: 0;
}
</style>
