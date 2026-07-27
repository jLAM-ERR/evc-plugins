---
name: run
description: Drive a task through the generic gated workflow — intake, design panel, implementation, hardening and review, wrap-up — with explicit human gates, resumable state, and every gate decision captured into the project knowledge base. Use for non-trivial tasks that deserve staged delivery; input is a task description or spec file, no ticket system required.
invocation: user
disable-model-invocation: true
---

# run — the generic gated workflow

Genericized from upstream-source (extraction inventory kept locally). One
stage per invocation; freeze at every human gate; never infer approval
from silence. Helpers live in `scripts/` next to this file; state lives at
`.evc-workflow/runs/<KEY>/` (KEY = `TASK-<n>` or any `ABC-123`-style id
you pick for the run).

## Pipeline

`INTAKE → DESIGN → IMPLEMENT → HARDEN+REVIEW → WRAP-UP`

Use `scripts/run-state.sh` for init/status/record at every stage;
`--status` reports and performs no work.

1. **Intake (with bounded interrogation).** Read the task description or
   spec file. Extract requirements, acceptance criteria, affected
   components, risks. Then interrogate the gaps — ask the user the
   questions whose answers would change the design (max ~5, one round;
   contradictory or materially incomplete spec → stop and say so). Propose
   a profile via `scripts/profile-select.sh` from spec signals (points/ACs/
   components/type/risk) — never from estimated lines of code.
2. **Profile gate.** Explicit `--approve` or `--profile quick|standard|deep`.
3. **Design.** For profiles that call for it, spawn `panel-role` agents
   per `scripts/panel-members.sh`, then `synthesizer` merges into
   design.md. Surface conflicts with proposed resolutions; the user
   decides.
4. **Design gate.** Show the artifact; require explicit approval or a
   decline reason.
5. **Implement.** Delegate production edits to `implementer` task by task.
6. **Implementation gate.** Show the cumulative diff; require explicit
   approval or revision instructions.
7. **Harden + review.** Run `test-hardener`, then `auto-reviewer` per
   profile. Critical findings block until fixed or explicitly escalated.
8. **Wrap-up.** Summarize; branch/PR per project convention (`gh pr
   create` where available — ticket/PR-system specifics belong to a
   downstream overlay, not here); then close the learning loop (below).

## Learning-loop wiring (every gate — this is not optional)

After EACH explicit gate decision, capture it with the evc-learning
capture CLI (deterministic protocol — never hand-write entries). Locate it
at `<evc-plugins>/plugins/evc-learning/skills/capture/scripts/new_entry.py`
(installed plugin cache or repo checkout):

- gate **approved** and the stage taught something reusable →
  `--outcome approve` (what worked, principle-level);
- gate returned with **corrections** → `--outcome correct` (the corrected
  rule — this is the highest-value signal);
- gate **declined** an approach → `--outcome decline` (what was rejected
  and why);
- nothing learned (routine pass) → capture nothing; do not manufacture
  entries.

Always `--source gate --kb-root docs/knowledge`, `--ref` the touched
files. Exit 10 (duplicate) is fine; exit 2 (secret refusal) → redact and
retry, never bypass.

At **wrap-up**, run the thresholds check and act on it:

```sh
python3 <evc-plugins>/plugins/evc-learning/skills/distill/scripts/mechanical.py \
  thresholds --kb-root docs/knowledge
```

Exit 4 → tell the user thresholds are hit and offer to run the `distill`
skill now (workflow boundary = the designed distillation moment); exit 0 →
nothing to do; exit 1 → the project has no KB (suggest adopting the evc
skeleton).
