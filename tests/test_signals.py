"""signals.py tests — corrections, errors, clusters, redaction, CLI."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIGNALS = REPO / "plugins/evc-learning/skills/retro/scripts/signals.py"

spec = importlib.util.spec_from_file_location("signals", SIGNALS)
signals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signals)


TRANSCRIPT = """user: please add the endpoint
assistant: done, added POST /users
user: no, that's wrong — I said PUT, not POST
assistant: fixing
Traceback (most recent call last):
AssertionError: expected 200 got 500
assistant: retrying
Traceback (most recent call last):
AssertionError: expected 200 got 500
assistant: retrying again
Traceback (most recent call last):
AssertionError: expected 200 got 500
user: don't do that, run the tests first
"""


def test_corrections_detected():
    report = signals.scan_transcript(TRANSCRIPT)
    corrections = [s for s in report["signals"] if s["type"] == "correction"]
    assert len(corrections) == 2
    assert any("that's wrong" in s["text"] for s in corrections)


def test_errors_and_repeat_cluster():
    report = signals.scan_transcript(TRANSCRIPT)
    assert report["counts"]["error"] >= 3
    clusters = [s for s in report["signals"] if s["type"] == "repeated-failure"]
    assert clusters and "seen 3x" in clusters[0]["text"]


def test_empty_transcript():
    report = signals.scan_transcript("")
    assert report == {"signals": [], "counts": {}}


def test_noisy_but_clean_transcript_no_false_corrections():
    text = "assistant: normally we retry\nuser: looks good, thanks\n"
    report = signals.scan_transcript(text)
    assert report["counts"].get("correction") is None


def test_signal_text_is_redacted():
    text = "user: no, that's wrong — the key is AKIAIOSFODNN7EXAMPLE\n"
    report = signals.scan_transcript(text)
    joined = json.dumps(report)
    assert "AKIAIOSFODNN7EXAMPLE" not in joined
    assert "[REDACTED:KB-SEC-002]" in joined


def test_cli_scan_and_missing_file(tmp_path):
    transcript = tmp_path / "t.txt"
    transcript.write_text(TRANSCRIPT)
    ok = subprocess.run([sys.executable, str(SIGNALS), "scan",
                         "--transcript", str(transcript)],
                        capture_output=True, text=True)
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["counts"]["correction"] == 2
    missing = subprocess.run([sys.executable, str(SIGNALS), "scan",
                              "--transcript", str(tmp_path / "nope.txt")],
                             capture_output=True, text=True)
    assert missing.returncode == 1
