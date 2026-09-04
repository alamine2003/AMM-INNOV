/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// Cible du proxy de développement : le backend local, ou le service Docker via VITE_PROXY_TARGET.
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000';
const wsTarget = proxyTarget.replace(/^http/, 'ws');

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': { target: proxyTarget, changeOrigin: true },
      '/ws': { target: wsTarget, ws: true },
    },
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          mui: ['@mui/material', '@mui/icons-material'],
          grid: ['@mui/x-data-grid'],
          charts: ['recharts'],
          pdf: ['react-pdf', 'pdfjs-dist'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    testTimeout: 20000,
    hookTimeout: 20000,
    include: ['src/**/*.test.{ts,tsx}'],
    server: { deps: { inline: ['@mui/x-data-grid'] } },
  },
});
