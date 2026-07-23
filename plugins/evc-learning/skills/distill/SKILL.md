---
name: distill
description: Garden the project knowledge base — merge duplicates, resolve contradictions, promote recurring candidates, tombstone stale ones — as a reviewable gardening PR. Run when thresholds are hit (the workflow's final stage checks them) or on demand.
invocation: user
disable-model-invocation: true
---

# distill — KB gardening as a PR

The ONLY path allowed to mutate existing entries or touch AGENTS.md.
Everything lands on a branch as a PR a human merges (mandatory until an
eval gate exists — CONTRACT §Moderation).

## Procedure

1. **Mechanical pass (deterministic first):**

   ```sh
   python3 "$(dirname "$SKILL_PATH")/scripts/mechanical.py" report \
     --kb-root docs/knowledge
   ```

   The JSON gives you: the kb-lint verdict, threshold state, recurrence
   groups (computed over the FULL candidate set — including identical-id
   duplicates from parallel branches), stale candidates (> 90 days), and
   **action chunks already capped at the 15-entry PR budget**.

2. **Branch:** `git switch -c gardening/<date>` — never garden on main.

3. **Semantic pass — delta edits only, in the anti-sprawl order:**
   - *patch existing entry*: a candidate that refines an existing entry →
     fold its content into that entry, delete the candidate file;
   - *extend umbrella*: candidates marked `umbrella:` → merge into the
     broader entry;
   - *keep standalone* only when neither applies.
   Also: resolve `contradiction:` pairs (pick the correct side, deprecate
   the other with a one-line reason), promote `candidate → approved` at
   recurrence ≥ 2–3 or clear utility, tombstone the stale list.
   **Never rewrite a whole file** ("context collapse"); after ANY body
   edit, recompute the entry `id` (kb-lint hard-fails on mismatch) and
   keep INDEX.md lines in sync.

4. **One chunk = one PR.** If the report produced multiple chunks, open
   them as separate PRs — the 15-entry budget is enforcement, not advice.
   Chunks flagged `oversized` are mechanical splits of one big action:
   re-cut them on semantic boundaries if the mechanical cut is awkward,
   but never merge them back over the budget.

5. **Close out the PR:** append one line to `docs/knowledge/.gardening-log`
   *inside the PR*: `YYYY-MM-DD gardening: <n> entries, <summary>`. Run
   kb-lint (`--layout project`) — must exit 0. Open the PR and stop:
   **a human merges it**.

AGENTS.md changes (new always-on rule earned by repeated corrections)
ride the same gardening PR — nothing else may touch that file.
