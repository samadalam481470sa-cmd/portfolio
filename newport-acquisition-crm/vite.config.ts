import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  // GH_PAGES: served from https://<user>.github.io/portfolio/
  // STATIC_DEMO: path-agnostic build for CDN hosting (relative assets + hash routing)
  base: process.env.STATIC_DEMO ? './' : process.env.GH_PAGES ? '/portfolio/' : '/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // Inline the Newport logo into the JS bundle so CDN demos don't rely on
    // relative image fetches (many raw CDNs serve HTML as text/plain or rate-limit assets).
    assetsInlineLimit: process.env.STATIC_DEMO ? 200_000 : 4096,
  },
  server: {
    host: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
})
