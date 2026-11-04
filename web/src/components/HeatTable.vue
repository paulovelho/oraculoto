<script setup lang="ts">
import { computed } from 'vue'
import type { Heat } from '@/api'
import { formatBall, formatDecimal, formatInt } from '@/lib/format'

// The 10 hottest or coldest balls by heat (docs/api.md §4): how many times each came out in the
// last 100 contests, against what its own long-run rate predicts. The same score oraculoto uses
// to complete its bet.
const props = defineProps<{ data: Heat; order: 'hot' | 'cold' }>()

const SHOWN = 10
const rows = computed(() => {
  const items = props.order === 'hot' ? props.data.items : [...props.data.items].reverse()
  return items.slice(0, SHOWN).map((i) => ({ ...i, expected: i.recent - i.heat }))
})
const signed = (n: number) => (n > 0 ? '+' : '') + formatDecimal(n)
</script>

<template>
  <div class="scroll">
    <table class="data-table">
      <thead>
        <tr>
          <th scope="col">Bola</th>
          <th scope="col" class="num">Últimos {{ formatInt(data.window.draws) }}</th>
          <th scope="col" class="num">Esperado</th>
          <th scope="col" class="num">Calor</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="h in rows" :key="h.ball">
          <th scope="row"><span class="mini-ball">{{ formatBall(h.ball) }}</span></th>
          <td class="num">{{ formatInt(h.recent) }}</td>
          <td class="num">{{ formatDecimal(h.expected, 1) }}</td>
          <td class="num" :class="h.heat > 0 ? 'hot' : 'cold'">{{ signed(h.heat) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="hint">
    Sempre os últimos {{ formatInt(data.window.draws) }} concursos (#{{ data.window.from }}–#{{ data.window.to }}),
    seja qual for a janela acima. "Esperado" é o que a taxa da própria bola, em todo o histórico, daria nesse trecho.
  </p>
</template>

<style scoped>
.scroll {
  overflow-x: auto;
}
.hot {
  color: var(--gold);
}
.cold {
  color: var(--text-muted);
}
</style>
