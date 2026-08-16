# BUILD NOTES — GUI audit (M13–M16)

Scope: audit the GUI milestones against their §20 exit criteria by driving the
real Electron application against the real Python core, and by running the
core's `--json` commands against real Yosys 0.23 output. Deliverables: the audit
(`docs/GUI-AUDIT.md`), a failing regression spec, and one small renderer honesty
fix.

## Test commands and result

```
$ .venv/bin/python -m pytest tests -q          # 504 passed, 4 skipped (unchanged)
$ cd app && npx tsc --noEmit -p tsconfig.json  # clean
$ cd app && npx tsc --noEmit -p tsconfig.main.json  # clean
$ cd app && npx vitest run                     # 149 passed (was 147)
$ cd app && npm run build:main && npx vite build  # clean
$ cd app && DISPLAY=:1 npx playwright test --config playwright.config.cjs tests/e2e/app.spec.ts
                                               # 9 passed (unchanged)
$ cd app && DISPLAY=:1 npx playwright test --config playwright.config.cjs tests/e2e/gui-audit.spec.ts
                                               # 1 passed, 2 FAILED (intentional — see below)
```

The two failing e2e tests are the regression deliverable. They assert the fixed
behaviour and fail against the current core. Do not "fix" them by weakening an
assertion; they pass when the core defects listed below are closed.

## What I implemented

- `app/tests/e2e/gui-audit.spec.ts` — launches the **real** main process with the
  **real** core (a shim `GATEPACK_CORE` that sets `PYTHONPATH` and execs
  `.venv/bin/python -m gatepack.cli`; the `PYTHONPATH` is needed because the
  core is spawned with cwd = the opened project dir, not the repo root).
  - M13 test (passes): graph edit ("+ state") rewrites `design.yaml`; positions
    never appear in the spec text.
  - M14 test (fails): seeds a `mapped.json` shaped exactly like real Yosys
    post-ABC output (no `port_directions`) and asserts `simulate()` returns real
    `actual` values — currently `"x"`.
  - M15/M16 test (fails): asserts `mappedNetlist()`/`provenance()`/`analyse()`
    are recognised by the core — currently all return GP9002 ("no parseable
    JSON envelope"), the argparse `invalid choice` symptom.
- `app/renderer/views/Schematic.tsx` — report `mappedNetlist()`/`analyse()`
  failures instead of an endless "laying out the netlist…" spinner and a
  misleading "(none reported)". This is a renderer-only change.
- `app/renderer/views/Schematic.test.tsx` — pins those two behaviours.
- `docs/GUI-AUDIT.md` — the audit.

## What I found (the audit result)

| M13 | met — three-way sync + positions-out-of-YAML hold; sidecar is `localStorage` not `design.layout.json` |
| M14 | NOT MET — `simulate` returns `actual: "x"` for every output, so `diverges` is always false |
| M15 | NOT MET — packed/overlay "layers" are text notices; the netlistsvg layer's `mappedNetlist()` call hits a nonexistent subcommand |
| M16 | NOT MET — `provenance()`/`mappedNetlist()` hit nonexistent subcommands; package/property selections map to nothing |

The dominant root cause: `main/session.cts` invokes `gatepack mapped-netlist`,
`gatepack provenance`, `gatepack analyse`; the CLI registers none of them.

The subtlest defect (the "machinery measures nothing" one): `simulate.load_mapped`
does not call `netlist.resolve_parts`, and real Yosys `write_json` carries no
`port_directions`, so `evaluate_mapped_netlist` skips every cell. The one test
that looks like it covers this (`test_cli_simulate_divergent_with_mapped`)
hand-writes a `mapped.json` *with* `port_directions`, a shape the toolchain
never emits.

## Guesses / decisions

- The M15/M16 regression asserts `env.ok || env.error.code !== 'GP9002'`. GP9002
  is the precise symptom of an unrecognised subcommand (empty stdout → no
  parseable JSON). When the subcommands are added, the "no build yet" state will
  be a *different* envelope (by the core's existing pattern: `ok: true` with an
  honest empty, as `simulate`/`estimate` already do), so this assertion is
  unambiguous about "the subcommand exists".
- I did **not** attempt to fix the core (`gatepack/` is off-limits), nor add
  Python regression tests (`tests/` is outside my write scope). The failing e2e
  spec is the regression deliverable; the core fixes are enumerated in
  `docs/GUI-AUDIT.md` "Open items for the core owner".

## What I could not verify

- The M14 `simulate` fix itself (it is core code) — I proved the defect and the
  fix direction in the toolchain container, but the working fix is someone
  else's to land.
- The packed-netlist and per-vector overlay layers, beyond confirming they are
  text, not renders — implementing them needs contract data that does not exist.

## Weakest / least confident

1. My verdict on M13. "met" vs "partial" turns on whether "sidecar" means any
   separate store or specifically the gitignored `design.layout.json`. I scored
   it met on the invariant and flagged the file-location deviation explicitly.
   A reviewer who reads §10.3 literally would call it partial.
2. The `env.ok || code !== 'GP9002'` assertion shape for M15/M16 is a deliberate
   compromise: asserting `ok === true` for `mappedNetlist()`/`analyse()` would
   have assumed a fixed core's "no build" behaviour, which is undefined. GP9002
   is the one thing all three broken calls have in common today and cannot have
   once the subcommands exist.
3. Whether the M14 netlist-evaluation fix belongs in `simulate.load_mapped` or
   in `netlist.parse_mapped_json` (recovering directions from the parts table at
   parse time). The former is a smaller change; the latter is arguably more
   robust for every consumer. I left the choice to the core owner.
