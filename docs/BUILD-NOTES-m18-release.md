# BUILD NOTES — M18 release (licence audit over the bundle, CI, release docs)

Scope: `scripts/**`, `.github/**`, `README.md`, `docs/RELEASING.md`,
`docs/worked-example.md`, `CHANGELOG.md`, and new tests under `tests/`. No
`app/**`, `gatepack/**`, or design/audit docs were edited (they were read).

## Test counts

```
baseline (per brief):    .venv/bin/python -m pytest tests -q   557 passed, 5 skipped
after:                   .venv/bin/python -m pytest tests -q   564 passed, 5 skipped
shell harness:           bash scripts/tests/run.sh             5/5  (was 4/5)
bundle acceptance:       pytest tests/toolchain/test_core_bundle.py -q   5 passed
packaging:               GATEPACK_PACKAGING=1 pytest tests/toolchain/test_packaging.py -q  1 passed
toolchain (host):        pytest tests/toolchain --ignore=core_bundle --ignore=packaging -q  30 passed
```

## 1. The licence audit now sees the bundled core

`scripts/licence_audit.py` gained a third input, `--bundle` / `--require-bundle`
(default `app/resources/bin/gatepack`). It opens the PyInstaller onefile binary
and enumerates what it **actually contains**, then classifies each component
against the `POLICY` table. An unrecognised component is a hard failure — never
a defaulted pass — for the same reason the npm tree audit fails on an unknown
licence: a licence the table cannot name is a hole, not a pass.

### Why a self-contained parser

The archive is parsed with stdlib only (`struct` + `marshal`), not by importing
PyInstaller. The audit must not depend on a build-only tool being installed at
audit time, and the format is small and stable enough to pin directly. I read
it from PyInstaller 6.22.1's `PyInstaller/archive/readers.py` and
`PyInstaller/loader/pyimod01_archive.py`:

- CArchive cookie `b"MEI\014\013\012\013\016"`, cookie `!8sIIII64s`, TOC entry
  `!IIIIBc`;
- PYZ header `b"PYZ\0"` + 4-byte bytecode magic + `!i` TOC offset, then a
  `marshal`'d object which PyInstaller rebuilds as `dict(marshal.load(fp))` — it
  is a **list** of `(name, entry)` pairs on disk, not a dict (my first parse
  assumed a dict and was corrected).

The parser was verified against a real bundle by cross-checking its TOC against
PyInstaller's own `pkg_archive_contents`.

### What the bundle actually contains (measured, not assumed)

The declared manifest lists `pydantic` as the only Python dependency. The real
binary contains, in addition to `gatepack` itself, the CPython runtime/stdlib,
the PyInstaller bootloader + loader + runtime hooks, and these Python packages:

| component | found in bundle | licence (where read) |
|---|---|---|
| pydantic 2.13.4 | PYZ + `dist-info` | MIT (dist-info `License-Expression`) |
| pydantic_core 2.46.4 | PYZ + `.so` | MIT |
| annotated-types 0.8.0 | PYZ | MIT |
| typing_extensions 4.16.0 | PYZ | PSF-2.0 |
| typing_inspection 0.4.4 | PYZ | MIT |
| packaging 26.3 | PYZ | Apache-2.0 OR BSD-2-Clause |
| setuptools 84.0.0 | PYZ (+ `_distutils_hack`) | MIT |

`typing_inspection`, `packaging` and `setuptools` are **not** in the declared
dependency list — which is the exact lesson the npm tree taught once already:
the declared set is not the shipped set. The audit now proves that by
enumerating the binary, so a future incompatible dependency (or a new
transitive of pydantic) will be caught by name.

Plus the bundled shared libraries PyInstaller pulled from the build host, each
classified by name prefix against a reviewed table:

