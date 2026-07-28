"""skill_lint tests — one valid skill + each violation class."""

from pathlib import Path

import skill_lint

VALID = """---
name: capture
description: Capture a gate decision into the project knowledge base.
invocation: model
---

# Capture

Body.
"""


def make_skill(root: Path, dirname: str, content: str) -> Path:
    skill_dir = root / "plugins" / "evc-learning" / "skills" / dirname
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_valid_skill_passes(tmp_path):
    make_skill(tmp_path, "capture", VALID)
    assert skill_lint.main(["--root", str(tmp_path)]) == 0


def test_missing_skill_md(tmp_path):
    (tmp_path / "plugins/p/skills/empty").mkdir(parents=True)
    assert skill_lint.main(["--root", str(tmp_path)]) == 2


def test_unparseable_frontmatter(tmp_path):
    make_skill(tmp_path, "capture", "---\nname: >\n  folded\n---\nbody\n")
    assert skill_lint.main(["--root", str(tmp_path)]) == 2


def test_name_dir_mismatch(tmp_path):
    make_skill(tmp_path, "other-dir", VALID)
    problems = skill_lint.lint_skill_dir(
        tmp_path / "plugins/evc-learning/skills/other-dir"
    )
    assert any("does not match dir" in p for p in problems)


def test_name_too_long(tmp_path):
    long_name = "a" * 65
    content = VALID.replace("name: capture", f"name: {long_name}")
    d = make_skill(tmp_path, long_name, content)
    assert any("longer than 64" in p for p in skill_lint.lint_skill_dir(d))


def test_name_not_kebab(tmp_path):
    content = VALID.replace("name: capture", "name: Capture_It")
    d = make_skill(tmp_path, "capture", content)
    # uppercase key value fails NAME_RE before the dir-match check
    assert any("not lowercase-kebab" in p for p in skill_lint.lint_skill_dir(d))


def test_description_missing(tmp_path):
    content = VALID.replace(
        "description: Capture a gate decision into the project knowledge base.\n", ""
    )
    d = make_skill(tmp_path, "capture", content)
    assert any("description missing" in p for p in skill_lint.lint_skill_dir(d))


def test_description_too_long(tmp_path):
    content = VALID.replace(
        "description: Capture a gate decision into the project knowledge base.",
        f"description: {'x' * 1025}",
    )
    d = make_skill(tmp_path, "capture", content)
    assert any("longer than 1024" in p for p in skill_lint.lint_skill_dir(d))


def test_invocation_marker_missing(tmp_path):
    content = VALID.replace("invocation: model\n", "")
    d = make_skill(tmp_path, "capture", content)
    assert any("invocation marker" in p for p in skill_lint.lint_skill_dir(d))


def test_user_invocation_requires_disable_flag(tmp_path):
    content = VALID.replace("invocation: model", "invocation: user")
    d = make_skill(tmp_path, "capture", content)
    assert any("disable-model-invocation" in p for p in skill_lint.lint_skill_dir(d))
    fixed = content.replace(
        "invocation: user", "invocation: user\ndisable-model-invocation: true"
    )
    (d / "SKILL.md").write_text(fixed, encoding="utf-8")
    assert skill_lint.lint_skill_dir(d) == []


def test_secret_in_skill_md_fails(tmp_path):
    d = make_skill(tmp_path, "capture", VALID + "\nexample AKIAIOSFODNN7EXAMPLE\n")
    assert any("KB-SEC-002" in p for p in skill_lint.lint_skill_dir(d))


def test_vendored_kblib_imports():
    from kblib import frontmatter, kb_checks, secret_rules  # noqa: F401

    assert frontmatter.entry_id("hello world") == "b94d27b9934d"
    assert (Path(__file__).parent.parent / "tools/kblib/SOURCE").is_file()
