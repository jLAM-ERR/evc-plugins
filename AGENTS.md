# Agent rules — autodidact-plugins repository

This repo is the EVC execution layer: a Claude Code plugin marketplace
shipping `autodidact-learning` (capture / retro / distill / promote) and
`autodidact-workflow` (generic gated workflow). The knowledge layer and the
normative contract live in the sibling `evc` repo — `CONTRACT.md` there
governs every format, routing rule, and CLI protocol implemented here.

## Hard rules

- Every vendored `evclib` location here (`tools/evclib/`,
  `plugins/autodidact-learning/lib/`) is **copied from evc, never edited here** —
  fix in evc, re-copy *every* location, update each `SOURCE` marker. Real
  copies, not symlinks: an install copies only the plugin dir. A copy no
  byte-identity test covers is a false provenance claim — test it or
  delete it. Rationale: evc `README.md` / `AGENTS.md`.
- Scripts are Python 3.12 **stdlib-only** at runtime (offline corporate CI;
  pytest is dev-only). No network calls anywhere.
- Every skill passes `python3 tools/skill_lint.py` (frontmatter, name/dir
  match, description ≤1024, `invocation:` marker; `invocation: user`
  requires `disable-model-invocation: true`).
- `python3 -m pytest tests/ -q` must be green before any commit touching
  scripts; run the shell suites under `plugins/autodidact-workflow/skills/run/
  scripts/*_test.sh` when touching those helpers.
- Exit codes and JSON shapes of `new_entry.py` / `mechanical.py` are
  CONTRACT-frozen — changing them is a contract change, made in evc first
  (bump CONTRACT's version there, tag it, then re-vendor here).
- Releases are annotated tags: `<plugin>-vX.Y.Z` matching that plugin's
  `plugin.json` version. Bump the manifest and tag in the same commit;
  the two plugins version independently of each other and of evc.
- The corporate plugin this repo was extracted from lives outside this
  repo and is a read-only source; never modify it from here. Corporate
  wiring (Jira/Confluence/Bitbucket) belongs to downstream overlays, not
  this repo.
