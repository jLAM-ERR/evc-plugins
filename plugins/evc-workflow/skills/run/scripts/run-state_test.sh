#!/usr/bin/env bash
# smoke tests for run-state.sh
# run: bash run-state_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/run-state.sh"

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; exit 1; }
assert_eq() {
  local label="$1" actual="$2" expected="$3"
  [ "$actual" = "$expected" ] || fail "$label: expected '$expected', got '$actual'"
}

KEY="TASK-1"
RUNFILE=".evc-workflow/runs/$KEY.yaml"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

# test 1: init creates run-file + artifacts dir, status running
bash "$SCRIPT" init "$KEY" >/dev/null
[ -f "$RUNFILE" ]               || fail "init did not create run-file"
[ -d ".evc-workflow/runs/$KEY/" ] || fail "init did not create artifacts dir"
assert_eq "init status"        "$(bash "$SCRIPT" get "$KEY" status)"        "running"
assert_eq "init artifacts_dir" "$(bash "$SCRIPT" get "$KEY" artifacts_dir)" ".evc-workflow/runs/$KEY/"
pass "init creates run-file + artifacts dir with status running"

# test 2: init idempotent (never clobbers)
bash "$SCRIPT" set "$KEY" status waiting-at-gate
bash "$SCRIPT" init "$KEY" >/dev/null
assert_eq "init idempotent" "$(bash "$SCRIPT" get "$KEY" status)" "waiting-at-gate"
pass "init is idempotent (no clobber)"

# test 3: scalar set/get round-trip
bash "$SCRIPT" set "$KEY" stage design
bash "$SCRIPT" set "$KEY" profile standard
assert_eq "get stage"   "$(bash "$SCRIPT" get "$KEY" stage)"   "design"
assert_eq "get profile" "$(bash "$SCRIPT" get "$KEY" profile)" "standard"
pass "scalar set/get round-trips"

# test 4: append-history adds one entry
bash "$SCRIPT" append-history "$KEY" intake approve alice "profile ok"
assert_eq "history count" "$(grep -c '^  - {' "$RUNFILE")" "1"
pass "append-history adds one entry"

# test 5: append-answer appends to spec.answers
bash "$SCRIPT" append-answer "$KEY" "use redis"
grep -q '    - "use redis"' "$RUNFILE" || fail "append-answer entry missing"
pass "append-answer appends to spec.answers"

# test 6: decline-count counts trailing declines and resets after approve
bash "$SCRIPT" append-history "$KEY" design decline bob "rework"
bash "$SCRIPT" append-history "$KEY" design decline bob "again"
assert_eq "decline-count 2" "$(bash "$SCRIPT" decline-count "$KEY" design)" "2"
bash "$SCRIPT" append-history "$KEY" design approve bob "ok"
assert_eq "decline-count reset" "$(bash "$SCRIPT" decline-count "$KEY" design)" "0"
pass "decline-count counts trailing declines + resets after approve"

# test 7: threshold
assert_eq "threshold" "$(bash "$SCRIPT" threshold)" "2"
pass "threshold prints 2"

# test 8: commit lands in a temp git repo with the expected message
git init -q
git config user.email t@t.com
git config user.name T
bash "$SCRIPT" commit "$KEY" intake approve >/dev/null
git log --oneline -1 | grep -q "chore(evc-workflow): intake approve \[$KEY\]" \
  || fail "commit message wrong: $(git log --oneline -1)"
pass "commit lands with the expected message"

# test 9: unknown subcommand exits 2
set +e
bash "$SCRIPT" bogus "$KEY" 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "unknown subcommand should exit 2, got $rc"
pass "unknown subcommand exits 2"

# test 10: init rejects a path-traversal KEY, creates nothing outside .evc-workflow/runs
set +e
bash "$SCRIPT" init '../../ESCAPED' 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ]        || fail "traversal KEY should exit 2, got $rc"
[ ! -e "ESCAPED" ]      || fail "traversal KEY created a dir outside .evc-workflow/runs"
[ ! -e "ESCAPED.yaml" ] || fail "traversal KEY created a file outside .evc-workflow/runs"
pass "init rejects a path-traversal KEY and creates nothing outside .evc-workflow/runs"

# test 11: init rejects a non-canonical KEY (no dash + digits)
set +e
bash "$SCRIPT" init 'K1' 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "non-canonical KEY should exit 2, got $rc"
pass "init rejects a non-canonical KEY"

