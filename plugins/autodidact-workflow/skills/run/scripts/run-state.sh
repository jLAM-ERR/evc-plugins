#!/usr/bin/env bash
# run-state.sh — manage an autodidact-workflow run-file at .autodidact-workflow/runs/<KEY>.yaml
# KEY is always the first arg after the subcommand.
#   init <KEY> [ticket]                                  create run-file + artifacts dir (idempotent)
#   path <KEY>                                           print the run-file path
#   get <KEY> <field>                                    print a top-level scalar (status|stage|profile|ticket|artifacts_dir)
#   set <KEY> <field> <value>                            set a top-level scalar
#   append-history <KEY> <stage> <decision> <by> <note>  append one audit entry (stamped UTC)
#   append-answer <KEY> <text>                           append a clarification to spec.answers
#   decline-count <KEY> <stage>                          trailing consecutive declines for <stage>
#   commit <KEY> <stage> <decision>                      git add run-file + artifacts, commit
#   cleanup <KEY> [--push] [--force]                     remove run-file + artifacts at their exact paths, commit (never a <KEY>* glob)
#   threshold                                            print the decline-escalation threshold
set -euo pipefail

RUNS_DIR=".autodidact-workflow/runs"
THRESHOLD=2

_file() { echo "$RUNS_DIR/$1.yaml"; }
_artifacts_dir() { echo "$RUNS_DIR/$1/"; }

# bash-3.2-safe canonical run-key check (single grammar, no relaxed mode)
_validate_key() {
  local key="${1:-}"
  if [[ ! "$key" =~ ^[A-Za-z][A-Za-z0-9]*-[0-9]+$ ]]; then
    echo "run-state: invalid KEY: '$key' (expected a canonical run key, e.g. TASK-123)" >&2
    exit 2
  fi
}

# escape \ and " for safe embedding in a double-quoted YAML scalar; reject embedded newlines/CR
_sanitize_value() {
  local v="$1"
  case "$v" in
    *$'\n'*|*$'\r'*)
      echo "run-state: value must not contain newlines: '$v'" >&2
      exit 2
      ;;
  esac
  v="${v//\\/\\\\}"
  v="${v//\"/\\\"}"
  printf '%s' "$v"
}

cmd_init() {
  _validate_key "${1:-}"
  local key="$1" ticket="${2:-$1}" file art
  file=$(_file "$key"); art=$(_artifacts_dir "$key")
  mkdir -p "$RUNS_DIR" "$art"
  if [ -f "$file" ]; then return 0; fi   # idempotent: never clobber an existing run
  cat > "$file" <<EOF
ticket: $ticket
profile:
status: running
stage:
artifacts_dir: $art
base_sha:
signals:
spec:
  source: []
  requirements: []
  acceptance_criteria: []
  answers:
history:
EOF
}

cmd_path() { _validate_key "${1:-}"; _file "$1"; }

cmd_get() {
  _validate_key "${1:-}"
  local key="$1" field="$2" file
  file=$(_file "$key")
  grep -m1 "^$field:" "$file" 2>/dev/null | sed "s/^$field:[[:space:]]*//" || true
}

cmd_set() {
  _validate_key "${1:-}"
  local key="$1" field="$2" value="$3" file tmp
  file=$(_file "$key"); tmp=$(mktemp)
  if ! awk -v f="$field" -v v="$value" '
    $0 ~ "^" f ":" && !done { print f ": " v; done=1; next }
    { print }
    END { if (!done) exit 1 }
  ' "$file" > "$tmp"; then
    rm -f "$tmp"
    echo "run-state: field not found: '$field'" >&2
    exit 2
  fi
  mv "$tmp" "$file"
}

cmd_append_history() {
  _validate_key "${1:-}"
  local key="$1" stage="$2" decision="$3" by="$4" note="$5" file ts s_note
  file=$(_file "$key"); ts=$(date -u +%FT%TZ)
  s_note=$(_sanitize_value "$note")
  printf '  - {stage: %s, decision: %s, by: %s, at: %s, note: "%s"}\n' \
    "$stage" "$decision" "$by" "$ts" "$s_note" >> "$file"
}

cmd_append_answer() {
  _validate_key "${1:-}"
  local key="$1" text="$2" file tmp s_text
  file=$(_file "$key")
  s_text=$(_sanitize_value "$text")
  tmp=$(mktemp)
  awk -v t="$s_text" '
    BEGIN { in_answers=0; last=0; n=0 }
    {
      n++; line[n]=$0
      if ($0 ~ "^  answers:") { in_answers=1; last=n; next }
      if (in_answers) {
        if ($0 ~ "^    - ") { last=n } else { in_answers=0 }
      }
    }
    END {
      for (i=1; i<=n; i++) {
        print line[i]
        if (i==last) print "    - \"" t "\""
      }
    }
  ' "$file" > "$tmp"
  mv "$tmp" "$file"
}

