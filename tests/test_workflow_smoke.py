"""Behavioral smoke: the run skill's learning-loop wiring, end to end.

Simulates the three gate outcomes exactly as SKILL.md prescribes (capture
CLI subprocess calls) against a temp project KB, then verifies the
wrap-up thresholds path switches to the distill branch (exit 4).
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from evclib import kb_checks

REPO = Path(__file__).resolve().parent.parent
NEW_ENTRY = REPO / "plugins/evc-learning/skills/capture/scripts/new_entry.py"
MECHANICAL = REPO / "plugins/evc-learning/skills/distill/scripts/mechanical.py"


def make_project(tmp_path: Path) -> Path:
    kb = tmp_path / "docs" / "knowledge"
    for cat in kb_checks.CATEGORIES:
        (kb / cat).mkdir(parents=True)
    (kb / "INDEX.md").write_text(
        "# Knowledge index\n\n## Patterns\n\n## Conventions\n\n"
        "## Solutions\n\n## Anti-patterns\n\n## Glossary\n"
    )
    (kb / ".gardening-log").write_text(f"{date.today().isoformat()} bootstrap\n")
    (tmp_path / "AGENTS.md").write_text("# rules\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.py").write_text("handler = None\n")
    return kb


def gate_capture(tmp_path: Path, kb: Path, outcome: str, topic: str, body: str):
    body_file = tmp_path / f"gate-{outcome}.md"
    body_file.write_text(body)
    result = subprocess.run(
        [sys.executable, str(NEW_ENTRY), "capture",
         "--kb-root", str(kb), "--topic", topic,
         "--outcome", outcome, "--source", "gate",
         "--ref", "src/api.py", "--body-file", str(body_file)],
        capture_output=True, text=True,
    )
    return result.returncode, json.loads(result.stdout) if result.stdout else None


def test_gate_events_write_routed_entries_then_thresholds_trigger(tmp_path):
    kb = make_project(tmp_path)

    code, out = gate_capture(tmp_path, kb, "approve", "staged handlers",
                             "Stage handlers behind explicit gates.")
    assert code == 0 and out["path"].startswith("solutions/")
    code, out = gate_capture(tmp_path, kb, "correct", "diff before approval",
                             "Always show the cumulative diff before asking approval.")
    assert code == 0 and out["path"].startswith("conventions/")
    code, out = gate_capture(tmp_path, kb, "decline", "silent auto-merge",
                             "Auto-merging on green CI was declined: gates need humans.")
    assert code == 0 and out["path"].startswith("anti-patterns/")

    # the whole simulated project passes kb-lint (entries + INDEX lines valid)
    findings, lint_code = kb_checks.run_all(tmp_path, "project")
    assert (findings, lint_code) == ([], 0)

    # wrap-up: quiet KB → exit 0 (no distill)
    quiet = subprocess.run([sys.executable, str(MECHANICAL), "thresholds",
                            "--kb-root", str(kb)], capture_output=True, text=True)
    assert quiet.returncode == 0

    # pile up candidates past the trigger → wrap-up must take the distill path
    for i in range(24):
        gate_capture(tmp_path, kb, "approve", f"lesson {i}",
                     f"Distinct lesson body number {i}.")
    hot = subprocess.run([sys.executable, str(MECHANICAL), "thresholds",
                          "--kb-root", str(kb)], capture_output=True, text=True)
    assert hot.returncode == 4
    payload = json.loads(hot.stdout)
    assert payload["triggered"] is True
    assert any("candidates" in r for r in payload["reasons"])


def test_gate_duplicate_and_refusal_paths(tmp_path):
    kb = make_project(tmp_path)
    code0, _ = gate_capture(tmp_path, kb, "approve", "same lesson", "One lesson.")
    code1, out = gate_capture(tmp_path, kb, "correct", "same lesson again", "One lesson.")
    assert (code0, code1) == (0, 10) and out["action"] == "noop"
    code2, out2 = gate_capture(tmp_path, kb, "approve", "leaky",
                               "token = sk_live_abcdef1234567890")
    assert code2 == 2 and out2["action"] == "refused"
