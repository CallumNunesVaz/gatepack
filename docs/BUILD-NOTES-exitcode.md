# BUILD NOTES — exit code / envelope contract ("core exited 1")

## The defect

`gatepack verify --json` on a host without yosys emits a complete, schema-valid
envelope with `ok: true`, `allPassed: false`, and per-check
`status: "not_run"` + `skippedReason` naming the missing tool — exactly the
visible state §C15 wants — **and exits 1** (because `allPassed` is false).

`app/main/core.cts` (~line 240) then threw that envelope away: any non-zero exit
with `ok: true` was treated as "a lying core" and replaced with a bare
`GP9004 "core exited 1"` envelope. The most informative envelope the tool
produces was destroyed by a guard that was written for a different failure.

## The contract question — resolved here, not in api.ts

`app/shared/api.ts` says (authoritatively, and it is off-limits to edit):

> Exit code is 0 for `ok: true` and non-zero otherwise; the renderer must key on
> `ok`, never on the exit code alone.

Two readings collided:

1. `ok` describes the command, so `verify` "ran perfectly and reports that three
   checks did not run" → `ok: true`, and exiting 1 violates the contract.
2. A non-zero exit for a failed verification is useful for shell/CI, and
   removing it would regress CLI users.

Both are right; the contract was underspecified. The resolution, which I could
not write into `api.ts` (that file is on the do-not-edit list) and so record
here as prose:

> **`ok` answers one question: "did the command execute, and is this envelope
> its answer?"** A schema-valid envelope is authoritative regardless of the exit
> code. **The exit code additionally answers a second question: "is the answer
> all-green?"** — it exists for shell scripts and CI, not for the renderer. The
> renderer must key on `ok` (and, for `verify`, on `allPassed` / per-check
> `status`), never on the exit code.

Which commands use their exit code that way (measured, table below): **`verify`
is the only one.** Every other command is either `ok: true` + exit 0 (success,
or a report like `lib check`/`doctor` that carries its findings in the payload)
or `ok: false` + exit 1 (a hard error). Only `verify` can legitimately emit
`ok: true` + non-zero exit, and it does so exactly when not all checks passed
and not all ran.

Consequently the main-process guard must fire **only when the envelope is absent
or unparseable** (a core that died mid-run and left a truncated/missing
envelope), never when a valid `ok: true` envelope accompanies a non-zero exit.

## The fix

`app/main/core.cts` `runEnvelope`'s `close` handler:

- A valid `ok: true` envelope now passes through intact, whatever the exit code.
- The "crashed core" case — absent or truncated stdout — was *already* handled
  by `parseEnvelope` (which returns a `GP9002`/`GP9003` `ok: false` envelope for
  unparseable/invalid stdout). The old guard never actually caught it: for
  garbage stdout `parseEnvelope` returns `ok: false`, so the `code !== 0 &&
  envelope.ok` branch did not fire there either — it only ever fired for the one
  case we now deem legitimate.
- To keep that case honest (and better than before), when the core exited
  non-zero **and** the envelope is a parse/validation failure (`GP9002`/`GP9003`),
  the error message is annotated with `core exited N` and the core's stderr, so a
  crashed core still surfaces a visible, actionable error and never a silent
  empty result. A core's own `ok: false` envelope (e.g. `GP1006`) is passed
  through unchanged.

The old `GP9004` code is gone; nothing else referenced it.

## Exit-code / ok audit (recorded, both toolchains)

Run with `--json`; `ok` read from the envelope. Host has no yosys; the
`gatepack-toolchain:m6` container has Yosys 0.23, sby, Icarus, z3.

| command     | host (no yosys)     | container (yosys)   | why                              |
|-------------|---------------------|---------------------|----------------------------------|
| `lib check` | exit 0, ok:true     | (not re-run)        | report; missing citations/refs are payload findings, never a gate (§C2) |
| `estimate`  | exit 0, ok:true     | exit 0, ok:true (amber) | verdict (green/amber/red) is data, not exit code |
| `verify`    | exit 1, ok:true     | exit 0, ok:true (all 7 passed) | **the one divergent command**: exit 0 iff `report.ok`, i.e. no failure and no not-run |
| `build`     | exit 1, ok:false    | exit 0, ok:true     | hard error without yosys/`--mapped` (GP1006) |
| `simulate`  | exit 0, ok:true     | exit 0, ok:true     | divergence is a data column, not exit code |
| `analyse`   | exit 1, ok:false    | exit 0, ok:true     | hard error without `mapped.json` |
| `provenance`| exit 1, ok:false    | exit 0, ok:true     | hard error without captured netlists |
| `doctor`    | exit 0, ok:true     | exit 0, ok:true     | report; `allToolsPresent:false` is a visible entry, exit stays 0 |

