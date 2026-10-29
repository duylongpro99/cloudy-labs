/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'

// POST /__results/<name>.json writes a benchmark result into BENCH_RESULTS_DIR (dev server only).
function saveBenchResults(): Plugin {
  const dir = resolve(process.env.BENCH_RESULTS_DIR ?? resolve(import.meta.dirname, 'bench-results'))
  return {
    name: 'save-bench-results',
    configureServer(server) {
      server.middlewares.use('/__results/', (req, res) => {
        const name = (req.url ?? '').replace(/^\//, '')
        if (req.method !== 'POST' || !/^[\w.-]+\.json$/.test(name)) {
          res.statusCode = 400
          return res.end('bad request')
        }
        let body = ''
        req.on('data', (c) => (body += c))
        req.on('end', () => {
          mkdirSync(dir, { recursive: true })
          writeFileSync(resolve(dir, name), body)
          res.end('saved')
        })
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), saveBenchResults()],
  server: {
    host: '127.0.0.1', // loopback only (NFR7)
    port: 5174,
    strictPort: true,
    // The page talks to the lab-server only, through these two paths (NFR4).
    proxy: {
      '/api': 'http://127.0.0.1:8730',
      '/ws': { target: 'http://127.0.0.1:8730', ws: true },
    },
  },
  test: { environment: 'jsdom' },
})
