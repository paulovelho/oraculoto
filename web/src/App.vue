<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import HealthBadge from '@/components/HealthBadge.vue'
import { loadHealth } from '@/lib/health'

onMounted(loadHealth)

// "Resultados" covers the latest result and any contest page.
const route = useRoute()
const section = computed(() => (route.name === 'stats' ? 'stats' : route.name === 'home' || route.name === 'contest' ? 'results' : null))
</script>

<template>
  <header class="site-header">
    <div class="container site-header__inner">
      <RouterLink to="/" class="brand" aria-label="Oraculoto, início">
        <img src="/favicon.png" alt="" width="36" height="36" />
        <span>Oraculoto</span>
      </RouterLink>
      <nav class="nav" aria-label="Seções">
        <RouterLink to="/" class="nav__link" :class="{ on: section === 'results' }">Resultados</RouterLink>
        <RouterLink to="/estatisticas" class="nav__link" :class="{ on: section === 'stats' }">Estatísticas</RouterLink>
      </nav>
      <HealthBadge />
    </div>
  </header>

  <main class="container">
    <RouterView />
  </main>

  <footer class="site-footer container">
    Resultados da Mega-Sena. Nenhum número aqui aumenta a sua chance de ganhar.
  </footer>
</template>

<style scoped>
.site-header {
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 85%, transparent);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.site-header__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  min-height: 3.75rem;
  flex-wrap: wrap;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  color: var(--gold);
  font-weight: 800;
  font-size: 1.25rem;
  letter-spacing: 0.02em;
  text-decoration: none;
}

.nav {
  display: flex;
  gap: 0.25rem;
  margin-right: auto;
}
.nav__link {
  padding: 0.3rem 0.7rem;
  border-radius: 999px;
  color: var(--text-muted);
  text-decoration: none;
  font-weight: 600;
}
.nav__link.on {
  color: var(--text);
  background: var(--surface-2);
}

main {
  padding-block: 2rem 3rem;
  min-height: calc(100dvh - 9rem);
}

.site-footer {
  padding-block: 1.5rem;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
