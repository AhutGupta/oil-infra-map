import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Use repository name as base path for GitHub Pages deployment.
  // Override via VITE_BASE_URL env-var if deploying under a different path.
  base: process.env.VITE_BASE_URL ?? '/global-hydrocarbon-map/',
})