| library | licence (from the build host's distro copyright files) |
|---|---|
| libpython3.x | PSF (CPython) |
| libssl / libcrypto | Apache-2.0 (OpenSSL 3.x) |
| libz | Zlib |
| libbz2 | bzip2 |
| liblzma | public domain (0BSD) |
| libffi | MIT |
| libexpat | MIT |
| libreadline | GPL-3.0-or-later |
| libtinfo | MIT/X11 (ncurses) |
| libgcc_s | GPL-3.0-or-later WITH GCC Runtime Library Exception |

### The PyInstaller bootloader exception, recorded

The GPL-3.0 compatibility of the bootloader turns on one exception, and I read
it rather than inferring it. From `pyinstaller-6.22.1.dist-info/licenses/COPYING.txt`:

> PyInstaller is licensed under the terms of the GNU General Public License as
> published by the Free Software Foundation; either version 2 of the License, or
> (at your option) any later version.
>
> **Bootloader Exception** — In addition to the permissions in the GNU General
> Public License, the authors give you unlimited permission to link or embed
> compiled bootloader and related files into combinations with other programs,
> and to distribute those combinations without any restriction coming from the
> use of those files. (The General Public License restrictions do apply in other
> respects; for example, they cover modification of the files, and distribution
> when not linked into a combined executable.)

That is the SPDX `GPL-2.0-or-later WITH Bootloader-exception`, now a `POLICY`
entry with that rationale. The same `COPYING.txt` licences PyInstaller's
**run-time hooks** under Apache-2.0, so the bundle carries two PyInstaller
components (`pyinstaller-bootloader` and `pyinstaller-runtime-hooks`), both
compatible. New `POLICY` entries added by name, after review: `psf-2.0`,
`gpl-2.0-or-later with bootloader-exception`,
`gpl-3.0-or-later with gcc-runtime-library-exception`, `zlib`, `bzip2`, `0bsd`.

### Make it fail (the tests)

`tests/unit/test_licence_audit_bundle.py` builds a minimal but structurally
faithful PyInstaller onefile archive (bootloader prefix + CArchive + PYZ) with
no PyInstaller dependency, and pins the failure modes:

- a known component set is accepted;
- an unrecognised Python package (`evilpkg`) rejects;
- an unrecognised shared library (`libevil.so.1`) rejects;
- a component with a known-*incompatible* licence (injected as `gpl-2.0-only`)
  rejects and names the licence;
- a non-PyInstaller file rejects.

`tests/toolchain/test_core_bundle.py` gained `test_bundle_passes_licence_audit`,
which builds the real bundle and asserts the audit names `pydantic`, `cpython`
and the bootloader exception — the parser is proven against real output, not
just the synthetic archive.

### The stale shell harness

`scripts/tests/test_licence_audit.sh` was **already broken before this work**
(4/5): it pinned the committed-tree audit to exit 1 with a shipped
`spdx-exceptions` finding and an EPL-1.0 elkjs. Both findings were remediated
before I started (`spdx-exceptions` packed out by `electron-builder.yml`'s
`files` excludes; netlistsvg pinned onto the EPL-2.0 elkjs 0.9.3 by the npm
override), so the audit exits 0 and the harness now pins that: exit 0, the
EPL-2.0 elkjs still *conditional*, `spdx-exceptions` still reported as
not-shipped, plus the new bundle CLI guards.

A second, subtler defect surfaced while fixing the first: the committed-tree
check is the only harness case that needs the real `app/node_modules`, and the
`test` CI job runs no `npm ci`. In that job the old check passed its
exit-code assertion by *coincidence* (a missing tree and the old spdx finding
both exit 1) while its `grep` assertions failed. The committed-tree section is
now gated on `app/node_modules` existing, so the `test` job skips it cleanly and
`desktop-packaging` (which has the tree) still exercises it.

## 2. CI — findings first, then the fix

**Finding 1: the `toolchain` job could not pass.** It ran
`docker run gatepack-toolchain:m6 bash -c 'python3 -m pytest tests/toolchain'`
*inside* the container, but the image carries no pytest (→ `No module named
pytest`) and no docker. The toolchain tests are written to run on the **host**:
they `docker run` the image themselves, guarded by `requires_toolchain`
(host `docker` + `docker image inspect`). So even with pytest in the image the
tests would have skipped and the job's own "a skip is a failure" grep would have
failed. The fix: run pytest on the host (`pip install -e . pytest`), excluding
`test_core_bundle.py` (PyInstaller) and `test_packaging.py`
(`GATEPACK_PACKAGING=1`), which are not toolchain tests.

**Finding 2: `test_core_bundle.py`, `test_packaging.py`, and every vitest file
were never run by any job.** `test_core_bundle.py` skips without PyInstaller;
`test_packaging.py` skips without `GATEPACK_PACKAGING=1`; vitest and the two
`tsc` typechecks had no CI step at all. `test_doctor.py` (unit) and
`test_doctor_contract.py` (contract) *were* already run by the `test` job — the
brief listed them, but they are genuinely covered (they live in `tests/unit`
and `tests/contract`).

The fix, wired into `desktop-packaging` (which already has node + npm ci):
build the core, licence-audit tree **and** bundle, run `test_core_bundle.py`,
run `tsc` + `vitest`, and run `test_packaging.py` with `GATEPACK_PACKAGING=1`.
The `test` job now runs only `tests/unit tests/golden tests/contract` so it
stops collecting the toolchain/bundle/packaging tests it would only ever skip.

## 3. Docs

- `README.md` Status rewritten against `docs/MILESTONE-AUDIT.md` (which was not
  edited): provenance is reported (M11b), the GUI milestones were audited and
  close (M12–M17), packaging exists, and the honest open corners are unsigned
  installers and the unbundled native toolchain.
- `docs/RELEASING.md`: the "spdx-exceptions ships" claim and the
  "desktop-packaging does not yet run bundle_core.py" claim were both stale and
  are corrected; the bundle build and the `--require-bundle` audit are now steps
  3 and 4 of "Cutting v0.1.0", in that order (the bundle must exist before it
  can be audited).
- `CHANGELOG.md` written from the git history, in user terms, with a "Known
  limitations" section that restates the unsigned/placeholder/unverified items.
- `docs/worked-example.md` — every command in it was run (in the toolchain
  container via `./start cli`, which is the simplest correct instruction) and
  its output pasted verbatim.

## What I could not verify

- **The CI workflow itself.** I cannot run GitHub Actions here; I validated the
  YAML syntactically and ran each wired command locally (they all pass), but the
  job graph has not executed.
- **The ubuntu-latest shared-library set.** The bundle I audited was built on
  this machine (Python 3.12). CI builds with Python 3.11, so the set of bundled
  `lib*.so` files there is *almost certainly* the same shapes but is not the
  exact bytes I enumerated. The table classifies by name prefix (`libssl`,
  `libz.`, `libpython`, …) precisely so it survives that difference, but a novel
  system library would fail the audit until a maintainer reviews it — which is
  the intended behaviour, not a bug.
- **Whether `setuptools` is genuinely needed at runtime or is collected dead
  weight.** It ships (the enumeration proves it), and it is MIT, so it passes;
  I did not investigate whether PyInstaller's module analysis could be tightened
  to drop it. That is a size optimisation, not a licence defect.

## Weakest parts / suspicions

1. **Stdlib detection uses the host's `sys.stdlib_module_names`.** If a bundle
   built with a different Python minor version than the auditing interpreter is
   audited, a newly-added stdlib module could be mis-read as an unrecognised
   third-party package (false positive — fails safe, but annoying). A
   version-match check reading the cookie's `python_version` field would tighten
   this; I did not add it.
2. **The shared-library licences are recorded from the build host's Debian
   copyright files**, not from reading inside each `.so` (which carries no
   licence). They are stable, well-known facts, but the "read what you record"
   standard is weaker here than for the Python packages and the bootloader.
3. **`sitecustomize`** in the PYZ is Ubuntu's `apport_python_hook` (a distro
   sitecustomize), classified as `cpython`. It is technically apport (GPL-3+),
   which is compatible, but bundling an OS hook into a supposedly
   self-contained binary is worth a look by the core-owner — it is a build-host
   leak, not a gatepack dependency.
