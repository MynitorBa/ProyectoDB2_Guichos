import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backend = env.VITE_BACKEND_URL || 'http://localhost:8000'
  return {
    plugins: [react(), tailwindcss()],
    publicDir: 'img',
    server: {
      port: Number(env.VITE_PORT || 5173),
      proxy: {
        '/api': backend,
        '/static': backend,
      },
    },
  }
})
