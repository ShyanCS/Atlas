import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const securityHeaders = {
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'same-origin',
}
const apiTarget = process.env.ATLAS_DEV_API_TARGET ?? 'http://127.0.0.1:8000'
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(apiTarget))
  throw new Error('Development API target must use loopback.')
const apiProxy = { '/api': { target: apiTarget, changeOrigin: false } }

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    allowedHosts: ['127.0.0.1'],
    fs: { strict: true, allow: [fileURLToPath(new URL('.', import.meta.url))] },
    headers: securityHeaders,
    proxy: apiProxy,
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
    strictPort: true,
    headers: securityHeaders,
    proxy: apiProxy,
  },
  test: {
    pool: 'threads',
    maxWorkers: 2,
    fsModuleCache: false,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
  },
})
