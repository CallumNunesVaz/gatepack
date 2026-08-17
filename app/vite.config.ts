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
  // The schematic worker is instantiated with `{ type: 'module' }`, so build it
  // as one. Vite's default worker format is `iife`, and bundling netlistsvg's
  // CommonJS dependency graph into an IIFE left a free `require$$1` as the
  // wrapper's argument — the worker threw `require$$1 is not defined` on load
  // and the view reported "schematic worker failed". The same code compiled as
  // ESM (which is what the in-process fallback chunk always was) has no such
  // reference, which is why the fallback worked and the worker did not.
  worker: {
    format: 'es',
  },
  resolve: {
    alias: {
      '@shared': resolve(__dirname, 'shared'),
      // elkjs's optional Node-only `web-worker` dependency, redirected to the
      // platform `Worker` it stands in for. See renderer/shims/web-worker.ts.
      'web-worker': resolve(__dirname, 'renderer/shims/web-worker.ts'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: [resolve(__dirname, 'renderer/**/*.test.{ts,tsx}')],
    setupFiles: [resolve(__dirname, 'vitest.setup.ts')],
  },
});
