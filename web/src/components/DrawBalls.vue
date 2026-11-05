<script setup lang="ts">
import { formatBall } from '@/lib/format'

// `matched` given: a bet against its draw. Matched balls stay white, the rest turn red.
// `tone="gold"`: the drawn numbers next to a bet, so they don't read as hits.
// `greenHits`: matched balls turn green instead of staying white (home page's past bet).
defineProps<{ balls: number[]; matched?: number[] | null; tone?: 'gold'; greenHits?: boolean }>()
</script>

<template>
  <ol class="balls">
    <li
      v-for="(n, i) in balls"
      :key="i"
      class="ball"
      :class="{
        'ball--miss': matched && !matched.includes(n),
        'ball--gold': tone === 'gold',
        'ball--hit': greenHits && matched && matched.includes(n),
      }"
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
  /* White lottery ball, same 3D treatment as .mini-ball (style.css), scaled up. */
  background:
    radial-gradient(circle at 32% 28%, #fff 0%, rgb(255 255 255 / 0) 38%),
    radial-gradient(circle at 40% 35%, #f7f5f2 0%, #e2dfda 55%, #a9a4a0 100%);
  color: #111;
  font-weight: 800;
  font-size: 1.3rem;
  box-shadow:
    inset -3px -5px 8px rgb(0 0 0 / 0.28),
    inset 2px 2px 3px rgb(255 255 255 / 0.9),
    0 3px 5px rgb(0 0 0 / 0.45);
}

.ball--miss {
  background: color-mix(in srgb, var(--danger) 18%, var(--surface-2));
  color: color-mix(in srgb, var(--danger) 70%, var(--text-muted));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 35%, var(--border));
}

.ball--hit {
  background:
    radial-gradient(circle at 32% 28%, rgb(255 255 255 / 0.55) 0%, rgb(255 255 255 / 0) 38%),
    radial-gradient(circle at 40% 35%, var(--green) 0%, var(--green-deep) 100%);
  color: #111;
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
