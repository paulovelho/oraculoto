<template>
  <section class="not-found">
    <h1>Página não encontrada</h1>
    <p>Nem o oráculo previu esse endereço.</p>
    <RouterLink to="/">Voltar ao início</RouterLink>
  </section>
</template>

<style scoped>
.not-found {
  display: grid;
  gap: 0.75rem;
  justify-items: start;
}

p {
  color: var(--text-muted);
}
</style>
