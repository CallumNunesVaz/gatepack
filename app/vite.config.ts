import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// Renderer build. Base must be relative: the packaged app loads the renderer
// from a file:// URL, and an absolute base silently breaks every asset there
// while working fine in `npm run dev`.
export default defineConfig({
  root: resolve(__dirname, 'renderer'),
  base: './',
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, 'dist/renderer'),
    emptyOutDir: true,
    sourcemap: true,
  },
  resolve: {
    alias: { '@shared': resolve(__dirname, 'shared') },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: [resolve(__dirname, 'renderer/**/*.test.{ts,tsx}')],
    setupFiles: [resolve(__dirname, 'vitest.setup.ts')],
  },
});