# test 12: canonical KEYs still work
bash "$SCRIPT" init 'TASK-123' >/dev/null
[ -f ".evc-workflow/runs/TASK-123.yaml" ] || fail "init did not create run-file for TASK-123"
bash "$SCRIPT" init 'K-1' >/dev/null
[ -f ".evc-workflow/runs/K-1.yaml" ] || fail "init did not create run-file for K-1"
pass "init still accepts canonical KEYs (TASK-123, K-1)"

# test 13: append-history note with a double quote is escaped and round-trips
bash "$SCRIPT" append-history "$KEY" design approve carol 'say "hi"'
grep -q 'note: "say \\"hi\\""' "$RUNFILE" || fail "escaped quote note missing"
pass "append-history escapes a double quote in the note"

# test 14: append-history note with an embedded newline is rejected
set +e
bash "$SCRIPT" append-history "$KEY" design approve carol "$(printf 'line1\nline2')" 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "note with newline should exit 2, got $rc"
pass "append-history rejects a note with an embedded newline"

# test 15: append-answer text with an embedded newline is rejected
set +e
bash "$SCRIPT" append-answer "$KEY" "$(printf 'line1\nline2')" 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "answer with newline should exit 2, got $rc"
pass "append-answer rejects a text with an embedded newline"

# test 16: append-answer preserves FIFO insertion order (not LIFO), stays inside spec.answers
KEY_FIFO="K-2"
bash "$SCRIPT" init "$KEY_FIFO" >/dev/null
bash "$SCRIPT" append-answer "$KEY_FIFO" "first answer"
bash "$SCRIPT" append-answer "$KEY_FIFO" "second answer"
FIRST_LINE=$(grep -n '"first answer"' ".evc-workflow/runs/$KEY_FIFO.yaml" | cut -d: -f1)
SECOND_LINE=$(grep -n '"second answer"' ".evc-workflow/runs/$KEY_FIFO.yaml" | cut -d: -f1)
HISTORY_LINE=$(grep -n '^history:' ".evc-workflow/runs/$KEY_FIFO.yaml" | cut -d: -f1)
[ -n "$FIRST_LINE" ] && [ -n "$SECOND_LINE" ] && [ -n "$HISTORY_LINE" ] || fail "FIFO answers or history: line missing"
[ "$FIRST_LINE" -lt "$SECOND_LINE" ] || fail "answers not in FIFO order (first should precede second)"
[ "$SECOND_LINE" -lt "$HISTORY_LINE" ] || fail "answers must stay inside spec.answers, before history:"
pass "append-answer keeps insertion order (FIFO) and stays before history:"

# test 17: set on a nonexistent field exits 2 and leaves the file unchanged
KEY_SET="K-3"
bash "$SCRIPT" init "$KEY_SET" >/dev/null
RUNFILE_SET=".evc-workflow/runs/$KEY_SET.yaml"
BEFORE=$(cat "$RUNFILE_SET")
set +e
bash "$SCRIPT" set "$KEY_SET" bogusfield x 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "set on unknown field should exit 2, got $rc"
AFTER=$(cat "$RUNFILE_SET")
[ "$BEFORE" = "$AFTER" ] || fail "set on unknown field modified the file"
pass "set on a nonexistent field exits 2 and leaves the file unchanged"

# test 18: base_sha and signals fields round-trip via set/get
bash "$SCRIPT" set "$KEY_SET" base_sha abc123
assert_eq "get base_sha" "$(bash "$SCRIPT" get "$KEY_SET" base_sha)" "abc123"
bash "$SCRIPT" set "$KEY_SET" signals "--points 5 --risk payments"
assert_eq "get signals" "$(bash "$SCRIPT" get "$KEY_SET" signals)" "--points 5 --risk payments"
pass "base_sha and signals round-trip via set/get"

# test 19: append-history note with a literal backslash escapes to \\ and round-trips
bash "$SCRIPT" append-history "$KEY" design approve carol 'back\slash'
grep -qF 'note: "back\\slash"' "$RUNFILE" || fail "escaped backslash note missing"
pass "append-history escapes a literal backslash in the note"

