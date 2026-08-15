import { defineConfig } from '@playwright/test';

// Electron end-to-end tests (C9/M12). Lives in tests/e2e/ rather than app/
// because the provided app/playwright.config.ts uses `__dirname`, which is
// undefined when Playwright loads it as an ES module (app/package.json is
// `"type": "module"`). This file sits under a directory tree with no
// package.json, so Playwright loads it as CommonJS and `__dirname` resolves.
// Run from app/ with: npx playwright test --config ../tests/e2e/playwright.config.ts
export default defineConfig({
  testDir: __dirname,
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { trace: 'retain-on-failure' },
});
