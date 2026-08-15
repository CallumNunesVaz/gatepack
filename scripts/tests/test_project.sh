#!/usr/bin/env bash
# test_project.sh — end-to-end check of the §10.4 single-file project format.
#
# Drives the built CLI through bundle/explode and asserts the round-trip is
# byte-deterministic, which is the property the format exists to protect.
# Safe on a developer machine: no sudo, no package installs, no network.

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

cat > "$WORK/design.yaml" <<'EOF'
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
constraints:
  vcc: 3.3
EOF

# -- bundle ----------------------------------------------------------------
check_code "project bundle exits 0" 0 \
  "${CLI[@]}" project bundle "$WORK" -o "$WORK/x.gpk"
check_file "bundle writes x.gpk" "$WORK/x.gpk"
check "x.gpk is plain multi-document YAML (not an archive)" \
  grep -q '^%YAML 1.2$' "$WORK/x.gpk"
check "x.gpk carries gatepack version + kind" \
  grep -q '^kind: design$' "$WORK/x.gpk"
check "x.gpk quotes expressions (round-trip safe)" \
  grep -q 'when: "!go"' "$WORK/x.gpk"

# -- compile from the .gpk (C1 accepts either form, §10.4) ----------------
check_code "compile accepts .gpk" 0 \
  "${CLI[@]}" compile "$WORK/x.gpk" -o "$WORK/build"
check_file "compile writes generated.v from .gpk" "$WORK/build/generated.v"

# -- explode + re-bundle must be byte-identical ----------------------------
check_code "project explode exits 0" 0 \
  "${CLI[@]}" project explode "$WORK/x.gpk" -o "$WORK/out"
check_file "explode writes design.yaml" "$WORK/out/design.yaml"
check_code "re-bundle exits 0" 0 \
  "${CLI[@]}" project bundle "$WORK/out" -o "$WORK/x2.gpk"
check "round-trip is byte-deterministic" \
  cmp -s "$WORK/x.gpk" "$WORK/x2.gpk"

# -- lib check on a .gpk with an embedded library --------------------------
cp "$LIBRARY" "$WORK/parts.csv"
check_code "bundle with embedded library exits 0" 0 \
  "${CLI[@]}" project bundle "$WORK" -o "$WORK/lib.gpk"
check_code "lib check on .gpk with matching library exits 0" 0 \
  "${CLI[@]}" lib check "$WORK/lib.gpk"
# diverge the on-disk library: the embedded sha256 no longer matches
"$PYTHON" -c "import sys; p='$WORK/parts.csv'; s=open(p).read(); open(p,'w').write(s.replace('1G04','1G99'))"
check_code "lib check reports library divergence (exit 1)" 1 \
  "${CLI[@]}" lib check "$WORK/lib.gpk"

finish
