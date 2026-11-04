<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Gaps } from '@/api'
import { formatBall, formatInt } from '@/lib/format'

// All 60 rows are there; the first 20 (in the chosen order, to match the
// 20 rows of "Mais frequentes" next to it) are shown until asked, so the page
// doesn't open on a wall of numbers. Ties keep ball order.
const props = defineProps<{ data: Gaps; order: 'most' | 'least' }>()

const SHOWN = 20
const all = ref(false)
const sorted = computed(() => {
  const dir = props.order === 'most' ? -1 : 1
  return [...props.data.items].sort((a, b) => dir * (a.current_gap - b.current_gap) || a.ball - b.ball)
})
const rows = computed(() => (all.value ? sorted.value : sorted.value.slice(0, SHOWN)))
</script>

<template>
  <div class="scroll">
    <table class="data-table">
      <thead>
        <tr>
          <th scope="col">Bola</th>
          <th scope="col" class="num">Ausente há</th>
          <th scope="col" class="num">Maior ausência</th>
          <th scope="col" class="num">Última vez</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="g in rows" :key="g.ball">
          <th scope="row"><span class="mini-ball">{{ formatBall(g.ball) }}</span></th>
          <td class="num">{{ formatInt(g.current_gap) }}</td>
          <td class="num">{{ formatInt(g.longest_gap) }}</td>
          <td class="num">
            <RouterLink v-if="g.last_seen !== null" :to="{ name: 'contest', params: { n: String(g.last_seen) } }">
              {{ formatInt(g.last_seen) }}
            </RouterLink>
            <span v-else class="muted">não saiu</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="hint">
    Em concursos, dentro da janela. "Maior ausência" só conta intervalos entre duas aparições.
    <button v-if="data.items.length > SHOWN" type="button" class="link" @click="all = !all">
      {{ all ? `Mostrar só as ${SHOWN} primeiras` : `Mostrar as ${data.items.length}` }}
    </button>
  </p>
</template>

<style scoped>
.scroll {
  overflow-x: auto;
}
.link {
  padding: 0;
  font: inherit;
  color: var(--gold);
  background: none;
  border: 0;
  text-decoration: underline;
  cursor: pointer;
}
</style>
