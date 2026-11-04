<script setup lang="ts">
import { onMounted } from 'vue'

// Logos come from public/images and sit directly on the page background.
const CREDITS = [
  {
    role: 'Produção',
    name: 'Paulo Velho',
    href: 'https://guia.lol/paulovelho',
    label: 'guia.lol/paulovelho',
    img: '/images/zebras.png',
    width: 170,
    height: 114,
  },
  {
    role: 'Desenvolvimento',
    name: 'Platypus Web',
    href: 'https://platypusweb.com.br',
    label: 'platypusweb.com.br',
    img: '/images/platypus.png',
    width: 200,
    height: 200,
  },
]

onMounted(() => {
  document.title = 'Créditos · Oraculoto'
})
</script>

<template>
  <section class="about">
    <h1>Créditos</h1>

    <ul class="credits">
      <li v-for="c in CREDITS" :key="c.role" class="block credit">
        <p class="eyebrow">{{ c.role }}</p>
        <a :href="c.href" target="_blank" rel="noopener" class="credit__logo">
          <img :src="c.img" :alt="c.name" :width="c.width" :height="c.height" loading="lazy" />
        </a>
        <h2 class="credit__name">{{ c.name }}</h2>
        <a :href="c.href" target="_blank" rel="noopener">{{ c.label }}</a>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.about {
  display: grid;
  gap: 1.5rem;
}

.credits {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.credit {
  justify-items: center;
  text-align: center;
}

.eyebrow {
  margin: 0;
  color: var(--gold);
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.credit__logo {
  display: grid;
  place-items: center;
  width: 100%;
  height: 160px;
}
.credit__logo img {
  max-height: 136px;
  width: auto;
  height: auto;
}

.credit__name {
  font-size: 1.15rem;
  color: var(--text);
}
</style>