# test 20: commit excludes an unrelated pre-staged file; audit commit contains
# only the run-file/artifacts, and the unrelated file stays staged
KEY_SCOPE="K-4"
bash "$SCRIPT" init "$KEY_SCOPE" >/dev/null
echo "unrelated" > unrelated_scope.txt
git add unrelated_scope.txt
bash "$SCRIPT" commit "$KEY_SCOPE" intake approve >/dev/null
COMMIT_FILES=$(git show --name-only --pretty=format: HEAD)
echo "$COMMIT_FILES" | grep -q "unrelated_scope.txt" && fail "commit swept in the unrelated pre-staged file"
echo "$COMMIT_FILES" | grep -q ".evc-workflow/runs/$KEY_SCOPE.yaml" || fail "commit did not include the run-file"
git status --porcelain -- unrelated_scope.txt | grep -q '^A  unrelated_scope.txt' || fail "unrelated file no longer staged after commit"
pass "commit is scoped: unrelated pre-staged file stays out and stays staged"

# test 21: a second identical commit is a no-op: exit 0 with the notice
set +e
OUT=$(bash "$SCRIPT" commit "$KEY_SCOPE" intake approve)
RC=$?
set -e
[ "$RC" -eq 0 ] || fail "repeat commit should exit 0, got $RC"
echo "$OUT" | grep -q "run-state: nothing to commit" || fail "repeat commit missing the nothing-to-commit notice"
pass "repeat commit is idempotent: exit 0 with notice"

# test 22: commit succeeds when the artifacts dir is empty/untracked (only the run-file gets committed)
KEY_EMPTY="K-5"
bash "$SCRIPT" init "$KEY_EMPTY" >/dev/null
[ -z "$(ls -A ".evc-workflow/runs/$KEY_EMPTY/" 2>/dev/null)" ] || fail "artifacts dir for $KEY_EMPTY should start empty"
bash "$SCRIPT" commit "$KEY_EMPTY" intake approve >/dev/null
EMPTY_COMMIT_FILES=$(git show --name-only --pretty=format: HEAD)
echo "$EMPTY_COMMIT_FILES" | grep -q ".evc-workflow/runs/$KEY_EMPTY.yaml" || fail "commit did not include the run-file for $KEY_EMPTY"
echo "$EMPTY_COMMIT_FILES" | grep -q ".evc-workflow/runs/$KEY_EMPTY/" && fail "commit should not reference the empty artifacts dir"
pass "commit succeeds with an empty/untracked artifacts dir; only the run-file is committed"

# test 23: a run-file staged then reverted back to HEAD in the worktree has nothing
# for `git commit -- <pathspec>` to actually record (worktree-vs-HEAD, not index-vs-HEAD);
# commit must exit 0 with the notice and leave the staged state untouched
KEY_REVERT="K-6"
bash "$SCRIPT" init "$KEY_REVERT" >/dev/null
RUNFILE_REVERT=".evc-workflow/runs/$KEY_REVERT.yaml"
bash "$SCRIPT" commit "$KEY_REVERT" intake approve >/dev/null
echo "extra: staged-then-reverted" >> "$RUNFILE_REVERT"
git add "$RUNFILE_REVERT"
git show HEAD:"$RUNFILE_REVERT" > "$RUNFILE_REVERT"   # revert worktree to HEAD; index keeps the staged edit
echo "unrelated2" > unrelated_revert.txt
git add unrelated_revert.txt
set +e
OUT=$(bash "$SCRIPT" commit "$KEY_REVERT" intake approve)
RC=$?
set -e
[ "$RC" -eq 0 ] || fail "staged-then-reverted commit should exit 0, got $RC"
echo "$OUT" | grep -q "run-state: nothing to commit" || fail "staged-then-reverted commit missing the nothing-to-commit notice"
git status --porcelain -- "$RUNFILE_REVERT" | grep -q '^M' || fail "staged run-file edit should remain staged after the no-op commit"
git status --porcelain -- unrelated_revert.txt | grep -q '^A  unrelated_revert.txt' || fail "unrelated staged file should remain staged"
pass "commit treats a staged-but-worktree-reverted run-file as nothing to commit"

# test 24: cleanup reuses the KEY validation guard (path-traversal KEY rejected
# with the guard's own message, not just an unknown-subcommand exit)
set +e
OUT=$(bash "$SCRIPT" cleanup '../../ESCAPED' 2>&1)
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "cleanup traversal KEY should exit 2, got $rc"
echo "$OUT" | grep -q "invalid KEY" || fail "cleanup should reuse _validate_key's message, got: $OUT"
pass "cleanup rejects a path-traversal KEY via the shared validation guard"

