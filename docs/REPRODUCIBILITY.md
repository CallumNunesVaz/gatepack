# REPRODUCIBILITY.md — what is and is not byte-reproducible

Reproducibility is a design principle (§3.5, §5.5): *same commit + same
container yields a byte-identical netlist.*  This file records the honest state
of that guarantee today, before the M0 pinned container exists.

## Reproducible today (verified without Yosys)

`scripts/repro_check.py` builds the traffic-light golden twice in two different
working directories and compares artefact hashes.  The following are
byte-identical by construction and by test:

| Artefact | Produced by | Why it is deterministic |
|---|---|---|
| `generated.v` | C1 front-end | pure function of `design.yaml`; `src` attributes use the file *basename*, never an absolute path |
| `properties.sv` | C1 front-end | pure function of `design.yaml` |
| `cells.lib` | C2 Liberty generator | pure function of `parts.csv`; stable cell order |
| `yosys.ys` | C3 backend | pure function of the SynthConfig, *given a fixed build path* |
| `manifest.json` | §6 verdict | `json.dumps(..., sort_keys=True)`, no timestamps (§C6) |

Determinism is mechanical, not incidental: sorted JSON keys, sorted output, no
dict-order dependence, no timestamps anywhere in a payload (§C6).  The contract
test `test_estimate_writes_deterministic_manifest` pins the manifest shape.

## Location-dependence caveat

`yosys.ys` embeds the build directory path (e.g. `build/generated.v`).  It is
deterministic for a *fixed* build path but differs across build locations.  The
reproducibility check therefore builds twice with the **same relative build
path** in different working directories — this holds the path constant and
proves the rest of the content is deterministic.  In the pinned container the
build always runs from a fixed `WORKDIR`, so even this caveat disappears.

## Not reproducible today (needs the M0 container)

| Artefact | Why not yet |
|---|---|
| `mapped.json`, `mapped.v` | produced by `dfflibmap`/`abc`; requires Yosys + ABC, which are not installed in this environment |
| `premap.json` | produced by the shared front end under Yosys |

The mapped netlist is the *actual* reproducibility target (R7: ABC result may
vary across versions).  It depends on the pinned Yosys/ABC versions in the
`Dockerfile`, whose version tags are still placeholders to be fixed at M0
(`yosys-0.40`, `sby v0.44`, `espresso v2.4` — see the Dockerfile comments).
Until that container is built and the tags are confirmed, the mapped netlist has
**never** been produced, let alone reproduced, and no result is faked here.

## What CI enforces

`.github/workflows/ci.yml` runs `scripts/repro_check.py` on every push.  It
guards the front-end/C2/C3-script/manifest determinism above.  When M0 lands,
the same check will be extended (or a new one added) to compare `mapped.json` /
`mapped.v` hashes across two runs in the pinned container — that is the §5.5
"build twice, compare output hashes" guarantee in full, and it is not claimable
before then.