cmd_decline_count() {
  _validate_key "${1:-}"
  local key="$1" stage="$2" file hist
  file=$(_file "$key")
  hist=$(grep "^  - {" "$file" 2>/dev/null || true)
  echo "$hist" | awk -v s="$stage" '
    {
      st=""; de=""
      if (match($0, /stage: [^,]+/))    { st=substr($0, RSTART+7,  RLENGTH-7) }
      if (match($0, /decision: [^,]+/)) { de=substr($0, RSTART+10, RLENGTH-10) }
      if (st==s) { if (de=="decline") c++; else c=0 }
    }
    END { print c+0 }
  '
}

cmd_commit() {
  _validate_key "${1:-}"
  local key="$1" stage="$2" decision="$3" file art art_status
  file=$(_file "$key"); art=$(_artifacts_dir "$key")
  local pathspec=("$file")
  art_status="$(git status --porcelain -- "$art" 2>/dev/null)"
  if [ -n "$art_status" ] || [ -n "$(git ls-files -- "$art" 2>/dev/null)" ]; then
    pathspec+=("$art")
  fi
  # `git commit -- <pathspec>` commits worktree-vs-HEAD, not index-vs-HEAD: probe
  # the same way, else a staged-then-worktree-reverted path looks "pending" here
  # but has nothing for `commit` to actually record, which aborts under set -e.
  local nothing_pending=0
  if git rev-parse --verify -q HEAD >/dev/null 2>&1; then
    if git diff --quiet HEAD -- "${pathspec[@]}" 2>/dev/null \
       && [ -z "$(git ls-files --others --exclude-standard -- "${pathspec[@]}" 2>/dev/null)" ]; then
      nothing_pending=1
    fi
  elif [ -z "$(git status --porcelain -- "${pathspec[@]}" 2>/dev/null)" ]; then
    nothing_pending=1   # no HEAD yet (first commit ever): status --porcelain is authoritative
  fi
  if [ "$nothing_pending" -eq 1 ]; then
    echo "run-state: nothing to commit"
    return 0
  fi
  git add -- "${pathspec[@]}"
  git commit -q -m "chore(autodidact-workflow): $stage $decision [$key]" -- "${pathspec[@]}"
}

# reads the `status:` field from the run-file as committed at HEAD.
# stdout: the status value — possibly empty when a HEAD copy exists but has
# no `status:` line (grep's own no-match must not trip `set -o pipefail`
# before the caller gets to decide what "empty" means; the trailing
# `|| true` neutralizes that).
# exit 1: no HEAD copy exists at all (file was never committed / untracked).
_head_status() {
  local f="$1" copy
  copy=$(git show "HEAD:$f" 2>/dev/null) || return 1
  printf '%s\n' "$copy" | grep -m1 '^status:' | sed 's/^status:[[:space:]]*//' || true
}