# test 25: cleanup refuses unless status is done, and leaves the run-file in place
KEY_CLEAN="TASK-20"
bash "$SCRIPT" init "$KEY_CLEAN" >/dev/null
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_CLEAN" 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "cleanup on a non-done run should fail, got exit 0"
echo "$OUT" | grep -qi "done" || fail "cleanup refusal message should mention 'done': $OUT"
[ -f ".evc-workflow/runs/$KEY_CLEAN.yaml" ] || fail "cleanup refusal must leave the run-file in place"
pass "cleanup refuses unless status is done"

# test 26: --force overrides the non-done refusal
bash "$SCRIPT" cleanup "$KEY_CLEAN" --force >/dev/null
[ ! -e ".evc-workflow/runs/$KEY_CLEAN.yaml" ] || fail "--force cleanup should remove the run-file"
[ ! -e ".evc-workflow/runs/$KEY_CLEAN/" ]     || fail "--force cleanup should remove the artifacts dir"
pass "cleanup --force overrides the non-done refusal"

# test 27: cleanup is idempotent — a second run exits 0 with an already-clean notice
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_CLEAN")
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "repeat cleanup should exit 0, got $rc"
echo "$OUT" | grep -qi "already clean" || fail "repeat cleanup missing the already-clean notice: $OUT"
pass "cleanup is idempotent: exit 0 with an already-clean notice on the second run"

# test 28: cleanup of the SHORTER prefix KEY must not sweep a LONGER sibling
# whose name starts with it — guards the <KEY>* glob footgun the other way
# round (TASK-1* also matches TASK-12; a buggy `rm -rf .../$key*`
# cleaning TASK-1 would take TASK-12 down with it)
KEY_SIB="TASK-12"
bash "$SCRIPT" init "$KEY_SIB" >/dev/null
echo "sibling artifact" > ".evc-workflow/runs/$KEY_SIB/note.md"
bash "$SCRIPT" cleanup "$KEY" --force >/dev/null
[ ! -e "$RUNFILE" ]                         || fail "cleanup did not remove $KEY's run-file"
[ ! -e ".evc-workflow/runs/$KEY/" ]          || fail "cleanup did not remove $KEY's artifacts dir"
[ -f ".evc-workflow/runs/$KEY_SIB.yaml" ]    || fail "cleanup of $KEY swept the longer sibling's run-file (glob footgun)"
[ -d ".evc-workflow/runs/$KEY_SIB/" ]        || fail "cleanup of $KEY swept the longer sibling's artifacts dir (glob footgun)"
[ -f ".evc-workflow/runs/$KEY_SIB/note.md" ] || fail "cleanup of $KEY swept the longer sibling's artifact file (glob footgun)"
pass "cleanup of a shorter prefix KEY leaves a longer (glob-suffix-matching) sibling untouched"

# test 29: the cleanup commit contains exactly the run-file + artifact paths, nothing else
KEY_COMMIT="TASK-30"
bash "$SCRIPT" init "$KEY_COMMIT" >/dev/null
echo "stub" > ".evc-workflow/runs/$KEY_COMMIT/design.md"
bash "$SCRIPT" commit "$KEY_COMMIT" design approve >/dev/null
bash "$SCRIPT" set "$KEY_COMMIT" status "done"
bash "$SCRIPT" commit "$KEY_COMMIT" pr "done" >/dev/null
bash "$SCRIPT" cleanup "$KEY_COMMIT" >/dev/null
CLEANUP_FILES=$(git show --name-only --pretty=format: HEAD | sort)
EXPECTED=$(printf '.evc-workflow/runs/%s.yaml\n.evc-workflow/runs/%s/design.md' "$KEY_COMMIT" "$KEY_COMMIT" | sort)
[ "$CLEANUP_FILES" = "$EXPECTED" ] || fail "cleanup commit should contain exactly the run-file + artifact, got: $CLEANUP_FILES"
pass "cleanup commit contains exactly the run-file + artifact paths"

