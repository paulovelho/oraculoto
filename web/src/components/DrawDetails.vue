<script setup lang="ts">
import { computed } from 'vue'
import type { Draw } from '@/api'
import DrawBalls from '@/components/DrawBalls.vue'
import { displayBalls, jackpotWon, locationLabel, sortedPrizes, tierName } from '@/lib/draws'
import { formatDate, formatInt, formatMoney } from '@/lib/format'

// `draw` null = still loading: same layout, skeleton blocks (docs/web.md §4).
const props = defineProps<{ draw: Draw | null; eyebrow?: string }>()

const shown = computed(() => (props.draw ? displayBalls(props.draw) : null))
const won = computed(() => (props.draw ? jackpotWon(props.draw) : null))
const prizes = computed(() => (props.draw ? sortedPrizes(props.draw.prizes) : []))
const next = computed(() => (props.draw ? formatInt(props.draw.contest + 1) : ''))

function winners(n: number | null): string {
  if (n === null) return '—'
  return n === 0 ? 'nenhum' : formatInt(n)
}
</script>

<template>
  <article v-if="draw && shown" class="draw">
    <header class="draw__head">
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <h1>Concurso {{ formatInt(draw.contest) }}</h1>
      <p class="draw__meta">
        <span>{{ formatDate(draw.date) }}</span>
        <span v-if="won === false" class="tag tag--gold">Acumulou</span>
        <span v-else-if="won === true" class="tag tag--green">Sena saiu</span>
        <span v-if="draw.is_special" class="tag">Concurso especial</span>
      </p>
    </header>

    <section class="block">
      <DrawBalls :balls="shown.balls" />
      <p class="hint">{{ shown.drawnOrder ? 'Na ordem do sorteio.' : 'Em ordem crescente (ordem do sorteio desconhecida).' }}</p>
    </section>

    <section class="block">
      <h2>Premiação</h2>
      <table class="data-table prizes">
        <thead>
          <tr>
            <th scope="col">Faixa</th>
            <th scope="col" class="num">Ganhadores</th>
            <th scope="col" class="num">Prêmio por ganhador</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in prizes" :key="p.hits">
            <th scope="row">{{ tierName(p.hits) }} <small>{{ p.hits }} acertos</small></th>
            <td class="num">{{ winners(p.winners) }}</td>
            <td class="num">{{ p.winners === 0 ? '—' : formatMoney(p.prize_per_winner) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="won" class="block">
      <h2>Onde saiu a Sena</h2>
      <ul v-if="draw.winner_locations.length" class="locations">
        <li v-for="(loc, i) in draw.winner_locations" :key="i">
          {{ locationLabel(loc) }}
          <span v-if="loc.winners !== null && loc.winners > 1" class="muted">· {{ formatInt(loc.winners) }} apostas</span>
        </li>
      </ul>
      <p v-else class="muted">Locais não informados para este concurso.</p>
    </section>

    <section class="block">
      <h2>Valores</h2>
      <dl class="money">
        <div>
          <dt>Acumulado para o concurso {{ next }}</dt>
          <dd>{{ formatMoney(draw.rollover_amount) }}</dd>
        </div>
        <div>
          <dt>Prêmio estimado do concurso {{ next }}</dt>
          <dd class="highlight">{{ formatMoney(draw.next_estimated_prize) }}</dd>
        </div>
        <div>
          <dt>Arrecadação total</dt>
          <dd>{{ formatMoney(draw.total_collected) }}</dd>
        </div>
        <div>
          <dt>Acumulado para a Mega da Virada</dt>
          <dd>{{ formatMoney(draw.special_accumulated) }}</dd>
        </div>
      </dl>
    </section>

    <p v-if="draw.notes" class="notes">{{ draw.notes }}</p>
  </article>

  <article v-else class="draw" aria-busy="true">
    <header class="draw__head">
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <h1><span class="skeleton sk sk--title">Concurso 0000</span></h1>
      <p class="draw__meta"><span class="skeleton sk">00/00/0000</span></p>
    </header>
    <section class="block">
      <ol class="balls-sk" aria-hidden="true">
        <li v-for="i in 6" :key="i" class="skeleton"></li>
      </ol>
    </section>
    <section class="block">
      <h2>Premiação</h2>
      <div class="skeleton sk sk--block" style="height: 7rem"></div>
    </section>
    <section class="block">
      <h2>Valores</h2>
      <div class="skeleton sk sk--block" style="height: 7rem"></div>
    </section>
  </article>
</template>

<style scoped>
.draw {
  display: grid;
  gap: 1.25rem;
}

.draw__head {
  display: grid;
  gap: 0.35rem;
}

.eyebrow {
  color: var(--gold);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  font-size: clamp(1.75rem, 5vw, 2.25rem);
}

.draw__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-muted);
}

.tag {
  padding: 0.1em 0.65em;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text);
}
.tag--gold {
  color: var(--gold);
  border-color: color-mix(in srgb, var(--gold) 45%, transparent);
}
.tag--green {
  color: var(--green);
  border-color: color-mix(in srgb, var(--green) 45%, transparent);
}

.prizes small {
  display: block;
  color: var(--text-muted);
  font-weight: 400;
}

.locations {
  margin: 0;
  padding-left: 1.2rem;
  display: grid;
  gap: 0.25rem;
}

.money {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1rem;
  margin: 0;
}
.money dt {
  color: var(--text-muted);
  font-size: 0.85rem;
}
.money dd {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}
.money .highlight {
  color: var(--gold);
}

.notes {
  color: var(--text-muted);
  font-size: 0.9rem;
  border-left: 3px solid var(--gold-deep);
  padding-left: 0.75rem;
}

.sk--title {
  min-width: 12ch;
}

.balls-sk {
  display: flex;
  flex-wrap: wrap;
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
