#!/usr/bin/env python3
"""capture CLI — append-only knowledge entry creation (CONTRACT.md).

new_entry.py capture --kb-root PATH --topic TOPIC
    --outcome approve|correct|decline --source gate|self-review|retro
    [--ref PATH[@SHA]]... [--related kind:category/file.md]...
    [--hook TEXT] --body-file F

Exit codes: 0 written / 10 NOOP (exact duplicate) / 2 refused (secret
findings) / 1 usage or validation error. JSON on stdout for 0/10/2.

Rules implemented here (normative text in CONTRACT.md):
- routing: approve -> solutions/, correct -> conventions/,
  decline -> anti-patterns/;
- append-only: existing entries are NEVER modified; arbitration only
  CLASSIFIES (duplicate -> NOOP; similar -> related report on the NEW
  entry). Kind heuristics are deterministic best-effort; the gardener
  re-judges at distill time;
- secret scan (project profile: <kb-root>/.secret-allowlist) refuses the
  write on any finding;
- the new entry also gets its one INDEX.md line (skipped if INDEX.md is
  absent -- kb-lint will flag the orphan).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path


def _find_kblib() -> Path:
    for parent in Path(__file__).resolve().parents:
        for rel in ("lib", "tools"):
            candidate = parent / rel / "kblib"
            if candidate.is_dir():
                return parent / rel
    raise SystemExit("new_entry.py: cannot locate tools/kblib (repo layout broken)")


sys.path.insert(0, str(_find_kblib()))

from kblib import frontmatter, secret_rules  # noqa: E402

ROUTING = {
    "approve": "solutions",
    "correct": "conventions",
    "decline": "anti-patterns",
}
SOURCES = ("gate", "self-review", "retro", "human")
RELATED_KINDS = ("related", "umbrella", "contradiction")
CATEGORIES = ("patterns", "conventions", "solutions", "anti-patterns", "glossary")
SECTION_FOR = {
    "patterns": "## Patterns",
    "conventions": "## Conventions",
    "solutions": "## Solutions",
    "anti-patterns": "## Anti-patterns",
    "glossary": "## Glossary",
}
STOPWORDS = frozenset(
    "the a an and or for with into from this that when what where how not "
    "never avoid dont use using are is was were will would should".split()
)
NEGATIONS = ("not ", "never ", "avoid ", "don't ", "do not ", "must not ")


class CaptureError(Exception):
    """Usage/validation error -> exit 1, message on stderr."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # CONTRACT: usage errors exit 1, not 2
        raise CaptureError(message)


def slugify(topic: str) -> str:
    text = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:50].rstrip("-") or "entry"


def terms_of(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]{4,}", text.lower())
    return frozenset(w for w in words if w not in STOPWORDS)


def _has_negation(text: str) -> bool:
    lowered = text.lower()
    return any(n in lowered for n in NEGATIONS)


def iter_kb_entries(kb_root: Path):
    for category in CATEGORIES:
        cat_dir = kb_root / category
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            try:
                fm, body = frontmatter.parse(path.read_text(encoding="utf-8"))
            except (frontmatter.FrontmatterError, UnicodeDecodeError):
                continue  # unparseable entries are kb-lint's problem
            yield path, fm, body


def classify_similar(
    kb_root: Path, topic: str, body: str
) -> list[dict[str, str]]:
    """Deterministic term-overlap search over the full KB; >=2 shared terms
    makes a hit. Kind: contradiction if exactly one side carries a negation
    marker; umbrella if the existing entry contains every topic term and
    has the longer body; else related."""
    new_terms = terms_of(topic + " " + body)
    topic_terms = terms_of(topic)
    hits = []
    for path, fm, existing_body in iter_kb_entries(kb_root):
        existing_text = str(fm.get("topic", "")) + " " + existing_body
        existing_terms = terms_of(existing_text)
        shared = new_terms & existing_terms
        if len(shared) < 2:
            continue
        if _has_negation(body) != _has_negation(existing_body):
            kind = "contradiction"
        elif topic_terms and topic_terms <= existing_terms and len(
            existing_body
        ) > len(body):
            kind = "umbrella"
        else:
            kind = "related"
        hits.append({"kind": kind, "entry": str(path.relative_to(kb_root))})
    return hits


def find_duplicate(kb_root: Path, entry_id: str) -> Path | None:
    for path, fm, _body in iter_kb_entries(kb_root):
        if fm.get("id") == entry_id:
            return path
    return None


def claim_entry_file(cat_dir: Path, today: date, slug: str) -> tuple[Path, int]:
    """Atomically claim a free filename (O_CREAT|O_EXCL) so concurrent
    captures with the same slug can never overwrite each other."""
    base = f"{today.strftime('%Y%m%d')}-{slug}"
    n = 1
    while True:
        name = f"{base}.md" if n == 1 else f"{base}-{n}.md"
        path = cat_dir / name
        try:
            return path, os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            n += 1


def build_entry(
    entry_id: str,
    source: str,
    today: date,
    topic: str,
    body: str,
    refs: list[str],
    related: list[dict[str, str]],
) -> str:
    lines = [
        "---",
        f"id: {entry_id}",
        "status: candidate",
        f"source: {source}",
        f"date: {today.isoformat()}",
        f"topic: {topic}",
    ]
    if refs:
        lines.append("refs:")
        lines += [f"  - {r}" for r in refs]
    if related:
        lines.append("related:")
        lines += [f"  - {r['kind']}:{r['entry']}" for r in related]
    lines += ["---", "", frontmatter.normalize_body(body), ""]
    return "\n".join(lines)