# test 30: cleanup interrupted between `git rm` and `git commit` (filesystem
# already clear, deletions still staged) must finish the commit on a retry,
# not report "already clean" and leave the deletions uncommitted
KEY_INTERRUPT="TASK-50"
bash "$SCRIPT" init "$KEY_INTERRUPT" >/dev/null
echo "stub" > ".evc-workflow/runs/$KEY_INTERRUPT/design.md"
bash "$SCRIPT" commit "$KEY_INTERRUPT" design approve >/dev/null
bash "$SCRIPT" set "$KEY_INTERRUPT" status "done"
bash "$SCRIPT" commit "$KEY_INTERRUPT" pr "done" >/dev/null
FILE_INTERRUPT=".evc-workflow/runs/$KEY_INTERRUPT.yaml"
ART_INTERRUPT=".evc-workflow/runs/$KEY_INTERRUPT/"
git rm -r -q -f --ignore-unmatch -- "$FILE_INTERRUPT" "$ART_INTERRUPT" >/dev/null
[ ! -e "$FILE_INTERRUPT" ] || fail "manual git rm should have cleared the run-file from the worktree"
git status --porcelain -- "$FILE_INTERRUPT" "$ART_INTERRUPT" | grep -q '^D' || fail "manual git rm should leave staged deletions behind"
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_INTERRUPT")
rc=$?
set -e
[ "$rc" -eq 0 ] || fail "interrupted-cleanup retry should exit 0, got $rc"
echo "$OUT" | grep -qi "already clean" && fail "interrupted-cleanup retry must not report already-clean — a commit was still pending: $OUT"
git log --oneline -1 | grep -q "cleanup \[$KEY_INTERRUPT\]" || fail "interrupted-cleanup retry should have committed the staged deletions"
pass "cleanup finishes a commit interrupted between git rm and git commit instead of reporting already-clean"

# test 31: a staged/unstaged run-file deletion for a NON-done run must NOT be
# committed without --force — only the legitimate "committed status: done,
# then interrupted" recovery (test 30) is allowed through unforced. A run-file
# git-rm'd some other way while still `status: running` must not get swept.
KEY_ACTIVE="TASK-70"
bash "$SCRIPT" init "$KEY_ACTIVE" >/dev/null
bash "$SCRIPT" commit "$KEY_ACTIVE" intake approve >/dev/null
FILE_ACTIVE=".evc-workflow/runs/$KEY_ACTIVE.yaml"
ART_ACTIVE=".evc-workflow/runs/$KEY_ACTIVE/"
git rm -r -q -f --ignore-unmatch -- "$FILE_ACTIVE" "$ART_ACTIVE" >/dev/null
rm -rf -- "$ART_ACTIVE"   # empty/untracked dir: git rm leaves it, mirror cleanup's own untracked-leftover removal
[ ! -e "$FILE_ACTIVE" ] || fail "manual git rm should have cleared the active run's run-file from the worktree"
[ ! -e "$ART_ACTIVE" ]  || fail "the artifacts dir should be gone from the worktree too"
git status --porcelain -- "$FILE_ACTIVE" "$ART_ACTIVE" | grep -q '^D' || fail "manual git rm should leave a staged deletion behind"
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_ACTIVE" 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "cleanup of a staged deletion for a non-done run should refuse without --force, got exit 0"
echo "$OUT" | grep -qi "not 'done'" || fail "refusal message should name the last committed (non-done) status: $OUT"
git status --porcelain -- "$FILE_ACTIVE" "$ART_ACTIVE" | grep -q '^D' || fail "refusal must leave the staged deletion pending, not committed"
bash "$SCRIPT" cleanup "$KEY_ACTIVE" --force >/dev/null
[ -z "$(git status --porcelain -- "$FILE_ACTIVE" "$ART_ACTIVE" 2>/dev/null)" ] || fail "--force should have committed the staged deletion"
pass "cleanup refuses to finish a staged run-file deletion for a non-done run without --force"

# test 32: worktree status=done but not yet committed to HEAD (HEAD still says
# running) must refuse — proceeding would authorize a git rm that an
# interrupted retry's HEAD-based recovery check (test 30/31) would then
# refuse to finish, stranding the run without --force
KEY_UNCOMMITTED="TASK-80"
bash "$SCRIPT" init "$KEY_UNCOMMITTED" >/dev/null
bash "$SCRIPT" commit "$KEY_UNCOMMITTED" intake approve >/dev/null
bash "$SCRIPT" set "$KEY_UNCOMMITTED" status "done"
FILE_UNCOMMITTED=".evc-workflow/runs/$KEY_UNCOMMITTED.yaml"
ART_UNCOMMITTED=".evc-workflow/runs/$KEY_UNCOMMITTED/"
BEFORE_HEAD=$(git rev-parse HEAD)
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_UNCOMMITTED" 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "cleanup should refuse an uncommitted worktree-done status, got exit 0"
echo "$OUT" | grep -qi "not yet committed" || fail "refusal message should say status is not yet committed: $OUT"
[ -f "$FILE_UNCOMMITTED" ]             || fail "refusal must leave the run-file in place"
[ -d "$ART_UNCOMMITTED" ]              || fail "refusal must leave the artifacts dir in place"
[ "$(git rev-parse HEAD)" = "$BEFORE_HEAD" ] || fail "refusal must not create any commit"
bash "$SCRIPT" commit "$KEY_UNCOMMITTED" pr "done" >/dev/null
bash "$SCRIPT" cleanup "$KEY_UNCOMMITTED" >/dev/null
[ ! -e "$FILE_UNCOMMITTED" ] || fail "cleanup should succeed once status:done is actually committed"
pass "cleanup refuses an uncommitted worktree-done status, then succeeds once committed"

