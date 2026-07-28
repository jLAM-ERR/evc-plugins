"""capture CLI tests — routing, hashing, NOOP, arbitration, secret gate."""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from kblib import frontmatter, kb_checks

REPO = Path(__file__).resolve().parent.parent
NEW_ENTRY = REPO / "plugins/autodidact-learning/skills/capture/scripts/new_entry.py"

spec = importlib.util.spec_from_file_location("new_entry", NEW_ENTRY)
new_entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(new_entry)


def make_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "docs" / "knowledge"
    for cat in kb_checks.CATEGORIES:
        (kb / cat).mkdir(parents=True)
    (kb / "INDEX.md").write_text(
        "# Knowledge index\n\n## Patterns\n\n## Conventions\n\n"
        "## Solutions\n\n## Anti-patterns\n\n## Glossary\n"
    )
    (kb / ".gardening-log").write_text(f"{date.today().isoformat()} bootstrap\n")
    return kb


def run_capture(tmp_path: Path, kb: Path, body: str, **over):
    body_file = tmp_path / "body.md"
    body_file.write_text(body)
    argv = {
        "kb_root": str(kb),
        "topic": over.pop("topic", "retry timeout handling"),
        "outcome": over.pop("outcome", "approve"),
        "source": over.pop("source", "gate"),
        "ref": over.pop("ref", None),
        "related": over.pop("related", None),
        "hook": over.pop("hook", None),
        "body_file": str(body_file),
    }
    assert not over, over
    args = type("Args", (), argv)()
    return new_entry.capture(args, today=date(2026, 7, 23))


@pytest.mark.parametrize(
    "outcome,category",
    [("approve", "solutions"), ("correct", "conventions"), ("decline", "anti-patterns")],
)
def test_routing_and_valid_entry(tmp_path, outcome, category):
    kb = make_kb(tmp_path)
    result, code = run_capture(tmp_path, kb, "Always cap retries at three.",
                               outcome=outcome)
    assert code == 0 and result["action"] == "written"
    written = kb / result["path"]
    assert written.parent.name == category
    fm, body = frontmatter.parse(written.read_text())
    assert fm["status"] == "candidate"
    assert fm["id"] == frontmatter.entry_id(body) == result["id"]
    # INDEX got exactly one line for it
    assert written.name in (kb / "INDEX.md").read_text()


def test_full_kb_lint_passes_after_capture(tmp_path):
    kb = make_kb(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    run_capture(tmp_path, kb, "Cap retries at three.", ref=["src/app.py"])
    findings, code = kb_checks.run_all(tmp_path, "project", today=date.today())
    assert (findings, code) == ([], 0)


def test_hash_stability_known_digest(tmp_path):
    kb = make_kb(tmp_path)
    result, _ = run_capture(tmp_path, kb, "hello world")
    assert result["id"] == "b94d27b9934d"


def test_source_human_accepted(tmp_path):
    kb = make_kb(tmp_path)
    result, code = run_capture(tmp_path, kb, "Filed by a human directly.",
                               source="human")
    assert code == 0
    assert "source: human" in (kb / result["path"]).read_text()


def test_duplicate_noop(tmp_path):
    kb = make_kb(tmp_path)
    first, code0 = run_capture(tmp_path, kb, "Same learning body.")
    second, code1 = run_capture(tmp_path, kb, "Same learning body.\n",
                                topic="different topic", outcome="decline")
    assert code1 == 10 and second["action"] == "noop"
    assert second["path"] == first["path"]
    assert not list((kb / "anti-patterns").glob("*.md"))


def test_similar_report_related(tmp_path):
    kb = make_kb(tmp_path)
    run_capture(tmp_path, kb, "Payments retries need exponential backoff.",
                topic="payments retries backoff")
    result, code = run_capture(
        tmp_path, kb, "Payments backoff must include jitter for retries.",
        topic="payments retries jitter", outcome="correct")
    assert code == 0
    assert any(r["kind"] in ("related", "umbrella") for r in result["related"])
    written = kb / result["path"]
    assert "related:" in written.read_text()


def test_contradiction_flag_heuristic_and_explicit(tmp_path):
    kb = make_kb(tmp_path)
    first, _ = run_capture(tmp_path, kb, "Payments retries use exponential backoff.",
                           topic="payments retries backoff")
    result, _ = run_capture(
        tmp_path, kb,
        "Never retry payments calls; backoff retries duplicate charges.",
        topic="payments retries forbidden", outcome="decline")
    assert {"kind": "contradiction", "entry": first["path"]} in result["related"]
    explicit, _ = run_capture(
        tmp_path, kb, "Unrelated body about deployment windows.",
        topic="deploy windows", related=[f"contradiction:{first['path']}"])
    assert {"kind": "contradiction", "entry": first["path"]} in explicit["related"]


def test_secret_refusal(tmp_path):
    kb = make_kb(tmp_path)
    result, code = run_capture(tmp_path, kb, "creds AKIAIOSFODNN7EXAMPLE here")
    assert code == 2 and result["action"] == "refused"
    assert "KB-SEC-002" in result["findings"]
    assert not list((kb / "solutions").glob("*.md"))


def test_allowlist_suppresses_refusal(tmp_path):
    kb = make_kb(tmp_path)
    (kb / ".secret-allowlist").write_text("someone@example.com\n")
    result, code = run_capture(tmp_path, kb, "contact someone@example.com for access")
    assert code == 0 and result["action"] == "written"


def test_filename_collision_appends_suffix(tmp_path):
    kb = make_kb(tmp_path)
    r1, _ = run_capture(tmp_path, kb, "First body.", topic="same topic")
    r2, _ = run_capture(tmp_path, kb, "Second body, different.", topic="same topic")
    assert r1["path"] != r2["path"]
    assert r2["path"].endswith("-2.md")


# --- CLI process-level ----------------------------------------------------


def cli(*args: str):
    return subprocess.run([sys.executable, str(NEW_ENTRY), *args],
                          capture_output=True, text=True)


def test_cli_written_and_json(tmp_path):
    kb = make_kb(tmp_path)
    body = tmp_path / "b.md"
    body.write_text("Cap retries at three.")
    result = cli("capture", "--kb-root", str(kb), "--topic", "retries",
                 "--outcome", "approve", "--source", "gate",
                 "--body-file", str(body))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["action"] == "written"


def test_cli_usage_errors_exit_1(tmp_path):
    kb = make_kb(tmp_path)
    body = tmp_path / "b.md"
    body.write_text("x")
    bad_outcome = cli("capture", "--kb-root", str(kb), "--topic", "t",
                      "--outcome", "maybe", "--source", "gate",
                      "--body-file", str(body))
    assert bad_outcome.returncode == 1 and bad_outcome.stdout == ""
    missing_arg = cli("capture", "--kb-root", str(kb))
    assert missing_arg.returncode == 1
    not_a_kb = cli("capture", "--kb-root", str(tmp_path), "--topic", "t",
                   "--outcome", "approve", "--source", "gate",
                   "--body-file", str(body))
    assert not_a_kb.returncode == 1
    assert "INDEX.md" in not_a_kb.stderr
