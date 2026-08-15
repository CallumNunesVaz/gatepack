// Two test projects with genuinely different environments: the renderer runs
// in jsdom, main/preload run in node with a `.cts` pre-transform.
//
// Without this file `vitest run` picks vitest.config.ts alone (it takes
// precedence over vite.config.ts) and the renderer's tests silently stop
// running — 54 of them vanished exactly that way during a merge, with the
// command still reporting a green result.
export default ['./vite.config.ts', './vitest.config.ts'];