Note the container `verify` produces all-seven-passed → `allPassed:true`. The
host `verify` produces `not_run` checks → `allPassed:false` + exit 1, with
`skippedReason`s. Both are `ok:true`.

## Tests

`app/main/core.test.ts` (unit, via a fake shell core):

- *Changed* `surfaces a non-zero exit that claimed ok as an error envelope`
  → `passes a valid ok envelope through even when the core exits non-zero`
  (the `verify` not-run shape). **Red before the fix**: `expect(env.ok).toBe(true)`
  failed with `expected false to be true` — the old guard returned the `GP9004`
  error. Green after.
- *Added* `a non-zero exit with no envelope surfaces a visible error, never a
  silent empty result` (empty stdout + exit 1 → `GP9002` + `core exited 1`).
  **Red before the fix** only on the annotation (`expected ... to contain 'core
  exited 1'`); the `ok:false` was already produced by `parseEnvelope`.
- *Added* `a truncated envelope with a non-zero exit surfaces a visible error`
  (partial JSON + exit 1 → `GP9002` + `core exited 1`). Red for the same reason.

`app/tests/e2e/verify-missing-tools.spec.ts` (new, real main process):

- Launches the app with `GATEPACK_FAKE_NONZERO_OK=verify`, opens a project, runs
  verification, and asserts the Verification panel renders
  `verification-result` ("Not all checks passed") with a `not_run` check and a
  yosys skip reason, and that `verification-error` is absent. **Red before the
  fix**: `getByTestId('verification-result')` never appeared (the panel showed
  `core exited 1` instead), timing out. Green after.

`app/tests/e2e/fake-core.cjs`:

- New honesty hook `GATEPACK_FAKE_NONZERO_OK` (comma-separated commands). For
  `verify` it emits `verifyNotRunData()` — a `not_run`/`skippedReason` payload
  copied field-for-field from the real core's missing-toolchain output — and
  exits 1. This is the real core's one legitimate non-zero `ok:true` shape.

## What I could not / did not verify

- A genuinely *failing* verify (exit 1 + `ok:true` + a `failed` check with a
  counterexample) was not constructed in the container; it shares the exact code
  path as the `not_run` case (`return EXIT_OK if result.report.ok else
  EXIT_ERROR` in `_cmd_verify`), so the behaviour is pinned by the existing
  `tests/contract/test_cli_contract.py::test_verify_exits_error_without_tools`
  and by inspection, not by a fresh failing design.
- I did **not** edit `app/shared/api.ts` (off-limits). The contract resolution
  above is prose *about* that file, and the code comment in `core.cts` records
  the resolution at the one seam I own. If the reviewer wants the resolution
  inside `api.ts` itself, that edit belongs to the api.ts owner.

## Suspicions / weakest

1. **`bounded` vs `report.ok` is a latent mismatch in the other direction.**
   `report.ok` (`gatepack/verify/base.py`) is `not has_failure and not
   has_not_run`, so a `bounded` check (k-induction did not close, §21.5) makes
   `report.ok` true → `verify` exits 0, while the envelope's `allPassed` requires
   every check `status === "passed"` → false. So a bounded-only verification
   exits 0 with `ok:true` + `allPassed:false`. The renderer is correct (keys on
   `allPassed`), but a shell user scripting on the exit code would read "green"
   for a result §21.5 insists must never render as a pass. I did not change
   `cli.py` for this: it is a core-contract question, not the app-side mismatch
   this task is about, and the existing contract test only pins the not-run path.
2. **The stderr annotation may leak a multi-line traceback into a one-line
   error message.** A genuinely crashed core's stderr is appended verbatim to
   `error.message`; the renderer renders it in a single `<span>`. Useful, but a
   very long traceback will wrap ugly. I judged "visible and actionable" worth
   it over truncation, which is a guess.
3. **Whether the annotation threshold (`GP9002`/`GP9003` only) is too narrow.**
   A core that exits non-zero with a legitimate `ok:false` envelope (e.g.
   `GP1006`) is passed through without the exit code or stderr attached — I
   assumed its own diagnostic is already the full story, and appending stderr
   would duplicate it. If a future command emits an `ok:false` whose message is
   less self-explanatory, this threshold would need widening.
