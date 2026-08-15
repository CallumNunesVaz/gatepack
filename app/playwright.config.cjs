// Electron end-to-end tests (C9/M12). These drive the real main process via
// `_electron.launch`, so they exercise the actual §5.2 security posture rather
// than a mock of it. There is no browser project and no webServer: Playwright
// is used purely as an Electron driver.
//
// `.cjs`, deliberately. app/package.json is `"type": "module"`, so a `.ts` or
// `.js` config here is loaded as ESM — where `@playwright/test` exposes no
// named `defineConfig` export and `__dirname` is undefined. Keeping the config
// The specs live under app/tests/e2e rather than the repo-root tests/e2e of
// §17 for the same reason: Node resolves node_modules by walking up from the
// importing file, and nothing above the repo-root tests/ directory has one.
const { defineConfig } = require('@playwright/test');
const { resolve } = require('node:path');

module.exports = defineConfig({
  testDir: resolve(__dirname, 'tests/e2e'),
  testMatch: '**/*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: { trace: 'retain-on-failure' },
});
