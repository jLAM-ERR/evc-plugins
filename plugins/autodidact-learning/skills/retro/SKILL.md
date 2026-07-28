---
name: retro
description: Session retrospective that turns this session's transcript into at most 10 principle-level knowledge proposals, each behind explicit user approval. Run at the end of a substantial session, or when the user asks for a retro.
invocation: user
disable-model-invocation: true
---

# retro — session retrospective

Evidence-based shape (evc `methodology/learning-loop.md`): deterministic
pre-pass → **parallel fresh-context analysts** → single curator merge →
per-proposal approval. Never re-review the same context repeatedly — one
fresh pass beats looping.

## Procedure

1. **Pre-pass (deterministic).** Export or locate the session transcript,
   then:

   ```sh
   python3 "$(dirname "$SKILL_PATH")/scripts/signals.py" scan \
     --transcript <transcript-file>
   ```

   The JSON lists corrections (dominant signal), errors, and
   repeated-failure clusters, secret-redacted.

2. **Parallel lens analysts (fresh context).** Spawn three subagents in one
   batch — each gets ONLY the transcript path + the signals JSON, none of
   this session's conversation:
   - *corrections lens*: what did the user correct, and what rule would
     have prevented each correction?
   - *errors lens*: which failures repeated, and what check/knowledge would
     have avoided the retry cluster?
   - *successes lens*: what worked well enough to become a reusable
     pattern?
   Each analyst returns findings **abstracted to principle level**
   (instance-level learnings decay; principles compound).

3. **Curator merge (you).** Merge the three lists: dedupe, drop anything
   that is really codebase-derivable, keep at most **10 proposals**
   (CONTRACT §Tunables). Before finalizing, read
   `.evc/retro-acceptance.md` if present and **deprioritize finding types
   the user has repeatedly rejected**.

4. **Per-proposal approval.** Present each proposal separately (topic, the
   principle, suggested outcome mapping). Nothing is written silently.

5. **Capture accepted proposals** through the capture CLI
   (`--source retro`; outcome: `approve` for patterns that worked,
   `correct` for corrected behavior, `decline` for things to avoid) — see
   the `capture` skill; never hand-write entries.

6. **Log acceptance.** Append one line per proposal to
   `.evc/retro-acceptance.md` (create the dir if needed):
   `YYYY-MM-DD accepted|rejected <lens> — <topic>`. This log is what makes
   step 3's self-tuning possible.
