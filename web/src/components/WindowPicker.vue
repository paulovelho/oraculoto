<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { StatsWindow } from '@/api'
import { formatInt } from '@/lib/format'
import { positiveInt, type WindowSel } from '@/lib/statsQuery'

// One window for every block on the stats page (docs/web.md §6.3). The form is a draft: nothing
// is fetched until "Aplicar", since every change costs ~1.3 s per block.
const props = defineProps<{
  modelValue: WindowSel
  /** What the API actually covered, from any stats response; null while loading. */
  covered: StatsWindow | null
  latest: number | null
}>()
const emit = defineEmits<{ 'update:modelValue': [WindowSel] }>()

const kind = ref<WindowSel['kind']>('all')
const last = ref('')
const from = ref('')
const to = ref('')

function reset() {
  const v = props.modelValue
  kind.value = v.kind
  last.value = v.kind === 'last' ? String(v.last) : '100'
  from.value = v.kind === 'range' && v.from !== null ? String(v.from) : ''
  to.value = v.kind === 'range' && v.to !== null ? String(v.to) : ''
}
watch(() => props.modelValue, reset, { immediate: true, deep: true })

const draft = computed<{ sel: WindowSel } | { error: string }>(() => {
  if (kind.value === 'all') return { sel: { kind: 'all' } }
  if (kind.value === 'last') {
    const n = positiveInt(last.value)
    return n === null ? { error: 'Informe quantos concursos (1 ou mais).' } : { sel: { kind: 'last', last: n } }
  }
  const f = from.value.trim() === '' ? null : positiveInt(from.value)
  const t = to.value.trim() === '' ? null : positiveInt(to.value)
  if ((from.value.trim() !== '' && f === null) || (to.value.trim() !== '' && t === null))
    return { error: 'Concursos são números a partir de 1.' }
  if (f === null && t === null) return { error: 'Informe pelo menos um dos dois concursos.' }
  if (f !== null && t !== null && f > t) return { error: 'O primeiro concurso vem depois do último.' }
  return { sel: { kind: 'range', from: f, to: t } }
})

const changed = computed(
  () => 'sel' in draft.value && JSON.stringify(draft.value.sel) !== JSON.stringify(props.modelValue),
)

function apply() {
  if ('sel' in draft.value) emit('update:modelValue', draft.value.sel)
}
</script>

<template>
  <form class="window block" @submit.prevent="apply">
    <fieldset>
      <legend>Janela</legend>
      <div class="kinds" role="radiogroup">
        <label><input v-model="kind" type="radio" value="all" /> Todo o histórico</label>
        <label><input v-model="kind" type="radio" value="last" /> Últimos</label>
        <label><input v-model="kind" type="radio" value="range" /> Do concurso… ao…</label>
      </div>

      <div class="inputs">
        <label v-if="kind === 'last'">
          <input v-model="last" class="input" type="number" inputmode="numeric" min="1" :max="latest ?? undefined" />
          concursos
        </label>
        <template v-else-if="kind === 'range'">
          <label>
            de
            <input v-model="from" class="input" type="number" inputmode="numeric" min="1" :max="latest ?? undefined" placeholder="1" />
          </label>
          <label>
            até
            <input
              v-model="to"
              class="input"
              type="number"
              inputmode="numeric"
              min="1"
              :max="latest ?? undefined"
              :placeholder="latest ? String(latest) : 'último'"
            />
          </label>
        </template>
        <button class="btn" type="submit" :disabled="!changed">Aplicar</button>
      </div>
    </fieldset>

    <p v-if="'error' in draft" class="error" role="alert">{{ draft.error }}</p>
    <p v-else-if="!covered" class="hint"><span class="skeleton sk">Concursos 0000 a 0000</span></p>
    <p v-else-if="covered.draws === 0" class="hint">Nenhum concurso nessa janela.</p>
    <p v-else class="hint">
      Concursos {{ formatInt(covered.from) }} a {{ formatInt(covered.to) }} ·
      <strong>{{ formatInt(covered.draws) }}</strong> {{ covered.draws === 1 ? 'sorteio' : 'sorteios' }}
    </p>
  </form>
</template>

<style scoped>
fieldset {
  display: grid;
  gap: 0.75rem;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}
legend {
  padding: 0;
  margin-bottom: 0.5rem;
  color: var(--text-muted);
  font-weight: 600;
}
.kinds,
.inputs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1.25rem;
}
.inputs {
  gap: 0.5rem 0.75rem;
}
.kinds label {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  cursor: pointer;
}
.inputs .input {
  width: 7rem;
}
.error {
  color: var(--danger);
  font-size: 0.85rem;
}
</style>
