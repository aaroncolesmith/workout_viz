import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'

function shortSha() {
  try {
    return execSync('git rev-parse --short HEAD').toString().trim()
  } catch {
    return 'unknown'
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Surfaced in Settings so a stale WKWebView (backgrounded, not reloaded)
    // is obvious to spot instead of silently running old JS.
    __APP_BUILD__: JSON.stringify({ sha: shortSha(), time: new Date().toISOString() }),
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
