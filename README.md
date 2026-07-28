# autodidact-plugins

Claude Code plugin marketplace for **[autodidact](https://github.com/jLAM-ERR/autodidact)** — the
execution layer of the two-repo system (the knowledge layer is the `autodidact`
repo; its `CONTRACT.md` defines every format and CLI protocol used here).

| Plugin | Version | Purpose |
|--------|---------|---------|
| `autodidact-learning` | 0.3.0 | the learning loop: capture / retro / distill / promote |
| `autodidact-workflow` | 0.2.0 | generic gated workflow (v0: run skill + 5 role agents) wired to the learning loop |

Both plugins implement **autodidact CONTRACT 2.x** (currently 2.0.0). The two
repos version independently — autodidact accretes knowledge continuously, plugins
ship as releases — so compatibility is expressed by the CONTRACT major
version, not by matching repo versions. Releases are annotated git tags:
`vX.Y.Z` in autodidact, `<plugin>-vX.Y.Z` here.

## Install

```sh
/plugin marketplace add jLAM-ERR/autodidact-plugins
/plugin install autodidact-learning@autodidact-plugins
/plugin install autodidact-workflow@autodidact-plugins
```

## Repo layout

```
.claude-plugin/marketplace.json   the catalog
plugins/<name>/                   one dir per plugin (autodidact-learning also vendors lib/kblib)
tools/kblib/                     vendored from autodidact (see tools/kblib/SOURCE)
tools/skill_lint.py               deterministic SKILL.md validation
tests/                            pytest (dev-only dependency)
docs/                             per-harness smoke-test checklist + results
```

Skills follow the Agent Skills standard (SKILL.md + frontmatter), so they
are portable beyond Claude Code; adapter-bound parts (hooks, agents) are
documented as such per plugin.

## Development rules

- `kblib` is **vendored from autodidact, never edited here**. It lives in two
  places — `tools/kblib/` (repo tooling) and
  `plugins/autodidact-learning/lib/kblib/` (the copy installed plugins import,
  since an install copies only the plugin dir). Fix in autodidact, re-copy both,
  update each `SOURCE` marker; a test enforces they stay byte-identical.
- Every skill passes `python3 tools/skill_lint.py` (frontmatter, name/dir
  match, description length, invocation marker).
- `pytest -q` must be green before any commit that touches scripts.
