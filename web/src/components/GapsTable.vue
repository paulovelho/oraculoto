<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Gaps } from '@/api'
import { formatBall, formatDecimal, formatInt } from '@/lib/format'

// Current absence first, as the API sends it. All 60 rows are there; the first 10 are shown
// until asked, so the page doesn't open on a wall of numbers.
const props = defineProps<{ data: Gaps }>()

const all = ref(false)
const rows = computed(() => (all.value ? props.data.items : props.data.items.slice(0, 10)))
</script>

<template>
  <p class="hint">
    Num sorteio honesto, uma bola fica em média <strong>{{ formatDecimal(data.expected_gap) }}</strong> concursos sem
    sair entre duas aparições. Uma bola "atrasada" não tem mais chance de sair no próximo: o sorteio não tem memória.
  </p>
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
          <th scope="row">{{ formatBall(g.ball) }}</th>
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
    <button v-if="data.items.length > 10" type="button" class="link" @click="all = !all">
      {{ all ? 'Mostrar só as 10 primeiras' : `Mostrar as ${data.items.length}` }}
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
