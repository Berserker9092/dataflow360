import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// L'API FastAPI tourne sur le port 8000. En développement, Vite relaie /api vers elle :
// pas de problème de CORS et aucune URL à configurer.
const target = process.env.VITE_API_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/health': { target, changeOrigin: true },
    },
  },
  preview: { proxy: { '/api': { target, changeOrigin: true } } },
  test: { environment: 'jsdom', globals: true },
})
