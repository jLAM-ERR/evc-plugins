"""Deterministic secret/PII scan — the normative ruleset (CONTRACT.md).

Rule IDs are contract-fixed: removing or renaming one is a MAJOR contract
bump; adding one is MINOR. No network, no external deps, by design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    rule_id: str
    matched_text: str
    line_no: int


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# (rule_id, compiled regex); EVC-SEC-005 additionally requires Luhn validity.
RULES: list[tuple[str, re.Pattern[str]]] = [
    ("EVC-SEC-001", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("EVC-SEC-002", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "EVC-SEC-003",
        re.compile(
            r"(?i)[a-z0-9_]*(?:api[_-]?key|secret|token|password|passwd|credential)"
            r"[a-z0-9_]*\s*[:=]\s*"
            r"(?:'[^']{6,}'|\"[^\"]{6,}\"|[A-Za-z0-9_\-/+=.]{8,})"
        ),
    ),
    (
        "EVC-SEC-004",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
            r"|(?i:\bBearer\s+[A-Za-z0-9_\-.=+/]{16,})"
        ),
    ),
    ("EVC-SEC-005", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("EVC-SEC-006", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("EVC-PII-001", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def load_allowlist(path: Path | None) -> frozenset[str]:
    """One literal string per line; `#` comments; missing file → empty."""
    if path is None or not path.is_file():
        return frozenset()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return frozenset(entries)


def scan_text(text: str, allowlist: frozenset[str] = frozenset()) -> list[Finding]:
    """Scan text with every rule; a finding is suppressed iff its exact
    matched text is an allowlist entry."""
    findings: list[Finding] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        for rule_id, pattern in RULES:
            for m in pattern.finditer(line):
                matched = m.group(0)
                if rule_id == "EVC-SEC-005":
                    digits = re.sub(r"[ -]", "", matched)
                    if not (13 <= len(digits) <= 19 and _luhn_valid(digits)):
                        continue
                if matched in allowlist:
                    continue
                findings.append(Finding(rule_id, matched, line_no))
    return findings
