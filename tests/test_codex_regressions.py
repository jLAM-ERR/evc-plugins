"""Regressions from the Codex adversarial review of the autodidact-learning plugin:
install-shape self-containment, full-persist secret scan, concurrent
capture safety, chunk budget enforcement."""

import filecmp
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins/autodidact-learning"
NEW_ENTRY_REL = "skills/capture/scripts/new_entry.py"


def make_kb(base: Path) -> Path:
    kb = base / "docs" / "knowledge"
    for cat in ("patterns", "conventions", "solutions", "anti-patterns", "glossary"):
        (kb / cat).mkdir(parents=True)
    (kb / "INDEX.md").write_text(
        "# Knowledge index\n\n## Patterns\n\n## Conventions\n\n"
        "## Solutions\n\n## Anti-patterns\n\n## Glossary\n"
    )
    (kb / ".gardening-log").write_text(f"{date.today().isoformat()} bootstrap\n")
    return kb


def test_vendored_lib_byte_identical_to_tools():
    tools = REPO / "tools/kblib"
    lib = PLUGIN / "lib/kblib"
    for name in ("__init__.py", "frontmatter.py", "kb_checks.py", "secret_rules.py"):
        assert filecmp.cmp(tools / name, lib / name, shallow=False), name


def test_install_shape_plugin_is_self_contained(tmp_path):
    """Copy ONLY the plugin dir (installed shape — no repo tools/) and run
    all three CLIs from there."""
    plug = tmp_path / "cache" / "autodidact-learning"
    shutil.copytree(PLUGIN, plug)
    kb = make_kb(tmp_path / "project")
    body = tmp_path / "b.md"
    body.write_text("Installed-shape capture works.")
    cap = subprocess.run(
        [sys.executable, str(plug / NEW_ENTRY_REL), "capture",
         "--kb-root", str(kb), "--topic", "install shape",
         "--outcome", "approve", "--source", "gate", "--body-file", str(body)],
        capture_output=True, text=True)
    assert cap.returncode == 0, cap.stderr
    transcript = tmp_path / "t.txt"
    transcript.write_text("user: no, that's wrong\n")
    sig = subprocess.run(
        [sys.executable, str(plug / "skills/retro/scripts/signals.py"),
         "scan", "--transcript", str(transcript)],
        capture_output=True, text=True)
    assert sig.returncode == 0, sig.stderr
    mech = subprocess.run(
        [sys.executable, str(plug / "skills/distill/scripts/mechanical.py"),
         "thresholds", "--kb-root", str(kb)],
        capture_output=True, text=True)
    assert mech.returncode in (0, 4), mech.stderr


def _capture(kb: Path, body_file: Path, topic: str, extra=()):
    return subprocess.run(
        [sys.executable, str(PLUGIN / NEW_ENTRY_REL), "capture",
         "--kb-root", str(kb), "--topic", topic,
         "--outcome", "approve", "--source", "gate",
         "--body-file", str(body_file), *extra],
        capture_output=True, text=True)


def test_secret_in_hook_refused_before_write(tmp_path):
    kb = make_kb(tmp_path)
    body = tmp_path / "b.md"
    body.write_text("Clean body.")
    result = _capture(kb, body, "clean topic",
                      ("--hook", "creds AKIAIOSFODNN7EXAMPLE"))
    assert result.returncode == 2
    assert json.loads(result.stdout)["action"] == "refused"
    assert not list((kb / "solutions").glob("*.md"))
    assert "AKIA" not in (kb / "INDEX.md").read_text()


def test_secret_in_ref_refused_before_write(tmp_path):
    kb = make_kb(tmp_path)
    body = tmp_path / "b.md"
    body.write_text("Clean body.")
    result = _capture(kb, body, "clean topic",
                      ("--ref", "password = supersecret99 x"))
    assert result.returncode == 2
    assert not list((kb / "solutions").glob("*.md"))


def test_parallel_captures_lose_nothing(tmp_path):
    kb = make_kb(tmp_path)
    bodies = []
    for i in range(5):
        f = tmp_path / f"b{i}.md"
        f.write_text(f"Distinct concurrent lesson {i}.")
        bodies.append(f)
    procs = [
        subprocess.Popen(
            [sys.executable, str(PLUGIN / NEW_ENTRY_REL), "capture",
             "--kb-root", str(kb), "--topic", "same topic",
             "--outcome", "approve", "--source", "gate",
             "--body-file", str(f)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for f in bodies
    ]
    assert all(p.wait() == 0 for p in procs)
    written = sorted((kb / "solutions").glob("*.md"))
    assert len(written) == 5  # atomic claims: no overwrites
    index_text = (kb / "INDEX.md").read_text()
    for path in written:
        assert path.name in index_text  # lock: no dropped INDEX lines
    assert not (kb / ".index.lock").exists()


def test_no_chunk_ever_exceeds_budget():
    sys.path.insert(0, str(PLUGIN / "skills/distill/scripts"))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "mech2", PLUGIN / "skills/distill/scripts/mechanical.py")
    mech = importlib.util.module_from_spec(spec)
    sys.modules["mech2"] = mech
    spec.loader.exec_module(mech)
    actions = [{"action": "consolidate", "entries": [f"e{i}" for i in range(38)]}]
    chunks = mech.chunk_actions(actions)
    sizes = [sum(len(a["entries"]) for a in c) for c in chunks]
    assert all(s <= 15 for s in sizes)
    assert sum(s for s in sizes) == 38  # nothing dropped
    assert all(a.get("oversized") for c in chunks for a in c)
