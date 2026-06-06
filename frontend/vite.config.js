import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/events": "http://localhost:8000",
      "/agents": "http://localhost:8000",
      "/data-source": "http://localhost:8000",
      "/simulate": "http://localhost:8000",
      "/relationships": "http://localhost:8000",
      "/forecasts": "http://localhost:8000",
      "/recommendations": "http://localhost:8000",
      "/voice": "http://localhost:8000",
    },
  },
})
