"""kb-lint checks 1-6 as importable functions (CONTRACT.md is normative).

Severity model: 'fail' -> exit 2, 'warn' -> exit 1, clean -> exit 0.
Read-only by default; only run_all(write=True) mutates (last_verified).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from kblib import frontmatter, secret_rules

# Values below mirror CONTRACT.md §Tunables (the canonical record).
INDEX_MAX_LINES = 200
AGENTS_MAX_LINES = 150
METHODOLOGY_MAX_LINES = 150
GARDENING_OVERDUE_DAYS = 30
CANDIDATE_TRIGGER = 25

CATEGORIES = ("patterns", "conventions", "solutions", "anti-patterns", "glossary")
REQUIRED_KEYS = ("id", "status", "source", "date", "topic")
OPTIONAL_KEYS = ("refs", "last_verified", "related")
STATUS_VALUES = ("candidate", "approved", "deprecated")
SOURCE_VALUES = ("gate", "self-review", "retro", "human")
RELATED_KINDS = ("related", "umbrella", "contradiction")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[0-9a-f]{12}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
INDEX_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")
LOG_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")

# Dirs never scanned for AGENTS.md budgets (fixtures and VCS internals).
EXCLUDED_DIR_NAMES = {".git", "tests", "node_modules", "__pycache__"}


@dataclass(frozen=True)
class LintFinding:
    severity: str  # 'warn' | 'fail'
    check: str  # budget | schema | refs | orphan | gardening | secret
    path: str  # root-relative
    message: str


def kb_dir_for(root: Path, layout: str) -> Path:
    if layout == "hub":
        return root / "knowledge"
    if layout == "project":
        return root / "docs" / "knowledge"
    raise ValueError(f"unknown layout: {layout}")


def allowlist_path_for(root: Path, layout: str) -> Path:
    if layout == "hub":
        return root / "tools" / "allowlist.txt"
    return kb_dir_for(root, layout) / ".secret-allowlist"


def _rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def iter_entries(kb_dir: Path) -> list[Path]:
    """Entry files: *.md inside category dirs; README.md is not an entry."""
    entries: list[Path] = []
    for category in CATEGORIES:
        cat_dir = kb_dir / category
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.glob("*.md")):
            if path.name != "README.md":
                entries.append(path)
    return entries


def check_budgets(root: Path, layout: str) -> list[LintFinding]:
    findings: list[LintFinding] = []
    index = kb_dir_for(root, layout) / "INDEX.md"
    if index.is_file():
        n = len(index.read_text(encoding="utf-8").splitlines())
        if n >= INDEX_MAX_LINES:
            findings.append(
                LintFinding(
                    "fail",
                    "budget",
                    _rel(root, index),
                    f"INDEX.md has {n} lines (budget < {INDEX_MAX_LINES})",
                )
            )
    for agents in sorted(root.rglob("AGENTS.md")):
        if EXCLUDED_DIR_NAMES & set(agents.relative_to(root).parts):
            continue
        n = len(agents.read_text(encoding="utf-8").splitlines())
        if n >= AGENTS_MAX_LINES:
            findings.append(
                LintFinding(
                    "fail",
                    "budget",
                    _rel(root, agents),
                    f"AGENTS.md has {n} lines (budget < {AGENTS_MAX_LINES})",
                )
            )
    methodology = root / "methodology"
    if methodology.is_dir():
        for doc in sorted(methodology.glob("*.md")):
            n = len(doc.read_text(encoding="utf-8").splitlines())
            if n >= METHODOLOGY_MAX_LINES:
                findings.append(
                    LintFinding(
                        "fail",
                        "budget",
                        _rel(root, doc),
                        f"methodology file has {n} lines (budget < {METHODOLOGY_MAX_LINES})",
                    )
                )
    return findings


ParsedEntries = dict[Path, tuple[dict[str, str | list[str]], str]]

SCALAR_KEYS = ("id", "status", "source", "date", "topic", "last_verified")
LIST_KEYS = ("refs", "related")


def check_schema(
    root: Path, kb_dir: Path
) -> tuple[list[LintFinding], ParsedEntries, set[Path]]:
    """Returns (findings, parsed entries, entries with schema failures).

    Schema-failed entries stay in `parsed` (orphan/candidate accounting)
    but callers must never write to them.
    """
    findings: list[LintFinding] = []
    parsed: ParsedEntries = {}
    failed: set[Path] = set()

    def fail(rel: str, entry: Path, message: str) -> None:
        findings.append(LintFinding("fail", "schema", rel, message))
        failed.add(entry)

    for entry in iter_entries(kb_dir):
        rel = _rel(root, entry)
        try:
            fm, body = frontmatter.parse(entry.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            fail(rel, entry, "not valid UTF-8")
            continue
        except frontmatter.FrontmatterError as exc:
            failed.add(entry)
            findings.append(LintFinding("fail", "schema", rel, str(exc)))
            continue
        for key in REQUIRED_KEYS:
            if key not in fm:
                fail(rel, entry, f"missing key: {key}")
        for key in fm:
            if key not in REQUIRED_KEYS + OPTIONAL_KEYS:
                fail(rel, entry, f"unknown key: {key}")
        for key in SCALAR_KEYS:
            if key in fm and not isinstance(fm[key], str):
                fail(rel, entry, f"{key} must be a scalar")
        for key in LIST_KEYS:
            if key in fm and not isinstance(fm[key], list):
                fail(rel, entry, f"{key} must be a list")
        status = fm.get("status")
        if isinstance(status, str) and status not in STATUS_VALUES:
            fail(rel, entry, f"bad status: {status}")
        source = fm.get("source")
        if isinstance(source, str) and source not in SOURCE_VALUES:
            fail(rel, entry, f"bad source: {source}")
        for key in ("date", "last_verified"):
            value = fm.get(key)
            if isinstance(value, str) and not DATE_RE.match(value):
                fail(rel, entry, f"bad {key}: {value}")
        entry_id = fm.get("id")
        if isinstance(entry_id, str):
            if not ID_RE.match(entry_id):
                fail(rel, entry, f"bad id: {entry_id}")
            elif frontmatter.entry_id(body) != entry_id:
                fail(
                    rel,
                    entry,
                    f"id mismatch: frontmatter {entry_id}, body hashes to "
                    f"{frontmatter.entry_id(body)}",
                )
        related = fm.get("related")
        if isinstance(related, list):
            for item in related:
                kind, _, target = item.partition(":")
                if kind not in RELATED_KINDS or not target:
                    fail(rel, entry, f"bad related item: {item}")
        parsed[entry] = (fm, body)
    return findings, parsed, failed


def split_ref(item: str) -> tuple[str, str | None]:
    """CONTRACT refs grammar: split on the LAST @; non-hex tail means the
    whole item is a path containing @."""
    path, sep, tail = item.rpartition("@")
    if sep and COMMIT_RE.match(tail):
        return path, tail
    return item, None


def _ref_path_ok(path: str) -> bool:
    if not path or path.startswith("/") or path.startswith("./"):
        return False
    return ".." not in Path(path).parts and "\\" not in path


def check_refs(
    root: Path,
    parsed: ParsedEntries,
    write: bool,
    today: date,
    schema_failed: set[Path] = frozenset(),
) -> list[LintFinding]:
    findings: list[LintFinding] = []
    for entry, (fm, _body) in sorted(parsed.items()):
        if entry in schema_failed:
            continue  # already exit 2; never inspect or rewrite failed entries
        rel = _rel(root, entry)
        refs = fm.get("refs")
        if not isinstance(refs, list):
            continue
        malformed = False
        unresolved: list[str] = []
        for item in refs:
            path, _commit = split_ref(item)
            if not _ref_path_ok(path):
                findings.append(LintFinding("fail", "refs", rel, f"malformed ref: {item}"))
                malformed = True
                continue
            target = root / path
            if target.exists() and not target.resolve().is_relative_to(root):
                findings.append(
                    LintFinding(
                        "fail", "refs", rel, f"ref escapes repo root (symlink): {item}"
                    )
                )
                malformed = True
            elif not target.exists():
                unresolved.append(item)
        for item in unresolved:
            findings.append(
                LintFinding("warn", "refs", rel, f"stale entry: ref does not resolve: {item}")
            )
        if write and refs and not malformed and not unresolved:
            _set_last_verified(entry, today)
    return findings


def _set_last_verified(entry: Path, today: date) -> None:
    """Rewrite only the last_verified scalar; every other byte unchanged."""
    lines = entry.read_text(encoding="utf-8").split("\n")
    close = lines.index("---", 1)
    new_line = f"last_verified: {today.isoformat()}"
    for i in range(1, close):
        if lines[i].startswith("last_verified: "):
            lines[i] = new_line
            break
    else:
        lines.insert(close, new_line)
    entry.write_text("\n".join(lines), encoding="utf-8")


def check_orphans(root: Path, kb_dir: Path, parsed: ParsedEntries) -> list[LintFinding]:
    findings: list[LintFinding] = []
    index = kb_dir / "INDEX.md"
    index_text = index.read_text(encoding="utf-8") if index.is_file() else ""
    linked = set()
    for target in INDEX_LINK_RE.findall(index_text):
        first_part = target.split("/", 1)[0]
        if first_part not in CATEGORIES:
            continue
        linked.add(target)
        if not (kb_dir / target).is_file():
            findings.append(
                LintFinding(
                    "fail",
                    "orphan",
                    _rel(root, index),
                    f"INDEX links to missing file: {target}",
                )
            )
    for entry in parsed:
        rel_to_kb = str(entry.relative_to(kb_dir))
        if rel_to_kb not in linked:
            findings.append(
                LintFinding(
                    "warn",
                    "orphan",
                    _rel(root, entry),
                    "entry has no line in INDEX.md",
                )
            )
    return findings


def check_gardening(
    root: Path, kb_dir: Path, parsed: ParsedEntries, today: date
) -> list[LintFinding]:
    findings: list[LintFinding] = []
    log = kb_dir / ".gardening-log"
    log_rel = _rel(root, log) if kb_dir.is_dir() else str(log)
    if not log.is_file():
        findings.append(LintFinding("warn", "gardening", log_rel, "no gardening log"))
    else:
        valid_dates: list[date] = []
        for raw in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LOG_DATE_RE.match(raw)
            if not m:
                continue
            try:
                valid_dates.append(date.fromisoformat(m.group(1)))
            except ValueError:
                findings.append(
                    LintFinding(
                        "warn", "gardening", log_rel, f"malformed dated line: {raw!r}"
                    )
                )
        if not valid_dates:
            findings.append(
                LintFinding("warn", "gardening", log_rel, "gardening log has no dated lines")
            )
        else:
            days = (today - valid_dates[-1]).days
            if days > GARDENING_OVERDUE_DAYS:
                findings.append(
                    LintFinding(
                        "warn",
                        "gardening",
                        log_rel,
                        f"gardening overdue: last run {days} days ago "
                        f"(> {GARDENING_OVERDUE_DAYS})",
                    )
                )
    candidates = sum(
        1 for fm, _ in parsed.values() if fm.get("status") == "candidate"
    )
    if candidates > CANDIDATE_TRIGGER:
        findings.append(
            LintFinding(
                "warn",
                "gardening",
                log_rel,
                f"{candidates} candidate entries (> {CANDIDATE_TRIGGER}) — run distill",
            )
        )
    return findings


def check_secrets(
    root: Path, kb_dir: Path, allowlist: frozenset[str]
) -> list[LintFinding]:
    """Scan EVERY regular file under the KB dir (CONTRACT: the persistence
    gate covers the whole dir, not just entries). The local allowlist file
    itself is excluded; undecodable files are reported, never skipped
    silently."""
    findings: list[LintFinding] = []
    if not kb_dir.is_dir():
        return findings
    for path in sorted(kb_dir.rglob("*")):
        if not path.is_file() or path.name == ".secret-allowlist":
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                LintFinding(
                    "warn", "secret", _rel(root, path), "unscannable file (not UTF-8)"
                )
            )
            continue
        for f in secret_rules.scan_text(text, allowlist):
            findings.append(
                LintFinding(
                    "fail",
                    "secret",
                    _rel(root, path),
                    f"{f.rule_id} at line {f.line_no}",
                )
            )
    return findings


def run_all(
    root: Path,
    layout: str,
    write: bool = False,
    today: date | None = None,
) -> tuple[list[LintFinding], int]:
    """Run checks 1-6; returns (findings, exit code 0/1/2)."""
    today = today or date.today()
    root = root.resolve()
    kb_dir = kb_dir_for(root, layout)
    findings = check_budgets(root, layout)
    schema_findings, parsed, schema_failed = check_schema(root, kb_dir)
    findings += schema_findings
    findings += check_refs(root, parsed, write, today, schema_failed)
    findings += check_orphans(root, kb_dir, parsed)
    findings += check_gardening(root, kb_dir, parsed, today)
    allowlist = secret_rules.load_allowlist(allowlist_path_for(root, layout))
    findings += check_secrets(root, kb_dir, allowlist)
    findings.sort(key=lambda f: (f.path, f.check, f.message))
    if any(f.severity == "fail" for f in findings):
        return findings, 2
    if findings:
        return findings, 1
    return findings, 0
