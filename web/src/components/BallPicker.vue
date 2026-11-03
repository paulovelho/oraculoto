<script setup lang="ts">
import { computed } from 'vue'
import { formatBall } from '@/lib/format'

// A grid of toggle buttons, min..max. Step 4's ticket form will reuse it with a larger `limit`.
const props = defineProps<{ modelValue: number[]; min: number; max: number; limit: number }>()
const emit = defineEmits<{ 'update:modelValue': [number[]] }>()

const balls = computed(() => Array.from({ length: props.max - props.min + 1 }, (_, i) => props.min + i))
const chosen = computed(() => new Set(props.modelValue))
const full = computed(() => props.modelValue.length >= props.limit)

function toggle(n: number) {
  if (chosen.value.has(n)) emit('update:modelValue', props.modelValue.filter((b) => b !== n))
  else if (!full.value) emit('update:modelValue', [...props.modelValue, n].sort((a, b) => a - b))
}
</script>

<template>
  <div class="picker" role="group" :aria-label="`Escolha até ${limit} bolas`">
    <button
      v-for="n in balls"
      :key="n"
      type="button"
      class="cell"
      :class="{ on: chosen.has(n) }"
      :aria-pressed="chosen.has(n)"
      :disabled="full && !chosen.has(n)"
      @click="toggle(n)"
    >
      {{ formatBall(n) }}
    </button>
  </div>
</template>

<style scoped>
.picker {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.35rem;
  max-width: 34rem;
}
.cell {
  aspect-ratio: 1;
  min-width: 0;
  padding: 0;
  font: inherit;
  font-weight: 700;
  font-size: 0.9rem;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 50%;
  cursor: pointer;
}
.cell.on {
  color: #fff;
  background: radial-gradient(circle at 32% 30%, var(--green) 0%, var(--green-deep) 100%);
  border-color: transparent;
}
.cell:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
@media (max-width: 380px) {
  .cell {
    font-size: 0.75rem;
  }
}
</style>
