import { build } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Cargar la configuración de forma programática evita que esbuild recorra los
// directorios superiores del usuario al empaquetar vite.config.js en Windows.
await build({
  configFile: false,
  root: process.cwd(),
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // Evita que Rollup arrastre dependencias compartidas a un chunk manual
        // y forme ciclos artificiales entre grupos de terceros.
        onlyExplicitManualChunks: true,
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('@radix-ui')) return 'radix-ui'
          if (id.match(/[\\/]node_modules[\\/](recharts|d3-|victory-vendor)/)) return 'charts'
          if (id.match(/[\\/]node_modules[\\/](motion|framer-motion)/)) return 'motion'
          if (id.match(/[\\/]node_modules[\\/](@hookform|react-hook-form|zod)/)) return 'forms'
          // React y el resto del runtime se agrupan juntos porque varios
          // paquetes se importan mutuamente; separarlos crea un ciclo de chunks.
          return 'framework'
        },
      },
    },
  },
})
