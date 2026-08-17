# Handoff notes — toolchain tests must not vandalise the checkout

The defect: `tests/toolchain/` ran the pinned Yosys/ABC/sby container as
*root*, so every artifact it wrote back through the bind mount — `build/`,
`.gpout/`, and a swath of `gatepack/**/__pycache__/*.cpython-311.pyc` — came out
root-owned. The developer's next *local* `gatepack` run then died with
`[Errno 13] Permission denied`. The fix is the one flag `scripts/start` already
passes and `tests/toolchain/test_examples.py` had inlined: `-u "$(id -u):$(id -g)"`.

## Call sites changed

One helper, not seventeen edits. New module `tests/toolchain/docker_runner.py`
builds every `docker run` command in the layer; each test module now imports it
and states only *what* to run, never *how* the container is invoked.

The helper has three entry points:

- `run(*argv, host_dir, container_dir, workdir, timeout)` — the general shape:
  `docker run --rm -u <uid>:<gid> -v host:container [-w workdir] IMAGE *argv`.
  The `-u` flag is supplied centrally, so a call site cannot forget it.
- `run_repo(*argv, timeout)` — the checkout mounted at `/repo`, `-w /repo`
  (the common case: `python3 -m gatepack …`, `python3 -c …`, `rm -rf …`,
  `cat …`, `bash -c …`, `env PATH=/nonexistent …`).
- `run_work(host_dir, *argv)` — a scratch/`tmp_path` dir mounted at `/work`
  with no workdir override (the `cd /work && yosys|sby …` runs).

Seventeen `docker run` call sites, across nine modules, now route through it:

| module | call sites |
|---|---|
| `test_examples.py` | `_run` (the already-fixed one, now shared) |
| `test_estimate_build_consistency.py` | `_run`, `_build_package_count`, `_rm` |
| `test_build_paths.py` | `_build`, `test_missing_yosys…` inline, `test_outputs_are_observable…` inline |
| `test_mcell_coverage.py` | `_run_yosys`, `_run_cli`, `test_verify_on_macro…` cleanup |
| `test_mux2_reachable.py` | the inline yosys run |
| `test_simulate_divergence.py` | `_run` |
| `test_provenance_real_run.py` | `_run` |
| `test_real_toolchain.py` | `_run_yosys`, `_run_sby` |
| `test_verify_paths.py` | `_verify`, `_read` |

No assertion changed. Two things did legitimately shift, both expected by the
brief:

1. **`test_examples.py` no longer has the flag inline** — it uses `run_repo`
   like everything else, so the `-u` behaviour it already had is unchanged but
   there is now one shape.
2. **Cleanup (`rm -rf`) runs as the invoking user, not root.** Before, the
   `finally:` blocks in `test_estimate_build_consistency.py` and
   `test_mcell_coverage.py` relied on root to delete build dirs. Now the dirs
   are created by the same non-root user (the build also runs with `-u`), so
   the same user can remove them; a root cleanup would be inconsistent rather
   than necessary. No cleanup silently does nothing — the suite passes with
   these cleanups running as the host user.

## Shape of the helper and why

Two shapes existed in the wild and both are real, so the helper mirrors them
rather than forcing one: a `/repo` mount with `-w /repo` (the CLI and shell
commands), and a `/work` mount with no workdir (the `yosys`/`sby` runs that `cd`
into place themselves). Forcing `bash -c` onto the `python3 -m gatepack` calls,
or `-w` onto the yosys ones, would have obscured what each test is doing, so
the odd shapes are left as their own thin wrappers (`run_repo`/`run_work`) over
the one `run`.

`os.getuid`/`os.getgid` do not exist on Windows. Decision: **fall back, not
skip.** When the platform has no uid/gid the helper omits `-u` and runs as the
image default. Rationale: these tests already skip when docker is absent, so a
Windows host with Docker Desktop and the image can still exercise the real
toolchain — skipping there would hide the whole suite for no reason. And the
defect this flag prevents is a POSIX-ownership phenomenon: a Windows bind mount
has no uid/gid on the host side, so there is nothing to protect and no honesty
cost in omitting the flag. (On POSIX — including the run below — the flag is
always present.)

## before-and-after `find -user root`

`find . -user root -not -path './.git/*'`:

**Before** (one run of the *unfixed* suite in a clean checkout):

```
329 entries total, of which:
  .gpout/            (the whole tree: t_flat, t_nested/one/two/three,
                      t_noyosys, t_observability, t_sim_ok, t_sim_bad,
                      tv_flat, tv_nested/..., tv_relative, tv_props/...,
                      prov_traffic_light, prov_pelican, …)
  gatepack/**/__pycache__/*.cpython-311.pyc   (71 files)
```

That single run also broke the *already-fixed* `test_examples.py` (12 failures,
`Permission denied: '.gpout/examples-check'`) and the local bundler tests (9
errors, `PermissionError: '.gpout/core-bundle'`) — because the unfixed tests had
root-owned `.gpout`, and the non-root `-u` user could no longer create inside
it. So the partial fix was actively broken until every call site carried `-u`.

Cleaned with `docker run --rm -v "$PWD:/repo" -w /repo gatepack-toolchain:m6
sh -c 'rm -rf .gpout build && find gatepack -type d -name __pycache__ -exec rm
-rf {} +'`, then the fixed suite was run.

**After** (one run of the fixed suite):

```
<no output — zero root-owned files>
```

## Test counts

```
.venv/bin/python -m pytest tests/toolchain -q
59 passed, 1 skipped in 66.97s
```

The single skip is `test_packaging.py::test_unpacked_app_contains_bundled_core`
(gated behind `GATEPACK_PACKAGING=1`), unchanged.

Ordinary local command after the run, with **no** cleanup step in between:

```
.venv/bin/python -m gatepack.cli compile examples/pelican/design.yaml -o build --json
→ {"ok": true, … "verilogPath": "build/generated.v", …}   (rc 0)
```

and `rm -rf build .gpout` succeeded as the host user — the artifacts are no
longer root-owned.

## What I left alone

- **`scripts/bundle_toolchain.py`** — its three `docker run` calls were checked
  and are *not* the defect. `_run_in_image` has no mount at all (runs
  `readlink -f`); the two `rm -rf` runs mount `REPO/.gpout/toolchain-bundle`
  (scratch) and `app/resources/share`/`ivl` but only *delete* their contents,
  never create files, so they leave nothing root-owned. The files it writes into
  the repo arrive via `docker cp` (`_Container.copy_out`/`copy_out_as`), a
  different mechanism that is not a `docker run` and not the EACCES failure this
  package targets; those land in the committed `app/resources/` tree rather than
  the developer's scratch. Left as-is.
- **`tests/toolchain/test_core_bundle.py` / `test_toolchain_bundle.py` /
  `test_packaging.py`** — no `docker run`; they drive the bundled binary under a
  scrubbed env or `electron-builder`, out of scope.
- **The `docker image inspect` availability probes and `requires_toolchain`
  marks** in each module — unchanged; they gate skipping, not invocation.
- No assertion, expected value, or fixture was touched.
