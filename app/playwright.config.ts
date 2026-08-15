import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';

// Electron end-to-end tests. These drive the real main process via
// `_electron.launch`, so they exercise the actual §5.2 posture rather than a
// mock of it. There is no browser project and no webServer: Playwright is used
// purely as an Electron driver.
export default defineConfig({
  testDir: resolve(__dirname, '../tests/e2e'),
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { trace: 'retain-on-failure' },
});
