/**
 * Browser stand-in for the `web-worker` package.
 *
 * elkjs (pulled in by netlistsvg) contains `require('web-worker')` behind a
 * `require.resolve` guard — it is an *optional* dependency that only matters in
 * Node, where `Worker` is not a global. It is not installed here, and at
 * runtime elkjs never reaches that branch: netlistsvg constructs ELK without a
 * `workerUrl`, so the bundled fake worker is used.
 *
 * A bundler cannot see that, though. Rollup resolved the bare specifier
 * statically and emitted `import from "web-worker"` into the schematic worker
 * chunk, which no browser can resolve — the worker died on load and the view
 * reported "schematic worker failed".
 *
 * This is what the real package's own browser build is: the platform `Worker`.
 * It is a redirect to the genuine article, not a stub that pretends to work.
 */
const BrowserWorker = (globalThis as unknown as { Worker: typeof Worker }).Worker;

export default BrowserWorker;
