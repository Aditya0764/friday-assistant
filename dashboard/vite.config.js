import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/health': API,
      '/chat': API,
      '/voice': API,
      '/documents': API,
      '/trace': { target: API, ws: true },
    },
  },
})