import { defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'node',
    // Root app is Newport CRM; ignore other packages that landed on main
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/job-finder/**',
      '**/chrome-extension/**',
      '**/web/**',
    ],
  },
})
