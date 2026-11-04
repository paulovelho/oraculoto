<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getTogether, type Query } from '@/api'
import BallPicker from '@/components/BallPicker.vue'
import LoadError from '@/components/LoadError.vue'
import { formatBall, formatDate, formatDecimal, formatInt } from '@/lib/format'
import type { BallRules, TogetherSel } from '@/lib/statsQuery'
import { useLoad } from '@/lib/useLoad'

// "Did these balls ever come out together?" The selection lives in the URL (the parent owns it);
// the picker and the jackpot box are a draft until "Consultar".
const props = defineProps<{ rules: BallRules; window: Query; value: TogetherSel }>()
const emit = defineEmits<{ change: [TogetherSel] }>()

const LIMIT = 20

const draft = ref<number[]>([])
const jackpot = ref(false)
watch(
  () => props.value,
  (v) => {
    draft.value = [...v.balls]
    jackpot.value = v.jackpot
  },
  { immediate: true, deep: true },
)

const changed = computed(
  () => draft.value.join(',') !== props.value.balls.join(',') || jackpot.value !== props.value.jackpot,
)

function submit() {
  if (draft.value.length) emit('change', { balls: [...draft.value], jackpot: jackpot.value, page: 1 })
}
function clear() {
  draft.value = []
  emit('change', { balls: [], jackpot: false, page: 1 })
}
function goPage(page: number) {
  emit('change', { ...props.value, page })
}

const { data, error, loading, run } = useLoad(() =>
  getTogether(props.window, props.value.balls, props.value.jackpot, props.value.page, LIMIT),
)
const key = computed(() => JSON.stringify([props.window, props.value]))
watch(key, () => props.value.balls.length && run(), { immediate: true })

const summary = computed(() => {
  const d = data.value
  if (!d) return ''
  const one = d.balls.length === 1
  const where = d.jackpot ? ' entre os concursos em que a Sena saiu' : ''
  if (d.total === 0) return `${one ? 'nunca saiu' : 'nunca saíram juntas'}${where} nessa janela.`
  const times = `${formatInt(d.total)} ${d.total === 1 ? 'concurso' : 'concursos'}`
  return `${one ? 'saiu' : 'saíram juntas'} em ${times}${where} nessa janela.`
})

const pages = computed(() => (data.value ? Math.max(1, Math.ceil(data.value.total / data.value.limit)) : 1))
</script>

<template>
  <form class="together" @submit.prevent="submit">
    <p class="hint">
      Escolha de 1 a {{ rules.balls_drawn }} bolas para ver em quais concursos saíram todas juntas, comparado com
      o que o acaso daria.
    </p>
    <div class="layout">
      <BallPicker v-model="draft" :min="rules.ball_min" :max="rules.ball_max" :limit="rules.balls_drawn" />

      <div class="side">
        <div class="controls">
          <label><input v-model="jackpot" type="checkbox" /> Só concursos em que a Sena saiu</label>
          <div class="buttons">
            <button class="btn" type="submit" :disabled="!draft.length || !changed">Consultar</button>
            <button v-if="draft.length || value.balls.length" class="btn btn--ghost" type="button" @click="clear">Limpar</button>
          </div>
        </div>

        <template v-if="value.balls.length">
          <LoadError v-if="error" :error="error" @retry="run" />
          <div v-else-if="loading || !data" class="skeleton sk sk--block" aria-busy="true"></div>
          <div v-else class="result" aria-live="polite">
            <p class="summary">
              <strong>{{ data.balls.map(formatBall).join(' · ') }}</strong> {{ summary }} O acaso daria em média
              <strong>{{ formatDecimal(data.expected) }}</strong>.
            </p>
            <p v-if="data.jackpot" class="hint">
              O esperado supõe que as bolas não influenciam se alguém acerta a Sena.
            </p>

            <template v-if="data.items.length">
              <ul class="contests">
                <li v-for="c in data.items" :key="c.contest">
                  <RouterLink :to="{ name: 'contest', params: { n: String(c.contest) } }">{{ formatInt(c.contest) }}</RouterLink>
                  <span class="muted">{{ formatDate(c.date) }}</span>
                </li>
              </ul>
              <nav v-if="pages > 1" class="pager" aria-label="Páginas">
                <button class="btn btn--ghost" type="button" :disabled="data.page <= 1" @click="goPage(data.page - 1)">‹ Anterior</button>
                <span class="muted">página {{ data.page }} de {{ pages }}</span>
                <button class="btn btn--ghost" type="button" :disabled="data.page >= pages" @click="goPage(data.page + 1)">Próxima ›</button>
              </nav>
            </template>
            <p v-else-if="data.total > 0" class="muted">
              Essa página não existe. <button class="btn btn--ghost" type="button" @click="goPage(1)">Voltar à primeira</button>
            </p>
          </div>
        </template>
      </div>
    </div>
  </form>
</template>

<style scoped>
.together {
  display: grid;
  gap: 0.75rem;
}
/* Picker on the left, controls + result on the right; stacked on narrow screens. */
.layout {
  display: grid;
  grid-template-columns: minmax(0, 34rem) minmax(15rem, 1fr);
  gap: 1rem 1.5rem;
  align-items: start;
}
.side {
  display: grid;
  gap: 1rem;
  align-content: start;
}
.controls {
  display: grid;
  gap: 0.75rem;
}
.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
@media (max-width: 720px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
.controls label {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  cursor: pointer;
}
.result {
  display: grid;
  gap: 0.75rem;
}
.contests {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: 0.35rem 1rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.contests li {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}
.pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}
</style>
