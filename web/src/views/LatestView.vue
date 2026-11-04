<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { getLatestDraw } from '@/api'
import ContestNav from '@/components/ContestNav.vue'
import DrawDetails from '@/components/DrawDetails.vue'
import LoadError from '@/components/LoadError.vue'
import { useHealth } from '@/lib/health'
import { useLoad } from '@/lib/useLoad'

const { latestContest } = useHealth()
const { data: draw, error, run } = useLoad(getLatestDraw)
onMounted(() => {
  document.title = 'Oraculoto · último resultado da Mega-Sena'
  run()
})

// draws/latest and /health can disagree for a moment around a new crawl; the larger one wins.
const latest = computed(() => {
  const fromHealth = latestContest.value
  const fromDraw = draw.value?.contest ?? null
  return fromHealth === null ? fromDraw : Math.max(fromHealth, fromDraw ?? 0)
})
</script>

<template>
  <div class="page">
    <LoadError v-if="error" :error="error" @retry="run" />
    <DrawDetails v-else :draw="draw" eyebrow="Último resultado" />
    <ContestNav :contest="draw?.contest ?? null" :latest="latest" />
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: 1.5rem;
}
</style>
