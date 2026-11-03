<script setup lang="ts">
import { computed, watch } from 'vue'
import { getDraw } from '@/api'
import ContestNav from '@/components/ContestNav.vue'
import DrawDetails from '@/components/DrawDetails.vue'
import LoadError from '@/components/LoadError.vue'
import { formatInt } from '@/lib/format'
import { useHealth } from '@/lib/health'
import { useLoad } from '@/lib/useLoad'

// The router only lets positive integers in (router.ts), so this is always a valid number.
const props = defineProps<{ n: string }>()
const contest = computed(() => Number(props.n))

const { latestContest: latest } = useHealth()
const { data: draw, error, run } = useLoad(() => getDraw(contest.value))

watch(
  contest,
  (n) => {
    document.title = `Concurso ${formatInt(n)} · Oraculoto`
    run()
  },
  { immediate: true },
)
</script>

<template>
  <div class="page">
    <section v-if="error?.code === 'not_found'" class="missing">
      <h1>Concurso {{ formatInt(contest) }}</h1>
      <p v-if="latest !== null && contest > latest">
        Ainda não foi sorteado. O último é o
        <RouterLink :to="{ name: 'contest', params: { n: String(latest) } }">{{ formatInt(latest) }}</RouterLink>.
      </p>
      <p v-else>Esse concurso não existe.</p>
    </section>
    <LoadError v-else-if="error" :error="error" @retry="run" />
    <DrawDetails v-else :draw="draw" :eyebrow="latest === contest ? 'Último resultado' : undefined" />

    <ContestNav :contest="contest" :latest="latest" />
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: 1.5rem;
}
.missing {
  display: grid;
  gap: 0.5rem;
}
.missing p {
  color: var(--text-muted);
}
</style>
