import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8080',
      '/agent': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
      '/models': 'http://localhost:8080',
      '/providers': 'http://localhost:8080',
      '/orchestrate': 'http://localhost:8080',
      '/vergadertafel': 'http://localhost:8080'
    }
  }
})
