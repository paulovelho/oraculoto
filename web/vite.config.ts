/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// docs/web.md §2-3: same origin as the API in production; the dev server proxies /api to it.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: {
      '/api': { target: 'https://oraculoto.platypusweb.com.br', changeOrigin: true },
    },
  },
  build: {
    // Never public/: emptyOutDir would delete index.cgi and .htaccess. Deploy rsyncs dist/ over.
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
