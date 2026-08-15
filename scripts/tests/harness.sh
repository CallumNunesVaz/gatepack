#!/usr/bin/env bash
# harness.sh — sourced by scripts/tests/test_*.sh.
#
# A tiny assertion layer with no test framework: `ok`, `bad`, `check`,
# `check_eq`.  Each test script sources this, uses the helpers, then calls
# `finish` (which prints the tally and exits non-zero on any failure).
#
# Modeled on reqmesh's scripts/tests/harness.sh.

set -u

GATEPACK_HARNESS_PASS=0
GATEPACK_HARNESS_FAIL=0
GATEPACK_HARNESS_NAME="${0##*/}"

ok() {
  GATEPACK_HARNESS_PASS=$((GATEPACK_HARNESS_PASS + 1))
  printf '  ok   %s\n' "$*"
}

bad() {
  GATEPACK_HARNESS_FAIL=$((GATEPACK_HARNESS_FAIL + 1))
  printf '  FAIL %s\n' "$*" >&2
}

# check <description> <command> [args...]  — passes iff the command exits 0.
check() {
  local desc="$1"
  shift
  if "$@"; then
    ok "$desc"
  else
    bad "$desc"
  fi
}

# check_fails <description> <command> [args...] — passes iff the command exits
# with a specific non-zero code (third-from-last check is on $? via check_code).
check_fails() {
  local desc="$1"
  shift
  if "$@"; then
    bad "$desc (expected failure, got success)"
  else
    ok "$desc"
  fi
}

# check_code <description> <expected_code> <command> [args...]
check_code() {
  local desc="$1" expected="$2"
  shift 2
  "$@"
  local code=$?
  if [ "$code" -eq "$expected" ]; then
    ok "$desc (exit $code)"
  else
    bad "$desc (expected exit $expected, got $code)"
  fi
}

check_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    ok "$desc"
  else
    bad "$desc (expected '$expected', got '$actual')"
  fi
}

check_file() {
  local desc="$1" path="$2"
  if [ -f "$path" ]; then
    ok "$desc"
  else
    bad "$desc (missing $path)"
  fi
}

finish() {
  printf '%s: %d passed, %d failed\n' \
    "$GATEPACK_HARNESS_NAME" "$GATEPACK_HARNESS_PASS" "$GATEPACK_HARNESS_FAIL"
  [ "$GATEPACK_HARNESS_FAIL" -eq 0 ]
}
