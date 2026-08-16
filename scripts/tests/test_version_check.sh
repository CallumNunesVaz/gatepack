#!/usr/bin/env bash
# test_version_check.sh — the pyproject.toml / app/package.json version must not
# drift (docs/M6-FINDINGS.md §5 recorded exactly this skew).  The check is only
# worth anything if a drift actually fails, so the committed pair is asserted to
# pass and a deliberately mismatched copy is asserted to fail.

SOURCE="${BASH_SOURCE[0]}"
DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"

# shellcheck source=harness.sh
. "$DIR/harness.sh"

PYTHON="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"
CHECK="$REPO_ROOT/scripts/version_check.py"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

check_code "committed versions agree" 0 "$PYTHON" "$CHECK"

# -- a real drift must fail ---------------------------------------------------
printf '%s\n' '[project]' 'name = "gatepack"' 'version = "0.1.0"' > "$WORK/pyproject.toml"
printf '%s\n' '{"name": "gatepack-app", "version": "0.2.0"}' > "$WORK/app-package.json"

check_code "mismatched versions fail" 1 \
  "$PYTHON" "$CHECK" --pyproject "$WORK/pyproject.toml" --package-json "$WORK/app-package.json"

printf '%s\n' '{"name": "gatepack-app", "version": "0.1.0"}' > "$WORK/app-package.json"

check_code "matching versions pass" 0 \
  "$PYTHON" "$CHECK" --pyproject "$WORK/pyproject.toml" --package-json "$WORK/app-package.json"

finish
