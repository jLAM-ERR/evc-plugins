#!/usr/bin/env python3
"""skill-lint — deterministic SKILL.md validation for this marketplace.

Checks per skill dir (plugins/*/skills/*/):
  1. SKILL.md exists and its frontmatter parses (restricted subset; keys
     may contain dashes, unlike KB entries);
  2. name: present, <=64 chars, lowercase kebab, equals the dir name
     (agentskills.io spec);
  3. description: present, <=1024 chars (spec);
  4. invocation marker present: `invocation: user|model|both` (EVC rule --
     every skill declares how it is meant to be triggered);
  5. `invocation: user` requires `disable-model-invocation: true` (the
     Claude Code mechanism that actually enforces it);
  6. secret scan over the whole SKILL.md (evclib rules).

Exit codes: 0 clean / 2 violations (mirrors kb-lint hard-fail semantics).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evclib import frontmatter, secret_rules  # noqa: E402

SKILL_KEY_RE = re.compile(r"^([a-z][a-z0-9_-]*)$")
SCALAR_RE = re.compile(r"^([a-z][a-z0-9_-]*): (.+)$")
LIST_HEAD_RE = re.compile(r"^([a-z][a-z0-9_-]*):$")
LIST_ITEM_RE = re.compile(r"^  - (.+)$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
INVOCATION_VALUES = ("user", "model", "both")


def parse_skill_frontmatter(text: str) -> dict[str, str | list[str]]:
    """Same grammar as evclib.frontmatter but keys may contain dashes
    (SKILL.md carries keys like disable-model-invocation)."""
    fm_lines, _body = frontmatter.split(text)
    data: dict[str, str | list[str]] = {}
    open_list: str | None = None
    for line in fm_lines:
        if "\t" in line or line.strip() == "" or line.lstrip().startswith("#"):
            raise frontmatter.FrontmatterError(f"bad frontmatter line: {line!r}")
        if m := LIST_ITEM_RE.match(line):
            if open_list is None:
                raise frontmatter.FrontmatterError(f"list item without head: {line!r}")
            items = data[open_list]
            assert isinstance(items, list)
            items.append(m.group(1).rstrip())
        elif m := SCALAR_RE.match(line):
            key, value = m.group(1), m.group(2).rstrip()
            if key in data:
                raise frontmatter.FrontmatterError(f"duplicate key: {key}")
            data[key] = value
            open_list = None
        elif m := LIST_HEAD_RE.match(line):
            key = m.group(1)
            if key in data:
                raise frontmatter.FrontmatterError(f"duplicate key: {key}")
            data[key] = []
            open_list = key
        else:
            raise frontmatter.FrontmatterError(f"line matches no allowed form: {line!r}")
    for key, value in data.items():
        if isinstance(value, list) and not value:
            raise frontmatter.FrontmatterError(f"list head with zero items: {key}")
    return data


def lint_skill_dir(skill_dir: Path) -> list[str]:
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir}: SKILL.md missing"]
    text = skill_md.read_text(encoding="utf-8")
    try:
        fm = parse_skill_frontmatter(text)
    except frontmatter.FrontmatterError as exc:
        return [f"{skill_md}: {exc}"]
    name = fm.get("name")
    if not isinstance(name, str):
        problems.append(f"{skill_md}: name missing or not a scalar")
    else:
        if len(name) > 64:
            problems.append(f"{skill_md}: name longer than 64 chars")
        if not NAME_RE.match(name):
            problems.append(f"{skill_md}: name not lowercase-kebab: {name!r}")
        if name != skill_dir.name:
            problems.append(
                f"{skill_md}: name {name!r} does not match dir {skill_dir.name!r}"
            )
    description = fm.get("description")
    if not isinstance(description, str):
        problems.append(f"{skill_md}: description missing or not a scalar")
    elif len(description) > 1024:
        problems.append(f"{skill_md}: description longer than 1024 chars")
    invocation = fm.get("invocation")
    if invocation not in INVOCATION_VALUES:
        problems.append(
            f"{skill_md}: invocation marker missing or invalid "
            f"(need one of {INVOCATION_VALUES})"
        )
    if invocation == "user" and fm.get("disable-model-invocation") != "true":
        problems.append(
            f"{skill_md}: invocation: user requires disable-model-invocation: true"
        )
    for f in secret_rules.scan_text(text):
        problems.append(f"{skill_md}: secret scan {f.rule_id} at line {f.line_no}")
    return problems


def iter_skill_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("plugins/*/skills/*") if p.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-lint", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    problems: list[str] = []
    for skill_dir in iter_skill_dirs(args.root):
        problems += lint_skill_dir(skill_dir)
    for p in problems:
        print(p)
    if problems:
        print(f"skill-lint: {len(problems)} problem(s)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
