<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { formatInt } from '@/lib/format'

// Previous / jump-to / next. `latest` null = unknown (health failed): the next link stays, and a
// contest that doesn't exist yet gets the contest page's own 404.
const props = defineProps<{ contest: number | null; latest: number | null }>()

// Past the latest (a contest not drawn yet), "previous" means the latest, not contest - 1.
const prev = computed(() => {
  if (props.contest === null || props.contest <= 1) return null
  return props.latest !== null && props.contest > props.latest ? props.latest : props.contest - 1
})

const router = useRouter()
const target = ref<number | ''>('')
watch(
  () => props.contest,
  () => (target.value = ''),
)

function go() {
  const n = Number(target.value)
  if (Number.isInteger(n) && n >= 1) router.push({ name: 'contest', params: { n: String(n) } })
}
</script>

<template>
  <nav class="contest-nav" aria-label="Navegar entre concursos">
    <RouterLink v-if="prev !== null" class="step" :to="{ name: 'contest', params: { n: String(prev) } }">
      ‹ {{ formatInt(prev) }}
    </RouterLink>
    <span v-else class="step step--off" aria-hidden="true">‹</span>

    <form class="jump" @submit.prevent="go">
      <label for="contest-jump">Ir para o concurso</label>
      <input
        id="contest-jump"
        v-model="target"
        type="number"
        inputmode="numeric"
        min="1"
        :max="latest ?? undefined"
        :placeholder="latest ? `1 a ${formatInt(latest)}` : 'número'"
        required
      />
      <button type="submit">Ver</button>
    </form>

    <RouterLink
      v-if="contest !== null && (latest === null || contest < latest)"
      class="step"
      :to="{ name: 'contest', params: { n: String(contest + 1) } }"
    >
      {{ formatInt(contest + 1) }} ›
    </RouterLink>
    <span v-else class="step step--off" aria-hidden="true">›</span>
  </nav>
</template>

<style scoped>
.contest-nav {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 0.75rem;
}

.step {
  padding: 0.45rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  text-decoration: none;
  white-space: nowrap;
}
.step--off {
  color: var(--border);
}

.jump {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.jump label {
  color: var(--text-muted);
  font-size: 0.85rem;
}
.jump input {
  width: 7.5rem;
  padding: 0.4rem 0.6rem;
  font: inherit;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.jump button {
  padding: 0.4rem 0.9rem;
  font: inherit;
  font-weight: 700;
  color: var(--bg);
  background: var(--gold);
  border: 0;
  border-radius: 8px;
  cursor: pointer;
}

@media (max-width: 520px) {
  .jump label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
}
</style>
