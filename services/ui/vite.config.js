import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/submissions': 'http://localhost:8000',
      '/approvals': 'http://localhost:8000',
      '/audit': 'http://localhost:8000',
    }
  }
})
