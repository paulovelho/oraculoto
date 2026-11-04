<script setup lang="ts">
import { formatBall } from '@/lib/format'

// `matched` given: a bet against its draw. Matched balls stay green, the rest turn red.
// `tone="gold"`: the drawn numbers next to a bet, so they don't read as hits.
defineProps<{ balls: number[]; matched?: number[] | null; tone?: 'gold' }>()
</script>

<template>
  <ol class="balls">
    <li
      v-for="(n, i) in balls"
      :key="i"
      class="ball"
      :class="{ 'ball--miss': matched && !matched.includes(n), 'ball--gold': tone === 'gold' }"
    >
      {{ formatBall(n) }}
    </li>
  </ol>
</template>

<style scoped>
.balls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.ball {
  display: grid;
  place-items: center;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 30%, var(--green) 0%, var(--green-deep) 100%);
  color: #fff;
  font-weight: 800;
  font-size: 1.3rem;
  box-shadow: inset 0 -3px 6px rgb(0 0 0 / 0.25);
}

.ball--miss {
  background: color-mix(in srgb, var(--danger) 18%, var(--surface-2));
  color: color-mix(in srgb, var(--danger) 70%, var(--text-muted));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 35%, var(--border));
}

.ball--gold {
  background: radial-gradient(circle at 32% 30%, var(--gold) 0%, var(--gold-deep) 100%);
  color: var(--bg);
}

@media (max-width: 420px) {
  .ball {
    width: 2.75rem;
    height: 2.75rem;
    font-size: 1.1rem;
  }
}
</style>
