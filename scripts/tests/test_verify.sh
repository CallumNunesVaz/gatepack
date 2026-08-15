#!/usr/bin/env bash
# test_verify.sh — functional check of `gatepack verify` (C4, M5) and the C2
# cells_sim.v deliverable ([R4-17]).
#
# No Yosys/Icarus is installed here, so the tool-dependent checks must report
# "not run" and the command must exit non-zero (a verification that could not
# run is never a pass, §14).  The pure-Python §9.5 checks still pass, and the
# C2 cells_sim.v artefact (G/F models + M-cell models) is written.
#
# Sourced helpers: harness.sh.  Aggregated by run.sh.

SOURCE="${BASH_SOURCE[0]}"
DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"

# shellcheck source=harness.sh
. "$DIR/harness.sh"

if command -v gatepack >/dev/null 2>&1; then
  CLI=(gatepack)
elif [ -x "$REPO_ROOT/.venv/bin/gatepack" ]; then
  CLI=("$REPO_ROOT/.venv/bin/gatepack")
else
  CLI=("$REPO_ROOT/.venv/bin/python" -m gatepack.cli)
fi

PYTHON="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

LIBRARY="$REPO_ROOT/libraries/74aup.csv"

cat > "$WORK/d.yaml" <<'EOF'
name: t
timing_model: synchronous
clock: {signal: clk, freq_hz: 1, source: OSC}
reset: {signal: rst_n, active: low, source: SUPERVISOR}
inputs:
  - {name: x, sync: true}
outputs:
  - {name: y}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "x"}
  - {from: A, to: A, when: "!x"}
  - {from: B, to: A, when: "1"}
output_logic:
  y: "state == B"
EOF

# -- verify (no toolchain -> not run, exit non-zero) -------------------------
check_code "verify exits non-zero without tools" 1 \
  "${CLI[@]}" verify "$WORK/d.yaml" --library "$LIBRARY" --build "$WORK/vbuild"

check_file "verify writes manifest.json" "$WORK/vbuild/manifest.json"
check "manifest.json is valid JSON" \
  "$PYTHON" -c "import json,sys; json.load(open(sys.argv[1]))" "$WORK/vbuild/manifest.json"
check "manifest reports 'not run' overall (tools absent)" \
  "$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1])); assert d['verification']['overall']=='not run'" "$WORK/vbuild/manifest.json"
check "no check claims 'passed' for a tool that is absent" \
  "$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1])); names=['equivalence','exhaustive simulation','mutation']; assert all(any(c['name']==n and c['status']=='not run' for c in d['verification']['checks']) for n in names)" "$WORK/vbuild/manifest.json"

# -- C2 cells_sim.v ([R4-17]) -------------------------------------------------
check_file "C2 writes cells_sim.v" "$WORK/vbuild/cells_sim.v"
check "cells_sim.v models the G-cells" \
  grep -q "module NAND2 (" "$WORK/vbuild/cells_sim.v"
check "cells_sim.v models the F-cells" \
  grep -q "module DFF_R (" "$WORK/vbuild/cells_sim.v"
check "cells_sim.v includes the M-cell models (same files as C4, R25)" \
  grep -q "module CNT4 (" "$WORK/vbuild/cells_sim.v"

# -- the §9.5 checks run without any tool -------------------------------------
check "flop reset connectivity check passes on a reset-connected design" \
  "$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1])); c=[x for x in d['verification']['checks'] if x['name']=='flop reset connectivity'][0]; assert c['status']=='passed'" "$WORK/vbuild/manifest.json"

finish
