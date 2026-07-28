#!/usr/bin/env python3
"""retro pre-pass — deterministic transcript signal extraction.

signals.py scan --transcript FILE [--json]

Greps a session transcript for the cheap, high-yield retro signals BEFORE
any LLM is involved (explicit user correction is the dominant signal in the
literature; errors and retry clusters follow). Output: one JSON object
{"signals": [{"type": "correction"|"error"|"repeated-failure",
"line_no": int, "text": str}, ...], "counts": {...}}.

Signal text is secret-scanned (kblib rules) and redacted, so the pre-pass
output can be safely handed to analyst subagents.

Exit codes: 0 report produced (even if empty) / 1 error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def _find_kblib() -> Path:
    for parent in Path(__file__).resolve().parents:
        for rel in ("lib", "tools"):
            candidate = parent / rel / "kblib"
            if candidate.is_dir():
                return parent / rel
    raise SystemExit("signals.py: cannot locate tools/kblib")


sys.path.insert(0, str(_find_kblib()))

from kblib import secret_rules  # noqa: E402

CORRECTION_RES = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^no[,.]",
        r"\bthat'?s (wrong|not right|incorrect)\b",
        r"\bnot what i (asked|meant|wanted)\b",
        r"\bi (already )?said\b",
        r"\bdon'?t do (that|this)\b",
        r"\byou (did it|got it) wrong\b",
        r"\bwrong again\b",
        r"\bredo (it|this)\b",
        r"\binstead of what you did\b",
        r"\bstop doing\b",
    )
]
ERROR_RES = [
    re.compile(p)
    for p in (
        r"\bTraceback \(most recent call last\)",
        r"\bAssertionError\b",
        r"^E\s{3,}",
        r"\bFAILED\b",
        r"(?i)\berror:",
        r"\bexit code [1-9]\d*\b",
        r"\bexited 1\b",
    )
]
MAX_TEXT = 200
REPEAT_THRESHOLD = 2  # same error line seen more than this → retry cluster


def redact(text: str) -> str:
    for finding in secret_rules.scan_text(text):
        text = text.replace(finding.matched_text, f"[REDACTED:{finding.rule_id}]")
    return text


def scan_transcript(text: str) -> dict:
    signals: list[dict] = []
    error_lines: Counter[str] = Counter()
    for line_no, raw in enumerate(text.split("\n"), start=1):
        line = raw.strip()
        if not line:
            continue
        if any(r.search(line) for r in CORRECTION_RES):
            signals.append(
                {"type": "correction", "line_no": line_no,
                 "text": redact(line[:MAX_TEXT])}
            )
        elif any(r.search(line) for r in ERROR_RES):
            error_lines[line[:MAX_TEXT]] += 1
            signals.append(
                {"type": "error", "line_no": line_no,
                 "text": redact(line[:MAX_TEXT])}
            )
    for text_key, count in sorted(error_lines.items()):
        if count > REPEAT_THRESHOLD:
            signals.append(
                {
                    "type": "repeated-failure",
                    "line_no": 0,
                    "text": redact(f"seen {count}x: {text_key}"),
                }
            )
    counts = Counter(s["type"] for s in signals)
    return {"signals": signals, "counts": dict(sorted(counts.items()))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signals.py", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan")
    scan.add_argument("--transcript", required=True, type=Path)
    scan.add_argument("--json", action="store_true", default=True)
    args = parser.parse_args(argv)
    if args.command != "scan":
        print("signals.py: the only command is: scan", file=sys.stderr)
        return 1
    if not args.transcript.is_file():
        print(f"signals.py: transcript not found: {args.transcript}", file=sys.stderr)
        return 1
    text = args.transcript.read_text(encoding="utf-8", errors="replace")
    print(json.dumps(scan_transcript(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
