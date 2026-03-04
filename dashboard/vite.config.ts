import path from "path"
import fs from "fs"
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

function outputServerPlugin(): Plugin {
  const outputDir = path.resolve(__dirname, '../output')

  function walkDir(dir: string, base: string): string[] {
    const results: string[] = []
    if (!fs.existsSync(dir)) return results
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const rel = path.join(base, entry.name)
      if (entry.isDirectory()) {
        results.push(...walkDir(path.join(dir, entry.name), rel))
      } else {
        results.push(rel)
      }
    }
    return results
  }

  return {
    name: 'output-server',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === '/api/output') {
          try {
            const files = walkDir(outputDir, '')
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(files))
          } catch {
            res.statusCode = 404
            res.end(JSON.stringify([]))
          }
          return
        }

        if (req.url?.startsWith('/api/output/')) {
          const filePath = path.join(outputDir, decodeURIComponent(req.url.slice('/api/output/'.length)))
          if (!filePath.startsWith(outputDir)) {
            res.statusCode = 403
            res.end('Forbidden')
            return
          }
          if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
            res.setHeader('Content-Type', 'application/json')
            fs.createReadStream(filePath).pipe(res)
          } else {
            res.statusCode = 404
            res.end('Not found')
          }
          return
        }

        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), outputServerPlugin()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