# test 33: a committed run-file with no `status:` line at all (hand-edited /
# corrupted) must refuse with a "cannot verify" message instead of a silent
# `set -o pipefail` abort — exercises the interrupted-deletion recovery path
# (HEAD copy exists but the status: field is missing)
KEY_NOSTATUS="TASK-90"
bash "$SCRIPT" init "$KEY_NOSTATUS" >/dev/null
FILE_NOSTATUS=".evc-workflow/runs/$KEY_NOSTATUS.yaml"
ART_NOSTATUS=".evc-workflow/runs/$KEY_NOSTATUS/"
grep -v '^status:' "$FILE_NOSTATUS" > "$FILE_NOSTATUS.tmp" && mv "$FILE_NOSTATUS.tmp" "$FILE_NOSTATUS"
grep -q '^status:' "$FILE_NOSTATUS" && fail "test setup: status: line should have been removed"
bash "$SCRIPT" commit "$KEY_NOSTATUS" intake approve >/dev/null
git rm -r -q -f --ignore-unmatch -- "$FILE_NOSTATUS" "$ART_NOSTATUS" >/dev/null
rm -rf -- "$ART_NOSTATUS"
[ ! -e "$FILE_NOSTATUS" ] || fail "manual git rm should have cleared the run-file from the worktree"
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_NOSTATUS" 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "cleanup with an unverifiable (missing status:) committed copy should refuse, got exit 0"
echo "$OUT" | grep -qi "cannot verify" || fail "refusal message should say status cannot be verified: $OUT"
pass "cleanup refuses a staged deletion whose committed copy has no status: line, instead of aborting silently"

# test 34: the run-file itself was never committed (no HEAD copy) but the
# artifacts dir HAS tracked content — same entry-authorizes/recovery-refuses
# hazard as test 32, one corner deeper: an interrupted retry would stage the
# tracked-artifact deletions with no committed run-file to verify against
KEY_TRACKED_ART="TASK-100"
bash "$SCRIPT" init "$KEY_TRACKED_ART" >/dev/null
FILE_TRACKED_ART=".evc-workflow/runs/$KEY_TRACKED_ART.yaml"
ART_TRACKED_ART=".evc-workflow/runs/$KEY_TRACKED_ART/"
echo "stub" > "${ART_TRACKED_ART}note.md"
git add "${ART_TRACKED_ART}note.md"
git commit -q -m "manual: track artifact only, bypassing cmd_commit"
git ls-files -- "$ART_TRACKED_ART" | grep -q "note.md" || fail "test setup: artifact should be tracked"
[ -z "$(git ls-files -- "$FILE_TRACKED_ART")" ] || fail "test setup: run-file should stay untracked"
bash "$SCRIPT" set "$KEY_TRACKED_ART" status "done"
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_TRACKED_ART" 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "cleanup should refuse when artifacts are tracked but the run-file was never committed, got exit 0"
echo "$OUT" | grep -qi "artifacts are tracked" || fail "refusal message should say artifacts are tracked but the run-file was never committed: $OUT"
[ -f "$FILE_TRACKED_ART" ]            || fail "refusal must leave the run-file in place"
[ -f "${ART_TRACKED_ART}note.md" ]    || fail "refusal must leave the tracked artifact in place"
git status --porcelain -- "$FILE_TRACKED_ART" "$ART_TRACKED_ART" | grep -q '^D' && fail "refusal must not stage any deletion"
bash "$SCRIPT" commit "$KEY_TRACKED_ART" pr "done" >/dev/null
bash "$SCRIPT" cleanup "$KEY_TRACKED_ART" >/dev/null
[ ! -e "$FILE_TRACKED_ART" ] || fail "cleanup should succeed once the run-file is actually committed"
pass "cleanup refuses when artifacts are tracked but the run-file was never committed, then succeeds once committed"

