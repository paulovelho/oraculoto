<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { getDraw, getOraculotoBets } from '@/api'
import DrawBalls from '@/components/DrawBalls.vue'
import LoadError from '@/components/LoadError.vue'
import { jackpotOdds } from '@/lib/bets'
import { tierName } from '@/lib/draws'
import { formatDate, formatInt, formatMoney } from '@/lib/format'
import { useHealth } from '@/lib/health'
import { useLoad } from '@/lib/useLoad'

const { latestContest } = useHealth()
// Newest contest first. Two are enough: a pending bet (the next contest) and the one before it.
const { data: page, error, run } = useLoad(() => getOraculotoBets(1, 2))
onMounted(() => {
  document.title = 'Oraculoto · a aposta do próximo concurso da Mega-Sena'
  run()
})

const next = computed(() => (page.value?.items[0]?.status === 'pending' ? page.value.items[0] : null))
// The last bet whose contest is past: drawn, or missing from the database.
const past = computed(() => page.value?.items.find((b) => b.status !== 'pending') ?? null)
// The contest it hasn't bet on yet: after the latest draw (from /health), or after its own last bet.
const nextContest = computed(() => {
  const newest = page.value?.items[0]
  const fromBet = newest ? newest.contest + 1 : null
  return latestContest.value === null ? fromBet : Math.max(latestContest.value + 1, fromBet ?? 0)
})
// "2026-11-07" → "sábado". Parsed as a local date: `new Date('2026-11-07')` is UTC midnight,
// which is still Friday in Brasília.
function weekday(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y!, m! - 1, d!).toLocaleDateString('pt-BR', { weekday: 'long' })
}
const odds = computed(() => (next.value ? jackpotOdds(next.value.numbers.length) : null))
const wins = computed(() => [...(past.value?.prizes ?? [])].sort((a, b) => b.hits - a.hits))
const topWin = computed(() => wins.value[0] ?? null)

// The numbers drawn in the past bet's contest (cached like every draw).
const pastContest = computed(() => (past.value?.status === 'drawn' ? past.value.contest : null))
const {
  data: draw,
  error: drawError,
  run: runDraw,
} = useLoad(() => (pastContest.value === null ? Promise.resolve(null) : getDraw(pastContest.value)))
watch(pastContest, () => runDraw())
</script>

<template>
  <div class="home">
    <h1 class="logo">
      <img src="/logo.webp" alt="Oraculoto" width="640" height="320" />
    </h1>

    <LoadError v-if="error" :error="error" @retry="run" />

    <section v-else-if="!page" class="block bet" aria-busy="true">
      <p class="eyebrow">Aposta do Oraculoto</p>
      <h2 class="bet__title"><span class="skeleton sk">Concurso 0000</span></h2>
      <ol class="balls-sk" aria-hidden="true">
        <li v-for="i in 6" :key="i" class="skeleton"></li>
      </ol>
      <p class="hint"><span class="skeleton sk">Chance da sena: 1 em 00.000.000</span></p>
    </section>

    <section v-else-if="!page.items.length" class="block bet">
      <p class="eyebrow">Aposta do Oraculoto</p>
      <p>O Oraculoto ainda não fez nenhuma aposta.</p>
    </section>

    <template v-else>
      <section v-if="next" class="block bet bet--next">
        <p class="eyebrow">Aposta do Oraculoto para o próximo concurso</p>
        <h2 class="bet__title">Concurso {{ formatInt(next.contest) }}</h2>
        <DrawBalls :balls="next.numbers" />
        <p v-if="next.date" class="draw-date">Sorteio em {{ weekday(next.date) }}, {{ formatDate(next.date) }}, às 20h.</p>
        <p v-if="odds !== null" class="hint">
          Chance da sena com {{ next.numbers.length }} números: 1 em {{ formatInt(odds) }}.
        </p>
      </section>
      <p v-else class="notice">A aposta do concurso {{ formatInt(nextContest) }} ainda não saiu.</p>

      <section v-if="past" class="block bet">
        <p class="eyebrow">Aposta passada</p>
        <h2 class="bet__title">
          <RouterLink v-if="past.status === 'drawn'" :to="{ name: 'contest', params: { n: String(past.contest) } }">
            Concurso {{ formatInt(past.contest) }}
          </RouterLink>
          <template v-else>Concurso {{ formatInt(past.contest) }}</template>
          <small v-if="past.date">{{ formatDate(past.date) }}</small>
        </h2>

        <template v-if="past.status === 'drawn'">
          <p v-if="topWin" class="prize" role="status">
            O Oraculoto acertou a {{ tierName(topWin.hits).toLowerCase() }}!
            <strong>{{ formatMoney(past.total) }}</strong>
          </p>

          <div class="row">
            <h3>Aposta do Oraculoto</h3>
            <DrawBalls :balls="past.numbers" :matched="past.matched" />
          </div>

          <div class="row">
            <h3>Números sorteados</h3>
            <LoadError v-if="drawError" :error="drawError" @retry="runDraw" />
            <DrawBalls v-else-if="draw" :balls="draw.balls" tone="gold" />
            <ol v-else class="balls-sk" aria-hidden="true">
              <li v-for="i in 6" :key="i" class="skeleton"></li>
            </ol>
          </div>

          <p>
            <strong>{{ past.hits === 1 ? '1 acerto' : `${past.hits ?? 0} acertos` }}</strong>
            <template v-if="!wins.length"> · sem prêmio</template>
          </p>
          <table v-if="wins.length" class="data-table">
            <thead>
              <tr>
                <th scope="col">Faixa</th>
                <th scope="col" class="num">Combinações</th>
                <th scope="col" class="num">Prêmio</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="w in wins" :key="w.hits">
                <th scope="row">{{ tierName(w.hits) }}</th>
                <td class="num">{{ formatInt(w.combinations) }}</td>
                <td class="num">{{ formatMoney(w.amount) }}</td>
              </tr>
            </tbody>
          </table>
        </template>

        <template v-else>
          <DrawBalls :balls="past.numbers" />
          <p class="muted">O resultado deste concurso não está na base.</p>
        </template>
      </section>
    </template>
  </div>
</template>

<style scoped>
.home {
  display: grid;
  gap: 1.5rem;
  max-width: 640px;
  margin-inline: auto;
}

.logo {
  margin: 0;
  line-height: 0;
}
.logo img {
  display: block;
  width: 100%;
  height: auto;
}

.eyebrow {
  color: var(--gold);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.bet {
  gap: 1rem;
}
.bet--next {
  border-color: color-mix(in srgb, var(--gold) 45%, var(--border));
}
.block > h2.bet__title {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--text);
}
.bet__title a {
  color: inherit;
}
.bet__title small {
  font-size: 0.9rem;
  font-weight: 400;
  color: var(--text-muted);
}

.row {
  display: grid;
  gap: 0.5rem;
}
.row h3 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-muted);
}

.prize {
  padding: 0.75rem 1rem;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--green) 18%, var(--surface));
  border: 1px solid var(--green);
  font-weight: 700;
}

.draw-date {
  font-weight: 600;
}

.notice {
  color: var(--text-muted);
}

.balls-sk {
  display: flex;
  gap: 0.6rem;
  list-style: none;
  margin: 0;
  padding: 0;
}
.balls-sk li {
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 50%;
}

@media (max-width: 420px) {
  .balls-sk li {
    width: 2.75rem;
    height: 2.75rem;
  }
}
</style>
