<script setup lang="ts">
import { ref } from 'vue'
import { useAdminStore } from '@/stores/admin'

const store = useAdminStore()
const user = ref('')
const pass = ref('')

async function handleLogin() {
  await store.login(user.value, pass.value)
}
</script>

<template>
  <div class="admin-login">
    <h2>Admin Login</h2>
    <form @submit.prevent="handleLogin" class="login-form">
      <input
        v-model="user"
        type="text"
        placeholder="Username"
        autocomplete="username"
      />
      <input
        v-model="pass"
        type="password"
        placeholder="Password"
        autocomplete="current-password"
      />
      <button type="submit">Login</button>
      <p v-if="store.authError" class="error">{{ store.authError }}</p>
    </form>
  </div>
</template>

<style scoped>
.admin-login {
  max-width: 400px;
  margin: var(--space-xl) auto;
  padding: var(--space-xl);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

h2 {
  margin-bottom: var(--space-lg);
  color: var(--color-accent);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

button {
  background: var(--color-accent);
  color: var(--color-bg);
  font-weight: 600;
}

button:hover {
  background: var(--color-accent-hover);
}

.error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
}
</style>
