import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  envPrefix: ['VITE_'],  // Only expose VITE_ vars to prevent secret leakage
  server: {
    host: '127.0.0.1', // localhost only - accessible via nginx reverse proxy
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8001', // backend on same EC2
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 5173,
    allowedHosts: true,
  },
})
