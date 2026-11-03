<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCombinations, getFrequency, getGame, getGaps } from '@/api'
import CombinationsTable from '@/components/CombinationsTable.vue'
import FrequencyChart from '@/components/FrequencyChart.vue'
import GapsTable from '@/components/GapsTable.vue'
import LoadError from '@/components/LoadError.vue'
import TogetherSearch from '@/components/TogetherSearch.vue'
import WindowPicker from '@/components/WindowPicker.vue'
import { useHealth } from '@/lib/health'
import {
  parseTogether,
  parseWindow,
  statsRouteQuery,
  windowQuery,
  type BallRules,
  type TogetherSel,
  type WindowSel,
} from '@/lib/statsQuery'
import { useLoad } from '@/lib/useLoad'

// docs/web.md §6.3. The URL holds the state (window + "together" search), so any view can be
// shared. One window for every block; each block loads in parallel and fails on its own.

const route = useRoute()
const router = useRouter()
const { latestContest } = useHealth()

// Mega-Sena's rules as a fallback while /games loads, so the URL can be parsed straight away.
// /games replaces them as soon as it answers; nothing is fetched with these alone.
const FALLBACK: BallRules = { ball_min: 1, ball_max: 60, balls_drawn: 6 }
const game = useLoad(getGame)
const rules = computed<BallRules>(() => game.data.value ?? FALLBACK)
const pool = computed(() => rules.value.ball_max - rules.value.ball_min + 1)

const sel = computed(() => parseWindow(route.query))
const winQuery = computed(() => windowQuery(sel.value))
const together = computed(() => parseTogether(route.query, rules.value))

const freq = useLoad(() => getFrequency(winQuery.value))
const gaps = useLoad(() => getGaps(winQuery.value))
const size = ref<2 | 3>(2)
const combos = useLoad(() => getCombinations(winQuery.value, size.value))

onMounted(() => {
  document.title = 'Estatísticas · Oraculoto'
  game.run()
})
watch(
  () => JSON.stringify(winQuery.value),
  () => {
    freq.run()
    gaps.run()
    combos.run()
  },
  { immediate: true },
)
watch(size, () => combos.run())

// Any response tells which contests the window covered; frequency is the cheapest to wait for.
const covered = computed(
  () => freq.data.value?.window ?? gaps.data.value?.window ?? combos.data.value?.window ?? null,
)
const empty = computed(() => covered.value?.draws === 0)

function setWindow(next: WindowSel) {
  // A new window starts the "together" list over at page 1.
  router.push({ query: statsRouteQuery(next, { ...together.value, page: 1 }) })
}
function setTogether(next: TogetherSel) {
  router.push({ query: statsRouteQuery(sel.value, next) })
}
</script>

<template>
  <div class="page">
    <header class="head">
      <h1>Estatísticas</h1>
      <p class="muted">
        O que já saiu, sempre ao lado do que o acaso daria. Nada aqui muda a chance do próximo sorteio:
        cada combinação de 6 números continua com 1 em 50.063.860.
      </p>
    </header>

    <WindowPicker :model-value="sel" :covered="covered" :latest="latestContest" @update:model-value="setWindow" />

    <section class="block">
      <h2>Frequência</h2>
      <LoadError v-if="freq.error.value" :error="freq.error.value" @retry="freq.run" />
      <div v-else-if="!freq.data.value" class="skeleton sk sk--block" aria-busy="true"></div>
      <p v-else-if="empty" class="muted">Nenhum concurso nessa janela.</p>
      <FrequencyChart v-else :data="freq.data.value" :rules="rules" />
    </section>

    <div class="cols">
      <section class="block">
        <h2>Ausências</h2>
        <LoadError v-if="gaps.error.value" :error="gaps.error.value" @retry="gaps.run" />
        <div v-else-if="!gaps.data.value" class="skeleton sk sk--block" aria-busy="true"></div>
        <p v-else-if="empty" class="muted">Nenhum concurso nessa janela.</p>
        <GapsTable v-else :data="gaps.data.value" />
      </section>

      <section class="block">
        <header class="block-head">
          <h2>Mais frequentes</h2>
          <div class="tabs" role="radiogroup" aria-label="Tamanho da combinação">
            <label><input v-model="size" type="radio" :value="2" /> Pares</label>
            <label><input v-model="size" type="radio" :value="3" /> Trincas</label>
          </div>
        </header>
        <LoadError v-if="combos.error.value" :error="combos.error.value" @retry="combos.run" />
        <div v-else-if="!combos.data.value" class="skeleton sk sk--block" aria-busy="true"></div>
        <p v-else-if="empty" class="muted">Nenhum concurso nessa janela.</p>
        <CombinationsTable v-else :data="combos.data.value" :pool="pool" />
      </section>
    </div>

    <section class="block">
      <h2>Saíram juntas?</h2>
      <TogetherSearch :rules="rules" :window="winQuery" :value="together" @change="setTogether" />
    </section>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: 1.25rem;
}
.head {
  display: grid;
  gap: 0.35rem;
}
h1 {
  font-size: clamp(1.75rem, 5vw, 2.25rem);
}
.cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
  gap: 1.25rem;
  align-items: start;
}
.block-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.tabs {
  display: flex;
  gap: 1rem;
  font-size: 0.9rem;
}
.tabs label {
  display: inline-flex;
  gap: 0.35rem;
  align-items: center;
  cursor: pointer;
}
</style>
