#!/usr/bin/env python3
"""distill mechanical pass — deterministic gardening groundwork (CONTRACT.md).

Subcommands:
  thresholds --kb-root PATH [--json]   (the CONTRACT CLI protocol)
      exit 0 = report produced, not triggered; 4 = thresholds hit (run
      distill); 1 = error. JSON: {"candidates", "index_lines",
      "index_budget", "index_pct", "days_since_gardening", "triggered",
      "reasons"}.
  report --kb-root PATH                (the distill skill's work order)
      lint summary + recurrence groups + stale candidates + action chunks,
      each chunk capped at PR_ENTRY_BUDGET entries (enforcement of the
      gardening PR size budget, not advisory).

Tunables mirror CONTRACT.md §Tunables (the canonical record):
candidates > 25, INDEX > 80% of its 200-line budget, gardening age > 30
days, stale-candidate expiry X = 90 days, PR size budget N = 15.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _find_evclib() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tools" / "evclib"
        if candidate.is_dir():
            return parent / "tools"
    raise SystemExit("mechanical.py: cannot locate tools/evclib")


sys.path.insert(0, str(_find_evclib()))

from evclib import frontmatter, kb_checks  # noqa: E402

CANDIDATE_TRIGGER = 25
INDEX_FILL_TRIGGER = 0.80
GARDENING_AGE_TRIGGER_DAYS = 30
STALE_CANDIDATE_DAYS = 90  # X
PR_ENTRY_BUDGET = 15  # N

LOG_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")


@dataclass
class Entry:
    path: str  # relative to kb_root
    fm: dict
    body: str


def load_kb(kb_root: Path) -> list[Entry]:
    entries = []
    for category in kb_checks.CATEGORIES:
        cat_dir = kb_root / category
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            try:
                fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
            except (frontmatter.FrontmatterError, UnicodeDecodeError):
                continue  # schema failures are kb-lint findings, not ours
            entries.append(Entry(str(path.relative_to(kb_root)), fm, body))
    return entries


def days_since_gardening(kb_root: Path, today: date) -> int | None:
    log = kb_root / ".gardening-log"
    if not log.is_file():
        return None
    valid: list[date] = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LOG_DATE_RE.match(line)
        if m:
            try:
                valid.append(date.fromisoformat(m.group(1)))
            except ValueError:
                continue
    return (today - valid[-1]).days if valid else None


def thresholds_data(kb_root: Path, today: date) -> dict:
    entries = load_kb(kb_root)
    candidates = sum(1 for e in entries if e.fm.get("status") == "candidate")
    index = kb_root / "INDEX.md"
    index_lines = len(index.read_text(encoding="utf-8").splitlines())
    index_budget = kb_checks.INDEX_MAX_LINES
    index_pct = round(index_lines / index_budget, 4)
    days = days_since_gardening(kb_root, today)
    reasons = []
    if candidates > CANDIDATE_TRIGGER:
        reasons.append(f"candidates {candidates} > {CANDIDATE_TRIGGER}")
    if index_pct > INDEX_FILL_TRIGGER:
        reasons.append(f"INDEX at {index_pct:.0%} of budget (> {INDEX_FILL_TRIGGER:.0%})")
    if days is not None and days > GARDENING_AGE_TRIGGER_DAYS:
        reasons.append(f"last gardening {days}d ago (> {GARDENING_AGE_TRIGGER_DAYS}d)")
    if days is None:
        # informational only — a missing log already warns in kb-lint
        reasons.append("gardening log missing or has no dated lines")
    return {
        "candidates": candidates,
        "index_lines": index_lines,
        "index_budget": index_budget,
        "index_pct": index_pct,
        "days_since_gardening": days,
        "triggered": (
            candidates > CANDIDATE_TRIGGER
            or index_pct > INDEX_FILL_TRIGGER
            or (days is not None and days > GARDENING_AGE_TRIGGER_DAYS)
        ),
        "reasons": reasons,
    }


def recurrence_groups(entries: list[Entry]) -> list[list[str]]:
    """Connected components over: identical id (concurrent duplicates from
    parallel branches) + related: links. Recurrence of a learning =
    component size, computed HERE at gardening time — never in-place."""
    index = {e.path: i for i, e in enumerate(entries)}
    parent = list(range(len(entries)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        parent[find(a)] = find(b)

    by_id: dict[str, int] = {}
    for i, e in enumerate(entries):
        eid = e.fm.get("id")
        if isinstance(eid, str):
            if eid in by_id:
                union(i, by_id[eid])
            else:
                by_id[eid] = i
        related = e.fm.get("related")
        if isinstance(related, list):
            for item in related:
                _kind, _, target = item.partition(":")
                if target in index:
                    union(i, index[target])
    groups: dict[int, list[str]] = {}
    for i, e in enumerate(entries):
        groups.setdefault(find(i), []).append(e.path)
    return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=len,
                  reverse=True)


def stale_candidates(entries: list[Entry], today: date) -> list[str]:
    stale = []
    for e in entries:
        if e.fm.get("status") != "candidate":
            continue
        raw = e.fm.get("date")
        if not isinstance(raw, str):
            continue
        try:
            captured = date.fromisoformat(raw)
        except ValueError:
            continue
        if (today - captured).days > STALE_CANDIDATE_DAYS:
            stale.append(e.path)
    return sorted(stale)


def chunk_actions(actions: list[dict]) -> list[list[dict]]:
    """Greedy-pack actions into PR chunks of <= PR_ENTRY_BUDGET entries.
    An action larger than the budget becomes its own chunk marked
    oversized (the skill must split it semantically)."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_size = 0
    for action in actions:
        size = len(action["entries"])
        if size > PR_ENTRY_BUDGET:
            action = {**action, "oversized": True}
            chunks.append([action])
            continue
        if current_size + size > PR_ENTRY_BUDGET and current:
            chunks.append(current)
            current, current_size = [], 0
        current.append(action)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def _layout_of(kb_root: Path) -> tuple[Path, str] | None:
    """Derive (repo root, layout) from the CONTRACT kb-root mapping."""
    resolved = kb_root.resolve()
    if resolved.name == "knowledge" and resolved.parent.name == "docs":
        return resolved.parent.parent, "project"
    if resolved.name == "knowledge":
        return resolved.parent, "evc"
    return None


