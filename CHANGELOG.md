# Changelog

All notable changes to gatepack are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); gatepack is
versioned with [SemVer](https://semver.org/) (core and app together, one tree).

## [0.1.0] — 2026-08-16

The first release. gatepack compiles a truth table or finite state machine into
a bill of materials and a schematic netlist built from discrete 74AUP logic,
and formally verifies the result on every build. This is the initial,
honest cut: everything below ships, and the "known limitations" at the bottom
are stated rather than papered over.

### Added

**Core — from specification to a buildable netlist**

- `design.yaml` specifications: FSMs with states, transitions, guards,
  synchronous/async inputs, output logic, reset contracts, and properties
  (invariants, mutexes, reachability, liveness). A hand-rolled YAML subset
  parser keeps the core dependency-free beyond pydantic.
- `gatepack estimate` — a viability verdict before you invest in a build:
  gate count, board fit, and a CPLD warning when a design is too big for
  discrete gates.
- `gatepack compile` — specification to behavioural Verilog plus a formal
  properties file, with per-construct provenance (`gp_src`) attributes.
- `gatepack build` — synthesis, technology mapping to real 74AUP parts, packing
  into multi-gate packages (spare-gate avoidance), and a BOM (CSV with reference
  designators and tiers), a KiCad netlist, and a build report.
- `gatepack verify` — formal equivalence (Yosys), exhaustive simulation
  (Icarus), mutation testing, and property discharge (SymbiYosys), with a
  vacuity guard so a property that holds only because its antecedent never
  occurs is rejected. The central claim — the netlist is proven equivalent to
  the specification — is measured, not asserted.
- `gatepack simulate` — an exhaustive spec-vs-netlist divergence table (the
  basis for the GUI's divergence highlighting).
- `gatepack analyse` — SCOAP testability and stuck-at fault classification.
- `gatepack provenance` / `mapped-netlist` / `packed-netlist` — measured
  provenance coverage (per-construct, with the unlinked constructs named) and
  netlist inspection.
- `gatepack lib check` / `lib gen` — a cell-library citation audit (no
  electrical value without a datasheet reference) and Liberty generation.
- `gatepack project bundle` / `explode` — a single-file `.gpk` project format
  that round-trips byte-for-byte.
- `gatepack examples list` / `extract` — bundled example projects, including
  the pelican crossing showcase.
- `gatepack doctor` — reports each external tool as found (with version) or
  missing, with its purpose, rather than failing with a stack trace.
- Deterministic, byte-reproducible builds: two clean builds of the same
  specification are hash-identical including the mapped netlist and BOM.

**Desktop application (Electron)**

- A desktop app that is strictly a view over CLI-produced artefacts: it opens a
  project, edits the specification (three-way sync with the layout), shows the
  truth table with divergence highlighting, renders the schematic (all layers),
  cross-highlights packages/properties, persists packing overrides, and shows a
  dashboard of metrics. It never reimplements core logic.

**Release engineering**

- `./start` — one entry point for the app, the CLI and the toolchain.
- A bundled, self-contained Python core (PyInstaller onefile) that runs with no
  host Python — the packaged app does not fall through to a host venv.
- A licence audit that sees the *real* shipped surface: the installed npm tree
  and the contents of the PyInstaller binary, not just the declared dependency
  list.
- A reproducible toolchain container (`Dockerfile` / `Dockerfile.probe`) with
  Yosys 0.23, ABC, Icarus, SymbiYosys and z3.
- A tag-triggered release workflow (`.github/workflows/release.yml`) that builds
  the core bundle and the installer in a per-OS/arch matrix (PyInstaller does
  not cross-compile), runs the bundle acceptance test on each, and publishes
  `SHA256SUMS` checksums, a per-platform CycloneDX SBOM, and release notes.
  Signing is wired but unpopulated: builds are signed when credentials are
  supplied and unsigned otherwise, and the unsigned state is stated, not hidden.

### Known limitations

- **Installers are unsigned.** No signing identities have been provisioned, and
  none are fabricated: macOS and Windows installers will trip Gatekeeper /
  SmartScreen until a maintainer supplies credentials. The build machinery is
  wired (`docs/RELEASING.md`) and an unsigned build announces itself in the
  release notes and `SHA256SUMS.txt` rather than hiding it.
- **The native toolchain is not bundled.** The Python core ships; yosys, sby,
  iverilog and z3 are still host tools (or the provided container), and
  `gatepack doctor` reports them honestly when they are missing.
- **"KiCad import clean" is unverified** — deferred out of scope. The netlist is
  emitted; no one has yet imported it into KiCad.
- **16 of 22 library cells carry placeholder electrical data.** `gatepack lib
  check` enforces the citations; until they are filled in, the BOM is a shape,
  not a purchasable part list.
- **Multi-gate `gates_per_pkg` values are unverified.** A wrong value yields a
  netlist that physically cannot be built (a part whose true gate count differs
  from what the packer assumed), which is a worse failure than a wrong tPD; it
  is called out separately in `libraries/74aup.refs.md`.
