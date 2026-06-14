import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

// Reuse the app's vite config (the `@` alias + the vue plugin) and add the
// test runner settings. Specs run via esbuild (no type-check); they're
// excluded from tsconfig so `type-check`/`build` stay decoupled from them.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['src/**/*.spec.ts'],
    },
  }),
)
