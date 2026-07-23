#!/usr/bin/env bash
# profile-select.sh — choose a workflow tier from ticket-derived signals.
# Signals (all optional): --points N  --acs N  --components N  --type bug|feature|spike  --risk a,b
# Override:               --profile quick|standard|deep
# NEVER consumes lines-of-code — size comes only from the ticket.
# Emits key=value lines: tier, reason, stages (post-intake; intake is a fixed
# pre-stage and is NEVER listed here), review, security_required, defaulted.
set -euo pipefail

points=""; acs=""; components=""; type=""; risk=""; forced=""

# bash-3.2-safe non-negative-integer check (no extglob, no regex in case patterns)
_require_nonneg_int() {
  case "$2" in
    *[!0-9]*|'') echo "profile-select: $1 must be a non-negative integer, got: $2" >&2; exit 2 ;;
  esac
}

while [ $# -gt 0 ]; do
  case "$1" in
    --points)     _require_nonneg_int --points "$2";     points="$2";     shift 2 ;;
    --acs)        _require_nonneg_int --acs "$2";        acs="$2";        shift 2 ;;
    --components) _require_nonneg_int --components "$2"; components="$2"; shift 2 ;;
    --type)       type="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"; shift 2 ;;
    --risk)       risk="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"; shift 2 ;;
    --profile)    forced="$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')"; shift 2 ;;
    *) echo "profile-select: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Hardcoded tier config → sets STAGES (never includes intake) + REVIEW.
_tier_config() {
  case "$1" in
    quick)    STAGES="implement,pr";               REVIEW="none" ;;
    standard) STAGES="design,implement,harden,pr"; REVIEW="single" ;;
    deep)     STAGES="design,implement,harden,pr"; REVIEW="nvote=3" ;;
    *) echo "profile-select: invalid tier: $1" >&2; exit 2 ;;
  esac
}

_bump() {
  case "$1" in
    quick)    echo standard ;;
    standard) echo deep ;;
    *)        echo deep ;;
  esac
}

security_required=false
defaulted=false

risk_hit=""
case ",$risk," in
  *,payments,*|*,auth,*|*,pii,*|*,regulated,*) risk_hit=1 ;;
esac

if [ -n "$forced" ]; then
  tier="$forced"
  _tier_config "$tier"   # validates; invalid → exit 2
  reason="forced via --profile=$forced"
  [ -n "$risk_hit" ] && security_required=true
else
  if [ -n "$points" ]; then
    if   [ "$points" -le 2 ]; then size=small
    elif [ "$points" -le 8 ]; then size=medium
    else size=large; fi
    reason="points=$points -> $size"
  elif [ -n "$acs" ] || [ -n "$components" ]; then
    a=${acs:-0}; c=${components:-0}
    if   [ "$a" -le 2 ] && [ "$c" -le 1 ]; then size=small
    elif [ "$a" -le 5 ] && [ "$c" -le 2 ]; then size=medium
    else size=large; fi
    reason="acs=$a components=$c -> $size"
  else
    size=medium; defaulted=true
    reason="no size signals -> default standard"
  fi

  if [ "$type" = "spike" ] && [ "$size" = "small" ]; then
    size=medium; reason="$reason; spike -> medium"
  fi

  case "$size" in
    small)  tier=quick ;;
    medium) tier=standard ;;
    large)  tier=deep ;;
  esac

  if [ -n "$risk_hit" ]; then
    bumped=$(_bump "$tier")
    reason="$reason; risk=$risk bumped $tier->$bumped"
    tier="$bumped"; security_required=true
  fi
  _tier_config "$tier"
fi

cat <<EOF
tier=$tier
reason=$reason
stages=$STAGES
review=$REVIEW
security_required=$security_required
defaulted=$defaulted
EOF
