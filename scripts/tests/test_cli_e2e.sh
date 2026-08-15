#!/usr/bin/env bash
# test_cli_e2e.sh — end-to-end check of the *built* CLI on a golden design.
#
# This is the "works after a full build" check.  It drives the installed
# `gatepack` console script (falling back to the venv module entry point) end
# to end on the §18 traffic-light golden.  Safe on a developer machine: no sudo,
# no package installs, no ports bound, no network.
#
# Sourced helpers: harness.sh.  Aggregated by run.sh.

SOURCE="${BASH_SOURCE[0]}"
DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"

# shellcheck source=harness.sh
. "$DIR/harness.sh"

# Locate the CLI: prefer the installed console script, then the venv's, then
# the module entry point (works when the package is run from the source tree).
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

cat > "$WORK/traffic_light.yaml" <<'EOF'
name: traffic_light
timing_model: synchronous
clock: {signal: clk, freq_hz: 1000, source: OSC}
reset: {signal: rst_n, active: low, async_assert: true, sync_deassert: true, source: SUPERVISOR}
encoding: one_hot
inputs:
  - {name: go, sync: true}
outputs:
  - {name: green}
  - {name: red}
states: [RED, GREEN]
initial: RED
transitions:
  - {from: RED,   to: GREEN, when: "go"}
  - {from: RED,   to: RED,   when: "!go"}
  - {from: GREEN, to: RED,   when: "!go"}
  - {from: GREEN, to: GREEN, when: "go"}
output_logic:
  green: "state == GREEN"
  red: "state == RED"
properties:
  - {name: one_light_only, kind: mutex, expr: "!(green & red)"}
constraints:
  vcc: 3.3
EOF

cat > "$WORK/async.yaml" <<'EOF'
name: async_handshake
timing_model: asynchronous
reset: {signal: rst_n, active: low}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "1"}
  - {from: B, to: A, when: "1"}
output_logic: {}
EOF

cat > "$WORK/overlap.yaml" <<'EOF'
name: overlap
timing_model: synchronous
clock: {signal: clk, freq_hz: 1, source: OSC}
reset: {signal: rst_n, active: low}
inputs:
  - {name: x, sync: false}
states: [A, B]
initial: A
transitions:
  - {from: A, to: B, when: "x"}
  - {from: A, to: B, when: "x"}
  - {from: B, to: A, when: "1"}
output_logic: {}
EOF

# -- version ---------------------------------------------------------------
check_code "gatepack --version exits 0" 0 "${CLI[@]}" --version

# -- compile (passing golden) ---------------------------------------------
check_code "compile traffic_light exits 0" 0 \
  "${CLI[@]}" compile "$WORK/traffic_light.yaml" -o "$WORK/build"
check_file "compile writes generated.v" "$WORK/build/generated.v"
check_file "compile writes properties.sv" "$WORK/build/properties.sv"
check "generated.v carries src provenance attributes" \
  grep -q '(\* src = "traffic_light.yaml:' "$WORK/build/generated.v"
check "generated.v uses one-hot state bits" \
  grep -q 'reg state_RED;' "$WORK/build/generated.v"

# -- estimate --------------------------------------------------------------
check_code "estimate exits 0" 0 \
  "${CLI[@]}" estimate "$WORK/traffic_light.yaml" \
    --library "$LIBRARY" --build "$WORK/ebuild"
check_file "estimate writes manifest.json" "$WORK/ebuild/manifest.json"
check "manifest.json is valid JSON" \
  "$PYTHON" -c "import json,sys; json.load(open(sys.argv[1]))" "$WORK/ebuild/manifest.json"
check "manifest.json reports a verdict" \
  "$PYTHON" -c "import json,sys; d=json.load(open(sys.argv[1])); assert 'verdict' in d" "$WORK/ebuild/manifest.json"

# -- must-fail cases -------------------------------------------------------
check_code "async design refused (exit 3)" 3 \
  "${CLI[@]}" compile "$WORK/async.yaml" -o "$WORK/async_build"
check_code "overlapping guards rejected (exit 1)" 1 \
  "${CLI[@]}" compile "$WORK/overlap.yaml" -o "$WORK/overlap_build"

finish
