#!/usr/bin/env bash
# panel-members.sh — resolve the design-panel role list for a (tier, stage).
#   members <tier> <stage> [--security-required]
# Reads a flat `tier.stage=role,role` config: the project's
# .autodidact-workflow/panel-members.conf if present, else the shipped default.
# Prints one role per line. Unknown tier.stage → exit 2.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CONF="$SCRIPT_DIR/panel-members.default.conf"
PROJECT_CONF=".autodidact-workflow/panel-members.conf"

_trim() {
  printf '%s' "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

cmd_members() {
  [ $# -ge 2 ] || { echo "usage: members <tier> <stage> [--security-required]" >&2; exit 2; }
  local tier="$1" stage="$2"; shift 2
  local security_required=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --security-required) security_required=1; shift ;;
      *) echo "panel-members: unknown arg: $1" >&2; exit 2 ;;
    esac
  done

  local conf="$DEFAULT_CONF"
  [ -f "$PROJECT_CONF" ] && conf="$PROJECT_CONF"

  local key="$tier.$stage" line roles
  line=$(grep -m1 "^$key=" "$conf" 2>/dev/null || true)
  [ -n "$line" ] || { echo "panel-members: no members for $key" >&2; exit 2; }
  roles=$(echo "$line" | cut -d= -f2-)

  local has_security="" r trimmed
  local members=()
  IFS=',' read -ra arr <<< "$roles"
  for r in ${arr[@]+"${arr[@]}"}; do
    trimmed="$(_trim "$r")"
    [ -n "$trimmed" ] || continue
    [ "$trimmed" = "security" ] && has_security=1
    members+=("$trimmed")
  done
  [ ${#members[@]} -gt 0 ] || { echo "panel-members: empty member list for $key" >&2; exit 2; }

  for r in "${members[@]}"; do
    echo "$r"
  done
  if [ -n "$security_required" ] && [ -z "$has_security" ]; then
    echo "security"
  fi
}

case "${1:-}" in
  members) shift; cmd_members "$@" ;;
  *) echo "usage: panel-members.sh members <tier> <stage> [--security-required]" >&2; exit 2 ;;
esac
