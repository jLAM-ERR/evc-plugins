---
name: capture
description: Capture a learning into the project knowledge base as an append-only candidate entry. Use after a workflow gate decision (approve/correct/decline), after a self-review finding in auto mode, or when a good answer was assembled mid-task that should not die in chat history (the file-back rule).
invocation: both
---

# capture — file a learning into the project KB

Normative rules: `CONTRACT.md` in the autodidact repo. This skill only *classifies
and appends* — it never edits existing entries (mutations belong to the
`distill` gardening PR).

## When to invoke

- A workflow **gate decision** just happened (approve / correct / decline).
- **Self-review** in auto mode found something worth keeping
  (`--source self-review`).
- **File-back rule**: you assembled a good answer from KB queries or
  investigation during the task — file it before the session ends.

## How

1. Distill the learning to **principle level** (what should be done
   differently next time, not what happened this once). Keep the body
   ~10-30 lines. Write it to a temp file.
2. Run the deterministic CLI (it enforces routing, hashing, the secret
   gate, and arbitration — do not hand-write entry files):

   ```sh
   python3 "$(dirname "$SKILL_PATH")/scripts/new_entry.py" capture \
     --kb-root docs/knowledge \
     --topic "short phrase" \
     --outcome approve|correct|decline \
     --source gate|self-review|retro \
     --ref path/to/file.py@<short-sha> \
     --body-file /tmp/learning.md
   ```

   Routing is fixed: approve → `solutions/`, correct → `conventions/`,
   decline → `anti-patterns/`.

3. Read the JSON result:
   - `written` (exit 0) — done; the entry and its INDEX line exist.
   - `noop` (exit 10) — an identical entry already exists at `path`;
     nothing to do.
   - `refused` (exit 2) — the secret scan matched (`findings` lists rule
     IDs). **Redact the body and retry; never work around the gate.**
4. If you can judge relationships better than the CLI's term-overlap
   heuristic, pass them explicitly: `--related umbrella:conventions/x.md`
   or `--related contradiction:solutions/y.md`. Contradictions are fine to
   record — the gardener resolves them; do NOT edit the older entry.

## Hard rules

- Append-only: never modify an existing entry file, whatever you find.
- Never write entries by hand — the CLI is the only write path (it is what
  guarantees hash ids, schema validity, and the secret gate).
- One learning per entry. Two lessons = two captures.
