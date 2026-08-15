# AGENTS.md — gatepack conventions

Read before changing anything. Kept short on purpose.

## Commands

- Run tests with **`.venv/bin/pytest -q`** — never bare `python` or bare
  `pytest` (the venv has the pinned deps; nothing else is guaranteed).
- Run the CLI with **`.venv/bin/python -m gatepack.cli ...`** (or the installed
  `gatepack` console script after `pip install -e .`).
- Shell harness: **`scripts/tests/run.sh`** (aggregates `scripts/tests/test_*.sh`).
- Before an end-to-end run of the CLI, nothing needs rebuilding — the CLI runs
  from source. If you change a `.ys` resource under `gatepack/yosys/`, no rebuild
  is needed (loaded via `importlib.resources`); if you change `pyproject.toml`
  entry points, re-run `pip install -e .`.

## Layout

- `gatepack/` — pure-Python core, no GUI dependency. Front-end (C1) in
  `gatepack/frontend/`, Liberty (C2) in `gatepack/liberty/`, synthesis (C3) in
  `gatepack/synth/` + `gatepack/yosys/common_frontend.ys`, verdict (§6) in
  `gatepack/estimate.py`, CLI in `gatepack/cli.py`.
- `libraries/74aup.csv` + `74aup.refs.md` — the cell library (placeholder data).
- `tests/unit/`, `tests/golden/`, `tests/contract/` — see `docs/TESTING.md`.
- `scripts/tests/` — shell harness (post-build functional checks).
- `docs/` — design (`gatepack-design.md`, authoritative) and `TESTING.md`.

## Rules that matter

- **No network, no `latest` tags, no new runtime deps beyond `pydantic`** without
  a written justification in `docs/BUILD-NOTES.md`. The environment cannot `pip
  install`; the YAML parser is deliberately hand-rolled in
  `gatepack/frontend/yaml_subset.py`.
- **Do not fake a Yosys result.** Yosys is not installed here. Anything needing
  a real run is `pytest.skip(...)` with an explicit reason. Script *generation*
  and verdict logic must be unit-testable without Yosys.
- Type-annotate, keep functions small, match the existing style (pydantic models,
  dataclasses, `from __future__ import annotations`).
- Do not modify `gatepack-design.md`, `docs/reviews/`, `.gitignore`, or `LICENSE`.
- Do not commit; leave work in the working tree.

## Test style

Tests pin behaviour, not coverage numbers. The CLI contract (exit codes `0`
success / `1` error / `2` usage / `3` async-refused, stable `manifest.json`
keys, deterministic sorted output, no timestamps) is pinned in
`tests/contract/`. Moving existing tests is fine; breaking them is not.