def lint_pass(kb_root: Path, today: date) -> dict:
    """Lint-first: the gardener starts from kb-lint's read-only verdict."""
    derived = _layout_of(kb_root)
    if derived is None:
        return {"exit": None, "findings": [],
                "note": "kb-root matches no CONTRACT layout; run kb-lint manually"}
    root, layout = derived
    findings, exit_code = kb_checks.run_all(root, layout, today=today)
    return {
        "exit": exit_code,
        "findings": [
            {"severity": f.severity, "check": f.check, "path": f.path,
             "message": f.message}
            for f in findings
        ],
    }


def build_report(kb_root: Path, today: date) -> dict:
    entries = load_kb(kb_root)
    groups = recurrence_groups(entries)
    stale = stale_candidates(entries, today)
    actions: list[dict] = []
    for group in groups:
        candidates_in_group = [
            p for p in group
            for e in entries if e.path == p and e.fm.get("status") == "candidate"
        ]
        kind = "merge-duplicates" if _same_id_group(entries, group) else "consolidate"
        actions.append(
            {"action": kind, "entries": group,
             "recurrence": len(group),
             "promote_eligible": len(candidates_in_group) >= 2}
        )
    if stale:
        actions.append({"action": "tombstone-stale", "entries": stale})
    return {
        "lint": lint_pass(kb_root, today),
        "thresholds": thresholds_data(kb_root, today),
        "recurrence_groups": groups,
        "stale_candidates": stale,
        "pr_entry_budget": PR_ENTRY_BUDGET,
        "chunks": chunk_actions(actions),
    }


def _same_id_group(entries: list[Entry], group: list[str]) -> bool:
    ids = {e.fm.get("id") for e in entries if e.path in group}
    return len(ids) == 1


def _kb_root_or_die(raw: str) -> Path:
    kb_root = Path(raw)
    if not (kb_root / "INDEX.md").is_file():
        print(f"mechanical.py: --kb-root {kb_root} is not a KB dir (no INDEX.md)",
              file=sys.stderr)
        raise SystemExit(1)
    return kb_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mechanical.py", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    for name in ("thresholds", "report"):
        p = sub.add_parser(name)
        p.add_argument("--kb-root", required=True)
        p.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)
    if args.command not in ("thresholds", "report"):
        print("mechanical.py: command must be thresholds or report", file=sys.stderr)
        return 1
    kb_root = _kb_root_or_die(args.kb_root)
    today = date.today()
    if args.command == "thresholds":
        data = thresholds_data(kb_root, today)
        print(json.dumps(data))
        return 4 if data["triggered"] else 0
    print(json.dumps(build_report(kb_root, today)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
