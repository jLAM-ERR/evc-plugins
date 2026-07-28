#!/usr/bin/env bash
# smoke tests for profile-select.sh
# run: bash profile-select_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/profile-select.sh"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }
assert_eq() {
  local label="$1" actual="$2" expected="$3"
  [ "$actual" = "$expected" ] || fail "$label: expected '$expected', got '$actual'"
}
# field <key> reads stdin (the script output) and prints the value
field() { grep "^$1=" | cut -d= -f2-; }

# test 1: small → quick (skips design + harden)
out=$(bash "$SCRIPT" --points 2)
assert_eq "small tier"   "$(echo "$out" | field tier)"   "quick"
assert_eq "small stages" "$(echo "$out" | field stages)" "implement,pr"
echo "$out" | field stages | grep -q design && fail "quick must not include design"
echo "$out" | field stages | grep -q harden && fail "quick must not include harden"
pass "small → quick, skips design+harden"

# test 2: medium → standard, single review
out=$(bash "$SCRIPT" --points 5)
assert_eq "medium tier"   "$(echo "$out" | field tier)"   "standard"
assert_eq "medium stages" "$(echo "$out" | field stages)" "design,implement,harden,pr"
assert_eq "medium review" "$(echo "$out" | field review)" "single"
pass "medium → standard, single review"

# test 3: large → deep, nvote=3
out=$(bash "$SCRIPT" --points 13)
assert_eq "large tier"   "$(echo "$out" | field tier)"   "deep"
assert_eq "large review" "$(echo "$out" | field review)" "nvote=3"
pass "large → deep, nvote=3 review"

# test 4: risk label bumps tier + forces security_required
out=$(bash "$SCRIPT" --points 5 --risk pii)
assert_eq "risk bumped tier"  "$(echo "$out" | field tier)"              "deep"
assert_eq "risk security flag" "$(echo "$out" | field security_required)" "true"
pass "risk label bumps standard→deep + sets security_required"

# test 5: --profile override wins over signals
out=$(bash "$SCRIPT" --points 1 --profile deep)
assert_eq "override tier" "$(echo "$out" | field tier)" "deep"
pass "--profile override wins"

# test 6: no signals → standard + defaulted
out=$(bash "$SCRIPT")
assert_eq "default tier"      "$(echo "$out" | field tier)"      "standard"
assert_eq "default defaulted" "$(echo "$out" | field defaulted)" "true"
pass "no signals → standard + defaulted=true"

# test 7: stages never contain intake (it's a fixed pre-stage)
for t in 1 5 13; do
  bash "$SCRIPT" --points "$t" | field stages | grep -q intake \
    && fail "stages must never include intake (points=$t)"
done
pass "stages never include intake for any tier"

# test 8: invalid --profile value → exit 2
set +e; bash "$SCRIPT" --profile bogus >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 2 ] || fail "invalid --profile should exit 2, got $rc"
pass "invalid --profile value exits 2"

# test 9: a LOC-style flag is rejected (the tool must never accept LOC)
set +e; bash "$SCRIPT" --loc 500 >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 2 ] || fail "LOC flag must be rejected (exit 2), got $rc"
pass "LOC flag is rejected — size is never lines-of-code"

# test 10: non-integer --points → exit 2, no tier= output
out=$(set +e; bash "$SCRIPT" --points abc 2>/dev/null; echo "rc=$?")
rc=$(echo "$out" | grep -o 'rc=[0-9]*' | cut -d= -f2)
[ "$rc" -eq 2 ] || fail "non-integer --points should exit 2, got $rc"
echo "$out" | grep -q '^tier=' && fail "non-integer --points must not print tier="
pass "non-integer --points exits 2 with no tier= output"

# test 11: non-integer --acs → exit 2, no tier= output
out=$(set +e; bash "$SCRIPT" --acs xyz 2>/dev/null; echo "rc=$?")
rc=$(echo "$out" | grep -o 'rc=[0-9]*' | cut -d= -f2)
[ "$rc" -eq 2 ] || fail "non-integer --acs should exit 2, got $rc"
echo "$out" | grep -q '^tier=' && fail "non-integer --acs must not print tier="
pass "non-integer --acs exits 2 with no tier= output"

# test 12: non-integer --components → exit 2, no tier= output
out=$(set +e; bash "$SCRIPT" --components "" 2>/dev/null; echo "rc=$?")
rc=$(echo "$out" | grep -o 'rc=[0-9]*' | cut -d= -f2)
[ "$rc" -eq 2 ] || fail "non-integer --components should exit 2, got $rc"
echo "$out" | grep -q '^tier=' && fail "non-integer --components must not print tier="
pass "non-integer --components exits 2 with no tier= output"

# test 13: --points must reject a leading-minus value (not a non-negative integer)
set +e; bash "$SCRIPT" --points -1 >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 2 ] || fail "negative --points should exit 2, got $rc"
pass "negative --points exits 2"

# test 14: error message names the offending flag and value
err=$(bash "$SCRIPT" --acs 3x 2>&1 >/dev/null || true)
echo "$err" | grep -q -- "--acs must be a non-negative integer, got: 3x" \
  || fail "error message should name flag and value, got: $err"
pass "error message names flag and offending value"

# test 15: uppercase --risk value still matches (case-insensitive)
out=$(bash "$SCRIPT" --points 5 --risk PII)
assert_eq "uppercase risk tier"  "$(echo "$out" | field tier)"              "deep"
assert_eq "uppercase risk flag" "$(echo "$out" | field security_required)" "true"
pass "uppercase --risk PII bumps tier + sets security_required"

# test 16: uppercase --type value still matches (case-insensitive)
out=$(bash "$SCRIPT" --type Spike --points 1)
assert_eq "uppercase type tier" "$(echo "$out" | field tier)" "standard"
pass "uppercase --type Spike --points 1 promotes small → standard"

# test 17: uppercase --profile value still matches (case-insensitive)
out=$(bash "$SCRIPT" --profile DEEP)
assert_eq "uppercase profile tier" "$(echo "$out" | field tier)" "deep"
pass "uppercase --profile DEEP forces tier=deep"

echo "all tests passed"
