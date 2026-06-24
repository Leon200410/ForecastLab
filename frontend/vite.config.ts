import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api -> backend so the SPA can use relative URLs (no CORS).
// For a static production build, set VITE_API_BASE_URL to the backend origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
})
