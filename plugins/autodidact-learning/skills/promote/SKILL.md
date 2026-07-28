---
name: promote
description: Promote a project knowledge entry that generalizes across projects into the shared evc knowledge base via PR, with the stricter destination secret gate and a redaction checklist. Run when the user asks to promote, or when distill flagged promote-eligible entries.
invocation: user
disable-model-invocation: true
---

# promote — project KB → shared evc KB

## Eligibility (all must hold)

- The learning **recurs across projects** (seen in ≥2 project KBs, or
  distill marked the group `promote_eligible` and you know it applies
  elsewhere) — not just repeated within this project.
- Nothing project-specific remains: no repo paths, service names, team
  names, ticket ids, internal hostnames.
- It is principle-level (would make sense to a stranger on another team).

## Procedure

1. **Generalize.** Rewrite the entry body without project specifics; keep
   it ~10–30 lines. The evc entry is a NEW entry (fresh id from the new
   body) targeting the same category under evc's `knowledge/`.
2. **Destination secret gate (stricter, per CONTRACT):** scan with the
   `evc` profile — ONLY evc's `tools/allowlist.txt` applies; the project's
   local allowlist does NOT travel upstream:

   ```sh
   python3 <evc-checkout>/tools/kb_lint.py --root <evc-checkout> --layout hub
   ```

   after placing the entry (next step) — exit must be 0.
3. **Redaction checklist (human-confirmed, every line):**
   - [ ] no credentials, tokens, keys (the scan is a net, not a substitute)
   - [ ] no personal data (names, emails, accounts)
   - [ ] no internal URLs/hostnames/architecture identifiers
   - [ ] no client or business-confidential specifics
4. **Branch in the evc checkout**, add the entry file + its INDEX.md line
   (use the capture CLI with `--kb-root <evc-checkout>/knowledge` — never
   hand-write), run kb-lint, commit.
5. **Open the PR**: `gh pr create` where GitHub is available; on the
   corporate Bitbucket overlay use its `bitbucket-pr.sh` slot instead
   (documented there — this skill does not embed corporate wiring).
6. Stop after opening: **a human reviews and merges** (CONTRACT
   §Moderation). evc's own gardening dedupes arrivals from many projects.
