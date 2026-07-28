# Per-harness smoke tests

Checklist per harness, run inside a project adopted from the evc skeleton
(`skeleton/` copied, gardening log refreshed, `.claude/skills/capture`
present, `.agents/skills → .claude/skills` symlink created):

1. **AGENTS.md read** — the harness's session demonstrably contains the
   project AGENTS.md (probe: ask for its exact first heading, no tools).
2. **Skills discovered** — the project-local `capture` skill appears in
   the harness's available skills.
3. **Capture writes entry** — the capture CLI creates a valid routed
   entry + INDEX line in `docs/knowledge/` (harness-agnostic: any harness
   with shell access can run it).
4. **kb-lint runs** — `python3 <evc>/tools/kb_lint.py --root . --layout
   project` exits 0.

Checks 3–4 are mechanical and harness-independent — executed once per
machine. Checks 1–2 are per-harness behavioral probes.

## Results — 2026-07-23, macOS (Darwin 25.5.0)

| Check | Claude Code 2.1.218 | Codex CLI 0.144.5 | OpenCode | Kilo Code |
|-------|---------------------|-------------------|----------|-----------|
| AGENTS.md read | **PASS** — `claude -p` returned the exact heading through the `CLAUDE.md @AGENTS.md` shim | **PASS** — native read confirmed (merged after the user's global `~/.codex` guidance; project file explicitly confirmed present in context) | BLOCKED¹ | PENDING² |
| Skills discovered | **PASS** — marketplace plugins load (`claude plugin details`: autodidact-learning 4 skills + 2 hooks, autodidact-workflow 1 skill + 5 agents); project `.claude/skills/capture` native | **PASS** — `capture` listed, discovered via the `.agents/skills` symlink | BLOCKED¹ | PENDING² |
| Capture writes entry | **PASS** — `new_entry.py capture` wrote `solutions/20260723-smoke-capture.md` + INDEX line (exit 0) | same (mechanical) | same (mechanical) | same (mechanical) |
| kb-lint runs | **PASS** — exit 0 before and after capture | same (mechanical) | same (mechanical) | same (mechanical) |

¹ **OpenCode — installed, probe blocked**: `opencode run` fails before any
model call — the configured provider key is expired ("Срок действия ключа
истёк"). Steps to finish (5 min): regenerate the provider key → `opencode
auth login` (or update the key in OpenCode config) → run the two probe
questions from the checklist in the smoke project → fill this table.
OpenCode reads AGENTS.md natively and discovers `.claude/skills/` /
`.opencode/skill/` per its docs, so PASS is expected but must be observed,
not assumed.

² **Kilo Code — not installed** on this machine. Steps: install the Kilo
Code VS Code extension → open the smoke project → confirm AGENTS.md is on
by default (Kilo reads it natively) → check the skills panel lists
`capture` → fill this table.

## Reproduce

```sh
SMOKE=$(mktemp -d)/smoke && cp -R <evc>/skeleton/. "$SMOKE" && cd "$SMOKE"
rm ADOPTION.md && echo "$(date +%F) bootstrap: adopted" > docs/knowledge/.gardening-log
git init -q && git add -A && git commit -qm init
mkdir -p .claude/skills && cp -R <autodidact-plugins>/plugins/autodidact-learning/skills/capture .claude/skills/
mkdir -p .agents && ln -s ../.claude/skills .agents/skills
python3 <evc>/tools/kb_lint.py --root . --layout project           # check 4
printf 'A lesson.' > /tmp/b.md && python3 .claude/skills/capture/scripts/new_entry.py \
  capture --kb-root docs/knowledge --topic smoke --outcome approve \
  --source self-review --body-file /tmp/b.md                        # check 3
# checks 1-2: run each harness's probe questions from the checklist above
```
