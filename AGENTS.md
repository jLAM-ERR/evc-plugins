# Agent rules — evc-plugins repository

This repo is the EVC execution layer: a Claude Code plugin marketplace
shipping `evc-learning` (capture / retro / distill / promote) and
`evc-workflow` (generic gated workflow). The knowledge layer and the
normative contract live in the sibling `evc` repo — `CONTRACT.md` there
governs every format, routing rule, and CLI protocol implemented here.

## Hard rules

- `tools/evclib/` and `plugins/evc-learning/lib/evclib/` are **vendored
  from evc, never edited here** — fix in evc, re-copy both, update
  `SOURCE`; a test enforces byte-identity between the copies. Real copies,
  not symlinks — installs copy only the plugin dir; full rationale in the
  evc KB: `knowledge/solutions/20260727-vendored-lib-in-installable-plugins.md`.
- Scripts are Python 3.12 **stdlib-only** at runtime (offline corporate CI;
  pytest is dev-only). No network calls anywhere.
- Every skill passes `python3 tools/skill_lint.py` (frontmatter, name/dir
  match, description ≤1024, `invocation:` marker; `invocation: user`
  requires `disable-model-invocation: true`).
- `python3 -m pytest tests/ -q` must be green before any commit touching
  scripts; run the shell suites under `plugins/evc-workflow/skills/run/
  scripts/*_test.sh` when touching those helpers.
- Exit codes and JSON shapes of `new_entry.py` / `mechanical.py` are
  CONTRACT-frozen — changing them is a contract change, made in evc first.
- upstream-source (in corporate upstream-hub) is a read-only extraction source;
  never modify it from here. Corporate wiring (Jira/Confluence/Bitbucket)
  belongs to downstream overlays, not this repo.
