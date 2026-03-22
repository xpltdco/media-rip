import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/components/MainView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/components/AdminPanel.vue'),
    },
  ],
})

// Cache the admin status check — fetched once per page load
let adminStatusCache: { enabled: boolean; setup_complete: boolean } | null = null

async function fetchAdminStatus() {
  if (adminStatusCache) return adminStatusCache
  try {
    const res = await fetch('/api/admin/status')
    if (res.ok) {
      adminStatusCache = await res.json()
      return adminStatusCache
    }
  } catch {
    // Network error — let navigation proceed
  }
  return null
}

/** Clear the cached admin status — call after setup completes. */
export function clearAdminStatusCache() {
  adminStatusCache = null
}

router.beforeEach(async (to) => {
  // Skip if already heading to admin
  if (to.name === 'admin') return true

  const status = await fetchAdminStatus()
  if (!status) return true // Can't determine — let it through

  // Force setup if admin is enabled but no password set
  if (status.enabled && !status.setup_complete) {
    return { name: 'admin' }
  }

  return true
})

export default router
