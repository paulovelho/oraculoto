<script setup lang="ts">
import type { ApiError } from '@/api'

defineProps<{ error: ApiError }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="load-error" role="alert">
    <p>Não deu para carregar: {{ error.message }}</p>
    <button type="button" @click="$emit('retry')">Tentar de novo</button>
  </div>
</template>

<style scoped>
.load-error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border: 1px solid color-mix(in srgb, var(--danger) 45%, transparent);
  border-radius: var(--radius);
  color: var(--danger);
}
button {
  font: inherit;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.35rem 0.9rem;
  cursor: pointer;
}
</style>
