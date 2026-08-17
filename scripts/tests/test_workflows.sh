#!/usr/bin/env bash
# test_workflows.sh — the GitHub Actions workflow YAML must parse, and the lint
# must actually catch a break.  A workflow lint that could not fail is worth
# nothing (the same class of defect the signing verification exists to kill):
# both directions are asserted here — the committed workflows lint clean, and a
# deliberately broken workflow is rejected.

SOURCE="${BASH_SOURCE[0]}"
DIR="$(cd "$(dirname "$SOURCE")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"

# shellcheck source=harness.sh
. "$DIR/harness.sh"

PYTHON="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"
LINT="$REPO_ROOT/scripts/lint_workflows.py"

check_code "committed workflows lint clean" 0 "$PYTHON" "$LINT"

# -- a real break must be caught ----------------------------------------------
WORK="$REPO_ROOT/.gpout/workflow-lint"
mkdir -p "$WORK"
printf 'jobs:\n    build:\n   bad-indent: x\n' > "$WORK/broken.yml"
check_code "broken workflow YAML is rejected" 1 "$PYTHON" "$LINT" --workflows "$WORK"
rm -rf "$WORK"

finish
