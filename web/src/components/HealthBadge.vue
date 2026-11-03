<script setup lang="ts">
import { computed } from 'vue'
import { formatDate, formatInt } from '@/lib/format'
import { useHealth } from '@/lib/health'

const { health, error, loading, reload } = useHealth()

const megasena = computed(() => health.value?.games.find((g) => g.game === 'megasena') ?? null)

const lastCrawl = computed(() => {
  const ts = megasena.value?.last_crawl
  // "2026-11-02T22:10:03Z" → "02/11/2026 22:10 UTC", by splitting, like every other date.
  return ts ? `${formatDate(ts.slice(0, 10))} ${ts.slice(11, 16)} UTC` : 'nunca'
})
</script>

<template>
  <div class="badge skeleton" v-if="loading && !health" aria-busy="true">carregando…</div>

  <button class="badge badge--error" v-else-if="error" type="button" @click="reload" :title="error.message">
    API indisponível · tentar de novo
  </button>

  <div
    v-else-if="megasena"
    class="badge"
    :class="{ 'badge--stale': megasena.stale }"
    :title="`Última coleta: ${lastCrawl}`"
  >
    <span class="dot" aria-hidden="true"></span>
    Concurso {{ formatInt(megasena.latest_contest) }} · {{ formatDate(megasena.latest_date) }}
    <strong v-if="megasena.stale">· desatualizado</strong>
  </div>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5em;
  padding: 0.35em 0.8em;
  border-radius: 999px;
  font-size: 0.85rem;
  background: var(--surface-2);
  color: var(--text-muted);
  border: 1px solid var(--border);
  white-space: nowrap;
}

.dot {
  width: 0.55em;
  height: 0.55em;
  border-radius: 50%;
  background: var(--green);
}

.badge--stale {
  color: var(--gold);
  border-color: color-mix(in srgb, var(--gold) 40%, transparent);
}
.badge--stale .dot {
  background: var(--gold);
}

.badge--error {
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 40%, transparent);
  cursor: pointer;
  font: inherit;
  font-size: 0.85rem;
}
</style>
