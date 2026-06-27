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
  if (to.meta.public) return true
  try {
    await client.get('/api/settings')
    return true
  } catch (e: unknown) {
    const status = (e as { status?: number }).status
    if (status === 401) return { name: 'login', query: { redirect: to.fullPath } }
    return true
  }
})
