import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/resultado', name: 'latest', component: () => import('@/views/LatestView.vue') },
    // Positive integers only; anything else (/contest/0, /contest/abc) is the app's 404.
    {
      path: '/contest/:n([1-9]\\d*)',
      name: 'contest',
      component: () => import('@/views/ContestView.vue'),
      props: true,
    },
    { path: '/estatisticas', name: 'stats', component: () => import('@/views/StatsView.vue') },
    { path: '/about', name: 'about', component: () => import('@/views/AboutView.vue') },
    // Old links. The host reserves /stats (301 to /stats/, then a 403 whose body is still our
    // index.html), so the app does boot there; this sends it to the real page. Keeps the query.
    { path: '/stats', redirect: (to) => ({ path: '/estatisticas', query: to.query, hash: to.hash }) },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
  ],
  // A query-only change (stats window, "together" page) keeps the scroll position.
  scrollBehavior: (to, from, saved) => saved ?? (to.path === from.path ? false : { top: 0 }),
})
