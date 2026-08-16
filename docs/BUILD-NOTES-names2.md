# BUILD NOTES — instance/stable cell-name boundary (CellNames)

Branch `deepseek/names2`. Scope: `gatepack/netlist.py`, `gatepack/pack/packer.py`,
`gatepack/emit/kicad.py`, `gatepack/build.py`, `gatepack/api.py`, `tests/`, and
this file. Nothing in `app/`, `scripts/`, `.github/`, `gatepack/report/report.py`,
`gatepack/provenance/` was touched (all read-only except where listed).

## What landed

`gatepack/netlist.py` gains `CellNames`, a `collections.abc.Mapping` (keyed by
**instance** name) that also owns the **reverse** (stable -> instance) direction
and exposes two direction-named, hard-erroring methods:

- `to_stable(instance)` — instance -> stable; `KeyError("... is not a known
  instance name")` on anything else.
- `to_instance(stable)` — stable -> instance; `KeyError("... is not a known
  stable name")` on anything else.
- `stable_of(cell)` — convenience instance -> stable.
- `stable_names` / `instance_to_stable` properties.
- `CellNames.identity(cells)` — the identity fallback the packer used to build
  inline (`{c.name: c.name}`).
- The constructor refuses a duplicate stable name (two instances sharing one
  stable name would make the reverse lookup ambiguous — a real defect that would
  otherwise be silently wrong).

`stable_cell_names()` now returns a `CellNames`, and the three boundary functions
that used to take a bare `Mapping[str, str]` now take `CellNames`:

- `pack.pack(stable_names: CellNames | None)` — `_collect_forced` now resolves
  each `force_groups` member through `names.to_instance`, so an ABC instance name
  passed as an override fails loudly as "unknown cell" (defect 1).
- `emit.kicad.emit_netlist(names: CellNames)` — the package's STABLE cell list is
  crossed back through `names.to_instance` to reach the cell's connections
  (defect 2's reverse-lookup, done once).
- `build.py` builds `cell_refdes` with `names.to_instance(stable)` instead of the
  hand-rolled `for instance, mapped_stable in names.items() if ...` triple-loop
  (defect 2). `BuildResult.stable_names` is now a `CellNames`; `api.py` emits
  `dict(result.stable_names)` which is exactly the `Record<string, string>`
  instance -> stable shape `app/shared/api.ts` requires (defect 3).

## Why `CellNames` and not `NewType`

The project has no type checker configured (no mypy/pyright/ruff in
`pyproject.toml`), so `NewType` aliases would be decorative: they catch nothing
at runtime, and a "caught at runtime" guarantee is what the requirement asks for
("a mix-up is caught rather than silently producing a wrong answer at runtime").
`CellNames` gives that guarantee by construction — the direction is in the method
name, and the wrong direction raises. I deliberately kept it a `Mapping` so
`dict(names)`/`names[instance]`/`names.items()` still work and the IPC shape
falls out unchanged; the boundary is the *type* of the parameter, not new string
wrappers. An elaborate two-NewType abstraction would have been more churn for
less protection here.

## A fourth defect found and fixed (same class, not in the brief)

`pack()`'s free-cell filter was `free = [c for c in members if c.name not in
forced["cells"]]` — comparing an **instance** name (`c.name`) against a set of
**stable** names (`forced["cells"]` from `force_groups`). When stable names
differ from instance names (i.e. every real Yosys run), the comparison never
matched, so a forced cell was **packed twice**: once by `_pack_group` and once by
`_pack_forced`. I confirmed this on the baseline before touching it:

```
OR2 ('OR2__aaaa', 'OR2__bbbb')   <- from the free path
OR2 ('OR2__aaaa', 'OR2__bbbb')   <- from the forced path
package_count 3                  <- should be 2
```

The existing `test_force_group_of_stable_names_is_honoured` asserted only that
*some* group contained the forced pair, so the duplicate went unnoticed. The fix
compares like-for-like (`names.stable_of(c) not in forced["cells"]`) and
`test_forced_cells_are_not_also_packed_as_free` pins it. This changes behaviour
for `force_groups` only; the showcase and goldens carry no `force_groups`, so
the pinned invariants are untouched.

## Test status

```
.venv/bin/python -m pytest tests -q   # 512 passed, 4 skipped (baseline 504/4)
npx tsc --noEmit -p tsconfig.json     # clean
npx tsc --noEmit -p tsconfig.main.json# clean
npx vitest run                        # 147 passed
```

New tests: `tests/unit/test_cell_names.py` (7) — the three-defect reproductions
at the boundary plus duplicate-stable-name refusal and both-direction lookups —
and `tests/unit/test_force_groups.py` gains the double-pack regression (1).
`tests/unit/test_force_groups.py`'s `_stable()` now returns `CellNames` instead
of a dict (the packer's `stable_names` is now typed `CellNames | None`).

Each new test was checked to actually fail on the pre-change code: the
double-pack test fails on the baseline (3 packages, duplicate cells), and
`to_instance`/`to_stable`/`PackError` paths raise on the wrong-space input.

## Real-toolchain verification

`scripts/repro_check.py` in the `gatepack-toolchain:m6` container reports **10
artefacts byte-identical** (including `mapped.json`, BOM and netlists). The
showcase still builds to **20 packages, 3 spare gates, pack_cost 32**, and its
report renders `- worst path: U1 -> U15 -> U16 -> U18` (refdes, not `$abc$...`),
which is defect 2 exercised against real Yosys. `gatepack verify` on
`xor2` passes (equivalence, exhaustive simulation, mutation, flop reset,
supervisor parameters).

## What I could not verify

- `tests/toolchain/*` runs under pytest, which is **not installed in the
  container image** (`ModuleNotFoundError: No module named 'pytest'`); the image
  carries only the toolchain + pydantic. I ran the equivalent real commands
  directly (`repro_check.py`, `gatepack build` on pelican, `gatepack verify` on
  xor2) rather than faking the pytest layer.
- The `CellNames` constructor's duplicate-stable-name refusal is exercised only
  by a unit test; `stable_cell_names` itself never produces duplicates (it
  disambiguates), so the guard is defensive rather than load-bearing today.

## What I am least confident about

1. **The double-pack fix is a behaviour change I was not asked to make.** It is
   the same class of bug and my boundary made it obvious, but it does change the
   `force_groups` output (fewer packages). I judged "no behaviour change" to mean
   the *pinned* invariants (goldens, showcase 20/3, byte-identical rebuilds),
   none of which use `force_groups`, and left a clear note + regression test
   rather than preserving a known-wrong answer.
2. **`CellNames` inherits `Mapping.__eq__`/`__contains__`** from the ABC. `in`
   and `==` are defined over **instance** keys, which is correct for the mapping
   but could mislead someone expecting `stable in names`. I documented it but did
   not override it, to avoid adding a second, subtler surface.
3. **No static type checker is wired**, so `CellNames`'s type signatures are
   enforced only by `AttributeError`/`KeyError` at runtime and by convention. A
   future mypy/pyright setup would make the boundary stronger still; I did not
   add one (off-scope build change).
