import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
// base: '/dashboard/' ensures production builds reference assets at /dashboard/assets/...
// so FastAPI can serve them correctly. Does not affect `npm run dev`.
export default defineConfig({
  base: '/dashboard/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Proxy API requests to the FastAPI backend during development.
  // In production, the SPA is served from FastAPI directly so no proxy is needed.
  server: {
    proxy: {
      '/database': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/track': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/stock-data': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
