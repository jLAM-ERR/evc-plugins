#!/usr/bin/env bash
# smoke tests for panel-members.sh
# run: bash panel-members_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/panel-members.sh"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }
assert_eq() {
  local label="$1" actual="$2" expected="$3"
  [ "$actual" = "$expected" ] || fail "$label: expected '$expected', got '$actual'"
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

# test 1: default standard.design
assert_eq "standard.design" "$(bash "$SCRIPT" members standard design)" "architect
qa"
pass "default standard.design = architect, qa"

# test 2: default deep.design
assert_eq "deep.design" "$(bash "$SCRIPT" members deep design)" "architect
security
qa
dba"
pass "default deep.design = architect, security, qa, dba"

# test 3: project override wins over default
mkdir -p .autodidact-workflow
echo "standard.design=architect,qa,perf" > .autodidact-workflow/panel-members.conf
assert_eq "override" "$(bash "$SCRIPT" members standard design)" "architect
qa
perf"
rm -f .autodidact-workflow/panel-members.conf
pass "project .autodidact-workflow/panel-members.conf overrides the default"

# test 4: --security-required injects security when absent
assert_eq "inject security" "$(bash "$SCRIPT" members standard design --security-required)" "architect
qa
security"
pass "--security-required injects security into standard.design"

# test 5: --security-required does not duplicate when already present
n=$(bash "$SCRIPT" members deep design --security-required | grep -c '^security$')
assert_eq "security once" "$n" "1"
pass "--security-required does not duplicate an existing security role"

# test 6: unknown tier.stage → exit 2
set +e; bash "$SCRIPT" members quick design >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 2 ] || fail "unknown tier.stage should exit 2, got $rc"
pass "unknown tier.stage (quick.design) exits 2"

# test 7: unknown subcommand → exit 2
set +e; bash "$SCRIPT" bogus >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 2 ] || fail "unknown subcommand should exit 2, got $rc"
pass "unknown subcommand exits 2"

# test 8: whitespace-padded conf roles are trimmed, no leading spaces, security appended
mkdir -p .autodidact-workflow
echo "standard.design=architect, qa" > .autodidact-workflow/panel-members.conf
assert_eq "trim + inject" "$(bash "$SCRIPT" members standard design --security-required)" "architect
qa
security"
rm -f .autodidact-workflow/panel-members.conf
pass "conf roles with whitespace are trimmed; --security-required appends security once"

# test 9: whitespace-padded security role in conf is not duplicated
mkdir -p .autodidact-workflow
echo "standard.design=architect, security" > .autodidact-workflow/panel-members.conf
assert_eq "no dup after trim" "$(bash "$SCRIPT" members standard design --security-required)" "architect
security"
rm -f .autodidact-workflow/panel-members.conf
pass "--security-required does not duplicate a whitespace-padded existing security role"

# test 10: empty role list after trimming → exit 2 under /bin/bash (3.2)
mkdir -p .autodidact-workflow
echo "standard.design=" > .autodidact-workflow/panel-members.conf
set +e; /bin/bash "$SCRIPT" members standard design >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -eq 2 ] || fail "empty member list should exit 2 under /bin/bash, got $rc"
rm -f .autodidact-workflow/panel-members.conf
pass "empty member list (standard.design=) exits 2 under /bin/bash (3.2)"

# test 11: tab-separated conf role is trimmed too (hand-edited conf case)
mkdir -p .autodidact-workflow
printf 'standard.design=architect,\tqa\n' > .autodidact-workflow/panel-members.conf
assert_eq "tab trim" "$(bash "$SCRIPT" members standard design)" "architect
qa"
rm -f .autodidact-workflow/panel-members.conf
pass "tab-separated conf role is trimmed"

# test 12: mid-list empty token (double comma) is skipped
mkdir -p .autodidact-workflow
echo "standard.design=architect,,qa" > .autodidact-workflow/panel-members.conf
assert_eq "empty token skipped" "$(bash "$SCRIPT" members standard design)" "architect
qa"
rm -f .autodidact-workflow/panel-members.conf
pass "mid-list empty token (double comma) is skipped"

echo "all tests passed"
