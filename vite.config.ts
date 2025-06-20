import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

const certPath = path.join(process.cwd(), 'cert.pem')
const keyPath = path.join(process.cwd(), 'key.pem')

// Check if SSL certificates exist
const useHttps = fs.existsSync(certPath) && fs.existsSync(keyPath)

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true
  },
  server: {
    port: 3000,
    https: useHttps ? {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath),
    } : false
  }
}) 