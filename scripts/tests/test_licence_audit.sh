#!/usr/bin/env bash
# test_licence_audit.sh — functional check of the extended §4 licence audit
# (scripts/licence_audit.py), specifically the installed-tree walk the declared
# manifest alone cannot see.
#
# The cases that matter are the ones a previous run got wrong: a shipped
# incompatible licence must fail, a *dev-only* incompatible licence must not
# (conflating the two drowns the signal in build tooling), an unrecognised
# licence must fail even when it does not ship, a *nested* production dependency
# must be classified as shipped (a hoisted version hides the real subtree), and
# the EPL elkjs case must survive as *conditional* rather than silently become
# permissive.

SOURCE="${BASH_SOURCE[0]}"
DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"

# shellcheck source=harness.sh
. "$DIR/harness.sh"

PYTHON="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"
AUDIT="$REPO_ROOT/scripts/licence_audit.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkpkg() { # mkpkg <dir> <name> <license>
  local dir="$1" name="$2" lic="$3"
  mkdir -p "$dir"
  cat > "$dir/package.json" <<EOF
{"name": "$name", "version": "1.0.0", "license": "$lic"}
EOF
}

# run_audit <outfile> <args...> — runs the audit, captures stdout+stderr, echoes exit code
run_audit() {
  local out="$1"
  shift
  "$PYTHON" "$AUDIT" "$@" > "$out" 2>&1
  echo $?
}

# -- the committed installed tree is audited and its one known finding is pinned
#    (spdx-exceptions ships via netlistsvg's yargs CLI tree; see BUILD-NOTES-m18)
rc=$(run_audit "$WORK/committed.txt" --require-node-tree)
check_eq "committed tree audit runs (exit 1: one shipped finding)" "1" "$rc"
check "committed tree finding names spdx-exceptions" grep -q "spdx-exceptions" "$WORK/committed.txt"
check "shipped elkjs EPL-1.0 survives as conditional" grep -q "EPL-1.0" "$WORK/committed.txt"

# -- a shipped GPL-2.0-only package fails --------------------------------------
T="$WORK/gpl20"; mkdir -p "$T/node_modules"
printf '%s\n' '{"dependencies": {"lib": "1.0.0"}}' > "$T/package.json"
mkpkg "$T/node_modules/lib" lib "GPL-2.0"
rc=$(run_audit "$WORK/gpl20.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json")
check_eq "shipped GPL-2.0-only fails" "1" "$rc"
check "shipped GPL-2.0 failure names the licence" grep -q "GPL-2.0-only" "$WORK/gpl20.txt"

# -- a shipped unrecognised licence fails --------------------------------------
T="$WORK/unrec"; mkdir -p "$T/node_modules"
printf '%s\n' '{"dependencies": {"lib": "1.0.0"}}' > "$T/package.json"
mkpkg "$T/node_modules/lib" lib "NoSuchLicence-9"
rc=$(run_audit "$WORK/unrec.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json")
check_eq "shipped unrecognised licence fails" "1" "$rc"
check "shipped unrecognised failure explains itself" grep -q "no policy entry" "$WORK/unrec.txt"

# -- a dev-only incompatible licence is non-blocking ---------------------------
T="$WORK/devinc"; mkdir -p "$T/node_modules"
printf '%s\n' '{"devDependencies": {"buildtool": "1.0.0"}}' > "$T/package.json"
mkpkg "$T/node_modules/buildtool" buildtool "GPL-2.0"
rc=$(run_audit "$WORK/devinc.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json")
check_eq "dev-only incompatible licence is non-blocking" "0" "$rc"
check "dev-only incompatible licence is reported as not shipped" grep -q "not shipped" "$WORK/devinc.txt"

# -- a dev-only unrecognised licence still fails (fail closed on unknowns) -----
T="$WORK/devunrec"; mkdir -p "$T/node_modules"
printf '%s\n' '{"devDependencies": {"buildtool": "1.0.0"}}' > "$T/package.json"
mkpkg "$T/node_modules/buildtool" buildtool "NoSuchLicence-9"
rc=$(run_audit "$WORK/devunrec.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json")
check_eq "dev-only unrecognised licence fails" "1" "$rc"

# -- a nested production dependency is shipped (lock file is authoritative) ----
T="$WORK/nested"; mkdir -p "$T/node_modules/netlistsvg/node_modules/camelcase"
printf '%s\n' '{"dependencies": {"netlistsvg": "1.0.0"}}' > "$T/package.json"
cat > "$T/node_modules/netlistsvg/package.json" <<'EOF'
{"name": "netlistsvg", "version": "1.0.0", "license": "MIT", "dependencies": {"camelcase": "^1.0.0"}}
EOF
mkpkg "$T/node_modules/netlistsvg/node_modules/camelcase" camelcase "GPL-2.0"
cat > "$T/package-lock.json" <<'EOF'
{"lockfileVersion": 3, "packages": {
  "": {"name": "app", "dependencies": {"netlistsvg": "1.0.0"}},
  "node_modules/netlistsvg": {"version": "1.0.0", "license": "MIT"},
  "node_modules/netlistsvg/node_modules/camelcase": {"version": "1.0.0", "license": "GPL-2.0"}
}}
EOF
rc=$(run_audit "$WORK/nested.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json" --lockfile "$T/package-lock.json")
check_eq "nested production dependency with incompatible licence fails" "1" "$rc"
check "nested production dependency is reported as shipped" grep -q "\[ships\] camelcase" "$WORK/nested.txt"

# -- EPL-2.0 shipped unmodified is accepted (conditional, not permissive) ------
T="$WORK/epl"; mkdir -p "$T/node_modules"
printf '%s\n' '{"dependencies": {"elkjs": "1.0.0"}}' > "$T/package.json"
mkpkg "$T/node_modules/elkjs" elkjs "EPL-2.0"
rc=$(run_audit "$WORK/epl.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json")
check_eq "shipped EPL-2.0 (unmodified) accepted" "0" "$rc"
check "EPL-2.0 is classified conditional, not permissive" grep -q "conditional" "$WORK/epl.txt"

# -- an SPDX OR expression is accepted when an alternative is compatible -------
T="$WORK/spdx"; mkdir -p "$T/node_modules"
printf '%s\n' '{"dependencies": {"lib": "1.0.0"}}' > "$T/package.json"
mkpkg "$T/node_modules/lib" lib "(MIT OR CC0-1.0)"
rc=$(run_audit "$WORK/spdx.txt" --node-tree "$T/node_modules" --app-manifest "$T/package.json")
check_eq "SPDX OR expression accepted" "0" "$rc"

# -- --require-node-tree fails when the tree is absent -------------------------
rc=$(run_audit "$WORK/req.txt" --node-tree "$WORK/does-not-exist" --require-node-tree)
check_eq "--require-node-tree fails on a missing tree" "1" "$rc"

finish
