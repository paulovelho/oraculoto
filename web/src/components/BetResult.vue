<script setup lang="ts">
import { computed } from 'vue'
import type { OraculotoBet } from '@/api'
import DrawBalls from '@/components/DrawBalls.vue'
import { tierName } from '@/lib/draws'
import { formatInt, formatMoney } from '@/lib/format'

// How one of oraculoto's bets did: prize banner, its numbers (hits green, misses red), hits and the
// winning tiers. The `draw` slot goes right under its numbers: the home page puts the drawn numbers
// there; the contest page leaves it empty, since the draw is already on the page.
// `untitled`: no "Aposta do Oraculoto" over its numbers, when the block around it already says so.
const props = defineProps<{ bet: OraculotoBet; untitled?: boolean }>()

const wins = computed(() => [...props.bet.prizes].sort((a, b) => b.hits - a.hits))
const topWin = computed(() => wins.value[0] ?? null)
</script>

<template>
  <template v-if="bet.status === 'drawn'">
    <p v-if="topWin" class="prize" role="status">
      O Oraculoto acertou a {{ tierName(topWin.hits).toLowerCase() }}!
      <strong>{{ formatMoney(bet.total) }}</strong>
    </p>

    <div class="row">
      <h3 v-if="!untitled">Aposta do Oraculoto</h3>
      <DrawBalls :balls="bet.numbers" :matched="bet.matched" green-hits />
    </div>

    <slot name="draw" />

    <p>
      <strong>{{ bet.hits === 1 ? '1 acerto' : `${bet.hits ?? 0} acertos` }}</strong>
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
    <DrawBalls :balls="bet.numbers" />
    <p v-if="bet.status === 'missing'" class="muted">O resultado deste concurso não está na base.</p>
    <p v-else class="muted">Este concurso ainda não foi sorteado.</p>
  </template>
</template>

<style scoped>
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
</style>