# test 35: an orphaned artifacts dir (run-file already gone) refuses without
# --force — the done-guard's contract is status:done, not "no run-file to check"
KEY_ORPHAN="TASK-60"
bash "$SCRIPT" init "$KEY_ORPHAN" >/dev/null
echo "leftover" > ".evc-workflow/runs/$KEY_ORPHAN/leftover.md"
rm -f ".evc-workflow/runs/$KEY_ORPHAN.yaml"
set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_ORPHAN" 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "cleanup of an orphaned artifacts dir should refuse without --force, got exit 0"
echo "$OUT" | grep -qi "run-file missing" || fail "orphan refusal message should explain the run-file is missing: $OUT"
[ -d ".evc-workflow/runs/$KEY_ORPHAN/" ]             || fail "orphan refusal must leave the artifacts dir in place"
[ -f ".evc-workflow/runs/$KEY_ORPHAN/leftover.md" ]  || fail "orphan refusal must leave the artifact file in place"
bash "$SCRIPT" cleanup "$KEY_ORPHAN" --force >/dev/null
[ ! -e ".evc-workflow/runs/$KEY_ORPHAN/" ] || fail "--force should remove the orphaned artifacts dir"
pass "cleanup refuses an orphaned artifacts dir without --force, and --force removes it"

# test 36: cleanup --push retry must actually reach the remote after a failed
# push, even when the local removal/commit phase now finds nothing to do —
# a plain push on an up-to-date branch is a harmless no-op, but on a
# failed-push retry it's what completes the recovery. Runs in its own fresh
# repo (not the shared $WORK one above, which has intentional leftover
# staged files from earlier tests that would block a reconciling merge).
BASE_DIR="$WORK"
ISOLATED=$(mktemp -d)
cd "$ISOLATED"
git init -q
git config user.email t@t.com
git config user.name T
echo seed > seed.txt
git add seed.txt
git commit -q -m seed
BRANCH=$(git symbolic-ref --short HEAD)

REMOTE_DIR=$(mktemp -d)
git init -q --bare "$REMOTE_DIR"
git remote add origin "$REMOTE_DIR"
git push -q -u origin "$BRANCH"

CLONE_DIR=$(mktemp -d)
git clone -q "$REMOTE_DIR" "$CLONE_DIR"
(
  cd "$CLONE_DIR"
  git config user.email t2@t.com
  git config user.name T2
  echo "diverge" > diverge.txt
  git add diverge.txt
  git commit -q -m diverge
  git push -q origin "$BRANCH"
)

KEY_RETRY="TASK-40"
bash "$SCRIPT" init "$KEY_RETRY" >/dev/null
bash "$SCRIPT" set "$KEY_RETRY" status "done"
bash "$SCRIPT" commit "$KEY_RETRY" pr "done" >/dev/null

set +e
OUT=$(bash "$SCRIPT" cleanup "$KEY_RETRY" --push 2>&1)
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "first cleanup --push should fail against a diverged remote, got exit 0"
echo "$OUT" | grep -q "push failed" || fail "first cleanup --push missing the push-failed message: $OUT"
[ ! -e ".evc-workflow/runs/$KEY_RETRY.yaml" ] || fail "the cleanup commit should still have removed the run-file locally"

git fetch -q origin
git rebase -q "origin/$BRANCH"

set +e
OUT2=$(bash "$SCRIPT" cleanup "$KEY_RETRY" --push 2>&1)
rc2=$?
set -e
[ "$rc2" -eq 0 ] || fail "retry cleanup --push should succeed after reconciling, got $rc2: $OUT2"
LOCAL_TIP=$(git rev-parse HEAD)
REMOTE_TIP=$(git ls-remote "$REMOTE_DIR" "refs/heads/$BRANCH" | cut -f1)
[ "$LOCAL_TIP" = "$REMOTE_TIP" ] || fail "remote branch tip should equal the local tip after the retry push"

cd "$BASE_DIR"
rm -rf "$ISOLATED" "$REMOTE_DIR" "$CLONE_DIR"
pass "cleanup --push retry reaches the remote even when the removal phase is already-clean"

echo "all tests passed"
