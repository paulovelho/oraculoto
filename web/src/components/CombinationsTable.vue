<script setup lang="ts">
import { computed } from 'vue'
import type { Combinations } from '@/api'
import { formatBall, formatDecimal, formatInt } from '@/lib/format'
import { choose } from '@/lib/stats'

const props = defineProps<{ data: Combinations; pool: number }>()

const total = computed(() => choose(props.pool, props.data.size))
const noun = computed(() => (props.data.size === 2 ? 'pares' : 'trincas'))
</script>

<template>
  <p class="hint">
    Esperado por {{ data.size === 2 ? 'par' : 'trinca' }} num sorteio honesto:
    <strong>{{ formatDecimal(data.expected) }}</strong> vezes. Atenção: estes são os campeões entre
    {{ formatInt(total) }} {{ noun }} possíveis. O topo de uma lista tão longa fica sempre acima do esperado,
    mesmo com bolas perfeitamente aleatórias.
  </p>
  <p v-if="data.items.length === 0" class="muted">Nada nessa janela.</p>
  <div v-else class="scroll">
    <table class="data-table">
      <thead>
        <tr>
          <th scope="col" class="num">#</th>
          <th scope="col">Bolas</th>
          <th scope="col" class="num">Vezes</th>
          <th scope="col" class="num">× esperado</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(c, i) in data.items" :key="c.balls.join('-')">
          <td class="num muted">{{ i + 1 }}</td>
          <th scope="row">
            <span class="mini-balls" :class="{ 'mini-balls--trio': data.size === 3 }">
              <span v-for="b in c.balls" :key="b" class="mini-ball">{{ formatBall(b) }}</span>
            </span>
          </th>
          <td class="num">{{ formatInt(c.times) }}</td>
          <td class="num">{{ data.expected > 0 ? formatDecimal(c.times / data.expected, 1) : '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.scroll {
  overflow-x: auto;
}
/* Three balls plus the number columns don't fit a phone at full size. */
@media (max-width: 420px) {
  .mini-balls--trio {
    gap: 0.2rem;
  }
  .mini-balls--trio .mini-ball {
    width: 1.6rem;
    height: 1.6rem;
    font-size: 0.75rem;
  }
}
</style>
