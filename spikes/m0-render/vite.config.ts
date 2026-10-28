import react from '@vitejs/plugin-react'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'

// POST /__results/<name>.json writes a benchmark result into ./results (dev server only).
function saveResults(): Plugin {
  const dir = resolve(import.meta.dirname, 'results')
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
  plugins: [react(), saveResults()],
  server: { port: 5173, strictPort: true },
})
