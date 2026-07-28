"""mechanical.py tests — recurrence, staleness, thresholds, PR counter."""

import importlib.util
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from kblib import frontmatter

REPO = Path(__file__).resolve().parent.parent
MECHANICAL = REPO / "plugins/evc-learning/skills/distill/scripts/mechanical.py"

spec = importlib.util.spec_from_file_location("mechanical", MECHANICAL)
mechanical = importlib.util.module_from_spec(spec)
sys.modules["mechanical"] = mechanical  # @dataclass needs the module registered
spec.loader.exec_module(mechanical)

TODAY = date(2026, 7, 23)


def make_kb(tmp_path: Path, project_layout: bool = True) -> Path:
    kb = (tmp_path / "docs" / "knowledge") if project_layout else (tmp_path / "knowledge")
    for cat in ("patterns", "conventions", "solutions", "anti-patterns", "glossary"):
        (kb / cat).mkdir(parents=True)
    (kb / "INDEX.md").write_text(
        "# Knowledge index\n\n## Patterns\n\n## Conventions\n\n"
        "## Solutions\n\n## Anti-patterns\n\n## Glossary\n"
    )
    (kb / ".gardening-log").write_text(f"{TODAY.isoformat()} bootstrap\n")
    return kb


def write_entry(kb: Path, category: str, name: str, body: str, *,
                status="candidate", entry_date=None, related=(), index=True):
    entry_date = entry_date or TODAY.isoformat()
    lines = ["---", f"id: {frontmatter.entry_id(body)}", f"status: {status}",
             "source: gate", f"date: {entry_date}", f"topic: {name}"]
    if related:
        lines.append("related:")
        lines += [f"  - {r}" for r in related]
    lines += ["---", "", body, ""]
    (kb / category / f"{name}.md").write_text("\n".join(lines))
    if index:
        index_file = kb / "INDEX.md"
        index_file.write_text(
            index_file.read_text() + f"- [{name}]({category}/{name}.md) — t\n"
        )
    return f"{category}/{name}.md"


def test_thresholds_quiet_kb_not_triggered(tmp_path):
    kb = make_kb(tmp_path)
    data = mechanical.thresholds_data(kb, TODAY)
    assert data["triggered"] is False
    assert data["candidates"] == 0


def test_thresholds_candidate_count_triggers(tmp_path):
    kb = make_kb(tmp_path)
    for i in range(26):
        write_entry(kb, "solutions", f"cand-{i}", f"body {i}", index=False)
    data = mechanical.thresholds_data(kb, TODAY)
    assert data["triggered"] is True
    assert any("candidates 26" in r for r in data["reasons"])


def test_thresholds_index_fill_triggers(tmp_path):
    kb = make_kb(tmp_path)
    index = kb / "INDEX.md"
    index.write_text(index.read_text() + "filler\n" * 165)
    data = mechanical.thresholds_data(kb, TODAY)
    assert data["index_pct"] > 0.80 and data["triggered"] is True


def test_thresholds_gardening_age_triggers_and_layout_correct_log(tmp_path):
    kb = make_kb(tmp_path)
    old = (TODAY - timedelta(days=45)).isoformat()
    (kb / ".gardening-log").write_text(f"{old} gardening: initial\n")
    data = mechanical.thresholds_data(kb, TODAY)
    assert data["days_since_gardening"] == 45 and data["triggered"] is True


def test_thresholds_missing_log_reports_but_does_not_trigger(tmp_path):
    kb = make_kb(tmp_path)
    (kb / ".gardening-log").unlink()
    data = mechanical.thresholds_data(kb, TODAY)
    assert data["days_since_gardening"] is None
    assert data["triggered"] is False
    assert any("missing" in r for r in data["reasons"])


def test_recurrence_concurrent_duplicates_same_id(tmp_path):
    kb = make_kb(tmp_path)
    # parallel branches captured the same body → same id, two files
    write_entry(kb, "solutions", "from-branch-a", "identical learning body")
    write_entry(kb, "solutions", "from-branch-b", "identical learning body")
    write_entry(kb, "conventions", "unrelated", "different body entirely")
    entries = mechanical.load_kb(kb)
    groups = mechanical.recurrence_groups(entries)
    assert groups == [["solutions/from-branch-a.md", "solutions/from-branch-b.md"]]


