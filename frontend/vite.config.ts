import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// `vite.config.ts` lives in `frontend/`; the SPA ships into `<repo>/app/web/`
// so the FastAPI app can serve it from the same origin in production.
// Use an absolute, platform-resolved path so the relative `../../app/web`
// doesn't get mangled by Windows / Git-Bash path normalization.
// `vite.config.ts` lives in `<repo>/frontend/`; the SPA ships into
// `<repo>/app/web/` so the FastAPI app can serve it from the same origin in
// production. Use an absolute, platform-resolved path so the relative
// `../app/web` doesn't get mangled by Windows / Git-Bash path normalization.
const here = dirname(fileURLToPath(import.meta.url))
const outDir = resolve(here, '..', 'app', 'web')

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(here, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/opds': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
    sourcemap: false,
  },
})
