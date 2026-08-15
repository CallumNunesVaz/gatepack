#!/usr/bin/env bash
# run.sh — executes every scripts/tests/test_*.sh and aggregates.
#
# Usage: scripts/tests/run.sh   (run from anywhere; it resolves its own dir)

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

total=0
failed=0

for t in "$DIR"/test_*.sh; do
  total=$((total + 1))
  name="$(basename "$t")"
  echo "== $name =="
  if bash "$t"; then
    echo "PASS $name"
  else
    echo "FAIL $name"
    failed=$((failed + 1))
  fi
  echo
done

echo "==== summary: $((total - failed))/$total test scripts passed ===="
[ "$failed" -eq 0 ]
