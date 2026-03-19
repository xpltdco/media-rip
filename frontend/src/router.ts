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

export default router