def test_recurrence_via_related_links(tmp_path):
    kb = make_kb(tmp_path)
    first = write_entry(kb, "solutions", "base", "retry with backoff")
    write_entry(kb, "conventions", "linked", "always use backoff jitter",
                related=[f"umbrella:{first}"])
    groups = mechanical.recurrence_groups(mechanical.load_kb(kb))
    assert groups == [["conventions/linked.md", "solutions/base.md"]]


def test_stale_candidates_x_90_days(tmp_path):
    kb = make_kb(tmp_path)
    old = (TODAY - timedelta(days=91)).isoformat()
    edge = (TODAY - timedelta(days=90)).isoformat()
    write_entry(kb, "solutions", "old", "old body", entry_date=old)
    write_entry(kb, "solutions", "edge", "edge body", entry_date=edge)
    write_entry(kb, "solutions", "appr", "approved body", status="approved",
                entry_date=old)
    entries = mechanical.load_kb(kb)
    assert mechanical.stale_candidates(entries, TODAY) == ["solutions/old.md"]


def test_pr_entry_counter_chunks_at_15():
    actions = [{"action": "consolidate", "entries": [f"e{i}-{j}" for j in range(4)]}
               for i in range(8)]  # 8 actions × 4 entries = 32
    chunks = mechanical.chunk_actions(actions)
    for chunk in chunks:
        assert sum(len(a["entries"]) for a in chunk) <= 15
    assert len(chunks) == 3


def test_pr_entry_counter_oversized_action_split_within_budget():
    actions = [{"action": "consolidate", "entries": [f"e{i}" for i in range(20)]}]
    chunks = mechanical.chunk_actions(actions)
    assert len(chunks) == 2  # 15 + 5, never one over-budget chunk
    assert [len(c[0]["entries"]) for c in chunks] == [15, 5]
    assert all(c[0]["oversized"] is True for c in chunks)


def test_report_includes_lint_and_chunks(tmp_path):
    kb = make_kb(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# rules\n")
    write_entry(kb, "solutions", "from-branch-a", "identical learning body")
    write_entry(kb, "solutions", "from-branch-b", "identical learning body")
    report = mechanical.build_report(kb, TODAY)
    assert report["lint"]["exit"] == 0
    assert report["chunks"] and report["chunks"][0][0]["action"] == "merge-duplicates"
    assert report["pr_entry_budget"] == 15


def test_cli_thresholds_exit_codes(tmp_path):
    kb = make_kb(tmp_path)
    quiet = subprocess.run([sys.executable, str(MECHANICAL), "thresholds",
                            "--kb-root", str(kb)], capture_output=True, text=True)
    assert quiet.returncode == 0
    assert json.loads(quiet.stdout)["triggered"] is False
    for i in range(26):
        write_entry(kb, "solutions", f"cand-{i}", f"body {i}", index=False)
    hot = subprocess.run([sys.executable, str(MECHANICAL), "thresholds",
                          "--kb-root", str(kb)], capture_output=True, text=True)
    assert hot.returncode == 4
    assert json.loads(hot.stdout)["triggered"] is True
    bad = subprocess.run([sys.executable, str(MECHANICAL), "thresholds",
                          "--kb-root", str(tmp_path)], capture_output=True, text=True)
    assert bad.returncode == 1 and "INDEX.md" in bad.stderr

def test_layout_of_resolves_both_layouts(tmp_path):
    """_layout_of must return the CONTRACT layout values; the hub branch was
    previously uncovered and silently returned a retired identifier."""
    project_kb = make_kb(tmp_path / "p", project_layout=True)
    hub_kb = make_kb(tmp_path / "h", project_layout=False)
    assert mechanical._layout_of(project_kb)[1] == "project"
    assert mechanical._layout_of(hub_kb)[1] == "hub"
    assert mechanical._layout_of(tmp_path / "nope") is None


def test_lint_pass_runs_on_hub_layout(tmp_path):
    """A hub-layout KB must lint without raising 'unknown layout'."""
    hub_kb = make_kb(tmp_path, project_layout=False)
    result = mechanical.lint_pass(hub_kb, TODAY)
    assert result is None or isinstance(result, (dict, list, tuple, str))
