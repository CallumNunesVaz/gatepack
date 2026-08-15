/**
 * Offline Monaco configuration. `@monaco-editor/react` defaults to loading the
 * editor from a CDN; in a packaged Electron app there is no network, so the
 * loader is pointed at the locally installed `monaco-editor` package.
 *
 * This module is imported only by the browser entry point (never by tests, which
 * mock `@monaco-editor/react`).
 */

import { loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';

loader.config({ monaco });

self.MonacoEnvironment = {
  getWorker(_workerId: string, _label: string) {
    // YAML is tokenised by a monarch grammar on the main thread; no language
    // worker is required. Provide a trivial editor worker for basic features.
    return new Worker(
      new URL('monaco-editor/esm/vs/editor/editor.worker.js', import.meta.url),
      { type: 'module' },
    );
  },
};