LOCK_RETRIES = 100
LOCK_DELAY_SECONDS = 0.05
LOCK_STALE_SECONDS = 60


def _acquire_index_lock(kb_root: Path) -> int | None:
    lock = kb_root / ".index.lock"
    for _ in range(LOCK_RETRIES):
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_SECONDS:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            time.sleep(LOCK_DELAY_SECONDS)
    return None


def add_index_line(
    kb_root: Path, category: str, filename: str, topic: str, hook: str
) -> bool:
    """Insert the entry's INDEX line under a lockfile: re-read inside the
    lock (so concurrent captures never drop each other's lines) and land
    the result with an atomic replace. Returns False (caller warns) if the
    lock cannot be acquired — the entry then surfaces as a kb-lint orphan
    rather than corrupting the index."""
    index = kb_root / "INDEX.md"
    if not index.is_file():
        return True
    lock_fd = _acquire_index_lock(kb_root)
    if lock_fd is None:
        return False
    try:
        entry_line = f"- [{topic}]({category}/{filename}) — {hook}"
        lines = index.read_text(encoding="utf-8").split("\n")
        heading = SECTION_FOR[category]
        try:
            start = lines.index(heading)
        except ValueError:
            lines += ["", heading, "", entry_line]
        else:
            end = len(lines)
            for i in range(start + 1, len(lines)):
                if lines[i].startswith("## "):
                    end = i
                    break
            insert_at = end
            while insert_at > start + 1 and lines[insert_at - 1].strip() == "":
                insert_at -= 1
            lines.insert(insert_at, entry_line)
        tmp = kb_root / f".INDEX.md.tmp-{os.getpid()}"
        tmp.write_text("\n".join(lines), encoding="utf-8")
        os.replace(tmp, index)
        return True
    finally:
        os.close(lock_fd)
        (kb_root / ".index.lock").unlink(missing_ok=True)


def capture(args, today: date | None = None) -> tuple[dict, int]:
    today = today or date.today()
    kb_root = Path(args.kb_root)
    if not (kb_root / "INDEX.md").is_file():
        raise CaptureError(f"--kb-root {kb_root} is not a KB dir (no INDEX.md)")
    if args.outcome not in ROUTING:
        raise CaptureError(f"--outcome must be one of {sorted(ROUTING)}")
    if args.source not in SOURCES:
        raise CaptureError(f"--source must be one of {SOURCES}")
    body_file = Path(args.body_file)
    if not body_file.is_file():
        raise CaptureError(f"--body-file {body_file} not found")
    body = body_file.read_text(encoding="utf-8")
    if not frontmatter.normalize_body(body):
        raise CaptureError("--body-file is empty after normalization")
    explicit_related = []
    for item in args.related or []:
        kind, _, target = item.partition(":")
        if kind not in RELATED_KINDS or not target:
            raise CaptureError(f"--related must be kind:category/file.md, got {item!r}")
        explicit_related.append({"kind": kind, "entry": target})

    entry_id = frontmatter.entry_id(body)
    related = explicit_related + [
        hit
        for hit in classify_similar(kb_root, args.topic, body)
        if hit["entry"] not in {r["entry"] for r in explicit_related}
    ]
    hook = args.hook or f"captured from {args.source} ({args.outcome})"
    entry_text = build_entry(entry_id, args.source, today, args.topic, body,
                             args.ref or [], related)

    # secret gate (project profile) — scan the EXACT bytes that will be
    # persisted (entry frontmatter incl. refs/related, body, and the INDEX
    # hook text); refuse before any filesystem write
    allowlist = secret_rules.load_allowlist(kb_root / ".secret-allowlist")
    findings = secret_rules.scan_text(entry_text + "\n" + hook, allowlist)
    if findings:
        return (
            {
                "action": "refused",
                "path": None,
                "id": entry_id,
                "related": [],
                "findings": sorted({f.rule_id for f in findings}),
            },
            2,
        )

    # exact duplicate anywhere in the KB → NOOP
    duplicate = find_duplicate(kb_root, entry_id)
    if duplicate is not None:
        return (
            {
                "action": "noop",
                "path": str(duplicate.relative_to(kb_root)),
                "id": entry_id,
                "related": [],
                "findings": [],
            },
            10,
        )

    category = ROUTING[args.outcome]
    cat_dir = kb_root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    target, fd = claim_entry_file(cat_dir, today, slugify(args.topic))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(entry_text)
    if not add_index_line(kb_root, category, target.name, args.topic, hook):
        print(
            f"new_entry.py: WARNING index lock timeout — {target.name} written "
            "without an INDEX line (kb-lint will flag the orphan)",
            file=sys.stderr,
        )
    return (
        {
            "action": "written",
            "path": str(target.relative_to(kb_root)),
            "id": entry_id,
            "related": related,
            "findings": [],
        },
        0,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="new_entry.py", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    cap = sub.add_parser("capture")
    cap.add_argument("--kb-root", required=True)
    cap.add_argument("--topic", required=True)
    cap.add_argument("--outcome", required=True)
    cap.add_argument("--source", required=True)
    cap.add_argument("--ref", action="append")
    cap.add_argument("--related", action="append")
    cap.add_argument("--hook")
    cap.add_argument("--body-file", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command != "capture":
            raise CaptureError("the only command is: capture")
        result, code = capture(args)
    except CaptureError as exc:
        print(f"new_entry.py: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    sys.exit(main())
