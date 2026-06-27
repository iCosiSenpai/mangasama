import { createRouter, createWebHistory } from 'vue-router'
import { client } from '@/api/client'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'library-list',
      component: () => import('@/views/LibraryList.vue'),
    },
    {
      path: '/library/:id',
      name: 'library-detail',
      component: () => import('@/views/LibraryDetail.vue'),
    },
    {
      path: '/series/:id',
      name: 'series-detail',
      component: () => import('@/views/SeriesDetail.vue'),
    },
    {
      path: '/search',
      name: 'search',
      component: () => import('@/views/SearchPage.vue'),
    },
    {
      path: '/follow',
      name: 'follow',
      component: () => import('@/views/FollowView.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/setup',
      name: 'setup',
      component: () => import('@/views/SetupView.vue'),
      meta: { public: true },
    },
    {
      path: '/jobs',
      name: 'jobs',
      component: () => import('@/views/JobsView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  // Setup wizard is public and must be shown when no admin account exists.
  if (to.name === 'setup') return true
  if (to.meta.public) {
    // If setup is still required, even public pages (login) should redirect to setup.
    try {
      const { data } = await client.get('/api/setup/status')
      if (data.setup_required) return { name: 'setup' }
    } catch {
      // Let the route proceed if the status check fails; the app is degraded.
    }
    return true
  }
  try {
    const [{ data: setup }] = await Promise.all([
      client.get('/api/setup/status'),
      client.get('/api/settings'),
    ])
    if (setup.setup_required) return { name: 'setup' }
    return true
  } catch (e: unknown) {
    const status = (e as { status?: number }).status
    if (status === 401) return { name: 'login', query: { redirect: to.fullPath } }
    return true
  }
})
