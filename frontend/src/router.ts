import { createRouter, createWebHistory } from 'vue-router'

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
