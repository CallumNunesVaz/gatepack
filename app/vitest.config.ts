import { defineConfig } from 'vitest/config';
import { transform } from 'esbuild';
import { resolve } from 'node:path';

// Vitest config for the Electron main + preload code only.
//
// The renderer has its own vitest config in vite.config.ts (jsdom, scoped to
// app/renderer/**). Main/preload code is CommonJS (tsconfig.main.json) and is
// written as `.cts` files so tsc emits `.cjs` (package.json is `"type":
// "module"`, so plain `.js` would be mis-read as ESM). Vite does not map `.cts`
// to a TypeScript loader by default, so we pre-transform `.cts` files with
// esbuild before Vite's Rollup-based SSR transform sees them.
const ctsTransform = {
  name: 'gatepack-cts-transform',
  enforce: 'pre' as const,
  async transform(code: string, id: string) {
    if (!id.endsWith('.cts')) return null;
    const result = await transform(code, {
      loader: 'ts',
      format: 'esm',
      sourcemap: 'inline',
      sourcefile: id,
    });
    return { code: result.code, map: result.map };
  },
};

export default defineConfig({
  plugins: [ctsTransform],
  resolve: {
    alias: { '@shared': resolve(__dirname, 'shared') },
  },
  test: {
    globals: true,
    environment: 'node',
    include: [
      resolve(__dirname, 'main/**/*.test.ts'),
      resolve(__dirname, 'preload/**/*.test.ts'),
    ],
  },
});
