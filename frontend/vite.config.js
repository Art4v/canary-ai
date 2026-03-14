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
})
