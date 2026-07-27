# evc-plugins

Claude Code plugin marketplace for **Enterprise Vibe Coding ([EVC](https://github.com/jLAM-ERR/evc))** — the
execution layer of the two-repo system (the knowledge layer is the `evc`
repo; its `CONTRACT.md` defines every format and CLI protocol used here).

| Plugin | Purpose |
|--------|---------|
| `evc-learning` | the learning loop: capture / retro / distill / promote |
| `evc-workflow` | generic gated workflow (v0: run skill + 5 role agents) wired to the learning loop |

## Install

```sh
/plugin marketplace add jLAM-ERR/evc-plugins
/plugin install evc-learning@evc-plugins
/plugin install evc-workflow@evc-plugins
```

## Repo layout

```
.claude-plugin/marketplace.json   the catalog
plugins/<name>/                   one dir per plugin (evc-learning also vendors lib/evclib)
tools/evclib/                     vendored from evc (see tools/evclib/SOURCE)
tools/skill_lint.py               deterministic SKILL.md validation
tests/                            pytest (dev-only dependency)
docs/                             per-harness smoke-test checklist + results
```

Skills follow the Agent Skills standard (SKILL.md + frontmatter), so they
are portable beyond Claude Code; adapter-bound parts (hooks, agents) are
documented as such per plugin.

## Development rules

- `tools/evclib/` is **vendored, never edited here** — fix in evc, re-vendor,
  update `tools/evclib/SOURCE`. Scripts import it; no copies of
  security-relevant code.
- Every skill passes `python3 tools/skill_lint.py` (frontmatter, name/dir
  match, description length, invocation marker).
- `pytest -q` must be green before any commit that touches scripts.
