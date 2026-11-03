import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    // Positive integers only; anything else (/contest/0, /contest/abc) is the app's 404.
    {
      path: '/contest/:n([1-9]\\d*)',
      name: 'contest',
      component: () => import('@/views/ContestView.vue'),
      props: true,
    },
    { path: '/stats', name: 'stats', component: () => import('@/views/StatsView.vue') },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
  ],
  // A query-only change (stats window, "together" page) keeps the scroll position.
  scrollBehavior: (to, from, saved) => saved ?? (to.path === from.path ? false : { top: 0 }),
})