# builds the two exact paths itself (never a <KEY>* glob, which would sweep
# a sibling run like TASK-1* matching TASK-12)
cmd_cleanup() {
  _validate_key "${1:-}"
  local key="$1"; shift
  local push=0 force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --push)  push=1;  shift ;;
      --force) force=1; shift ;;
      *) echo "run-state: cleanup: unknown flag: $1" >&2; exit 2 ;;
    esac
  done

  local file art
  file=$(_file "$key"); art=$(_artifacts_dir "$key")

  # phase (a) — removal + commit. "already clean" only when BOTH the
  # filesystem is clear AND git has nothing pending for these paths: a
  # cleanup interrupted between `git rm` and `git commit` leaves the
  # filesystem clear but a staged deletion behind — a retry must still
  # finish that commit, not report clean and skip it.
  local git_pending
  git_pending="$(git status --porcelain -- "$file" "$art" 2>/dev/null)"
  if [ ! -e "$file" ] && [ ! -e "$art" ] && [ -z "$git_pending" ]; then
    echo "run-state: cleanup $key: already clean"
  else
    if [ -f "$file" ]; then
      if [ "$force" -ne 1 ]; then
        local status
        status=$(cmd_get "$key" status)
        if [ "$status" != "done" ]; then
          echo "run-state: cleanup $key: refusing — status is '$status', not 'done' (use --force to override)" >&2
          exit 1
        fi
        # worktree says done — but if HEAD already has a tracked copy, it
        # must ALSO say done: otherwise a cleanup interrupted between the
        # `git rm` below and its commit would land in the recovery branch,
        # which checks HEAD and would refuse a removal this guard itself
        # just authorized. No HEAD copy (never committed / untracked) has
        # no such hazard — the worktree check alone is enough there.
        local head_status
        if head_status=$(_head_status "$file"); then
          if [ -z "$head_status" ]; then
            echo "run-state: cleanup $key: refusing — committed run-file has no 'status:' field, cannot verify (use --force to override)" >&2
            exit 1
          elif [ "$head_status" != "done" ]; then
            echo "run-state: cleanup $key: refusing — status 'done' not yet committed — run: run-state.sh commit $key pr done (or --force)" >&2
            exit 1
          fi
        elif [ -n "$(git ls-files -- "$art" 2>/dev/null)" ]; then
          # no committed run-file, but the artifacts dir has tracked content:
          # the same hazard one corner deeper — an interrupted retry would
          # stage the tracked-artifact deletions but have no committed
          # run-file to verify against, landing in the recovery branch's
          # "cannot verify" refusal
          echo "run-state: cleanup $key: refusing — artifacts are tracked but the run-file was never committed — run: run-state.sh commit $key pr done (or --force)" >&2
          exit 1
        fi
      fi
    elif [ -e "$art" ]; then
      if [ "$force" -ne 1 ]; then
        # run-file missing → no status field left to verify; refuse orphaned
        # artifacts unless explicitly forced (status-done is the contract,
        # not "the run-file happens to be gone")
        echo "run-state: cleanup $key: refusing — run-file missing, cannot verify status (use --force to remove orphaned artifacts)" >&2
        exit 1
      fi
    elif [ "$force" -ne 1 ]; then
      # neither path exists in the worktree, but git_pending fired (else we'd
      # be "already clean"): a run-file deletion is staged/unstaged but not
      # committed. The real flow only reaches cleanup after `set status
      # done` + `commit ... pr done`, so HEAD's copy must record `done` —
      # verify it before finishing what could otherwise be an unverified
      # sweep of an active run whose file got git-rm'd some other way.
      local head_status
      if head_status=$(_head_status "$file"); then
        if [ -z "$head_status" ]; then
          echo "run-state: cleanup $key: refusing — run-file deletion pending, committed copy has no 'status:' field, cannot verify (use --force to override)" >&2
          exit 1
        elif [ "$head_status" != "done" ]; then
          echo "run-state: cleanup $key: refusing — run-file deletion pending but last committed status is '$head_status', not 'done' (use --force to override)" >&2
          exit 1
        fi
      else
        echo "run-state: cleanup $key: refusing — run-file deletion pending, cannot verify status (no committed copy; use --force to override)" >&2
        exit 1
      fi
    fi

    # -f: cleanup removes these paths unconditionally, even with pending edits
    # (e.g. the just-written `status: done` not yet committed)
    git rm -r -q -f --ignore-unmatch -- "$file" "$art" >/dev/null
    # git rm only touches tracked paths — untracked leftovers need plain removal
    [ -e "$file" ] && rm -f -- "$file"
    [ -e "$art" ]  && rm -rf -- "$art"

    # `git commit -- <pathspec>` errors if a pathspec never matched anything
    # git knows about (e.g. an artifacts dir that was always untracked) — only
    # pass paths that actually have a pending change to record.
    local pathspec=()
    [ -n "$(git status --porcelain -- "$file" 2>/dev/null)" ] && pathspec+=("$file")
    [ -n "$(git status --porcelain -- "$art" 2>/dev/null)" ]  && pathspec+=("$art")
    if [ "${#pathspec[@]}" -eq 0 ]; then
      echo "run-state: cleanup $key: nothing to commit"
    else
      git commit -q -m "chore(autodidact-workflow): cleanup [$key]" -- "${pathspec[@]}"
    fi
  fi

  # phase (b) — push. Always attempted when requested, even when phase (a)
  # had nothing to do: a plain push on an up-to-date branch is a harmless
  # no-op, and on a failed-push retry it's exactly what finishes the job.
  if [ "$push" -eq 1 ]; then
    if ! git push -q; then
      echo "run-state: cleanup $key: push failed (commit is safe locally) — re-run: run-state.sh cleanup $key --push" >&2
      exit 1
    fi
  fi
}

case "${1:-}" in
  init)           shift; cmd_init "$@" ;;
  path)           shift; cmd_path "$@" ;;
  get)            shift; cmd_get "$@" ;;
  set)            shift; cmd_set "$@" ;;
  append-history) shift; cmd_append_history "$@" ;;
  append-answer)  shift; cmd_append_answer "$@" ;;
  decline-count)  shift; cmd_decline_count "$@" ;;
  commit)         shift; cmd_commit "$@" ;;
  cleanup)        shift; cmd_cleanup "$@" ;;
  threshold)      echo "$THRESHOLD" ;;
  *) echo "usage: run-state.sh <init|path|get|set|append-history|append-answer|decline-count|commit|cleanup|threshold> <KEY> [args…]" >&2; exit 2 ;;
esac
