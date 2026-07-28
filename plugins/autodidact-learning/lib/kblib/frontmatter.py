"""Restricted frontmatter parser + body normalization (CONTRACT.md grammar).

Deliberately NOT YAML: only `key: value` scalars and two-space `- item`
lists. Anything else is a parse error — the restriction is the contract.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

SCALAR_RE = re.compile(r"^([a-z_]+): (.+)$")
LIST_HEAD_RE = re.compile(r"^([a-z_]+):$")
LIST_ITEM_RE = re.compile(r"^  - (.+)$")


class FrontmatterError(ValueError):
    """Grammar violation; message states the offending line."""


def split(text: str) -> tuple[list[str], str]:
    """Split raw file text into (frontmatter lines, body text).

    The file must start with a line that is exactly `---`; frontmatter runs
    until the next such line; the body is everything after it.
    """
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        raise FrontmatterError("file does not start with '---'")
    for i in range(1, len(lines)):
        if lines[i] == "---":
            return lines[1:i], "\n".join(lines[i + 1 :])
    raise FrontmatterError("frontmatter is not closed by '---'")


def parse(text: str) -> tuple[dict[str, str | list[str]], str]:
    """Parse raw file text into (frontmatter dict, body).

    Enforces the grammar only; schema (known keys, enums, formats) is
    validated by kb_checks. Raises FrontmatterError on any violation.
    """
    fm_lines, body = split(text)
    data: dict[str, str | list[str]] = {}
    open_list: str | None = None
    for line in fm_lines:
        if "\t" in line:
            raise FrontmatterError(f"tab character in frontmatter: {line!r}")
        if line.strip() == "":
            raise FrontmatterError("blank line inside frontmatter")
        if line.lstrip().startswith("#"):
            raise FrontmatterError(f"comment inside frontmatter: {line!r}")
        m = LIST_ITEM_RE.match(line)
        if m:
            if open_list is None:
                raise FrontmatterError(f"list item without a list head: {line!r}")
            items = data[open_list]
            assert isinstance(items, list)
            items.append(m.group(1).rstrip())
            continue
        m = SCALAR_RE.match(line)
        if m:
            key, value = m.group(1), m.group(2).rstrip()
            if key in data:
                raise FrontmatterError(f"duplicate key: {key}")
            if not value:
                raise FrontmatterError(f"empty value for key: {key}")
            data[key] = value
            open_list = None
            continue
        m = LIST_HEAD_RE.match(line)
        if m:
            key = m.group(1)
            if key in data:
                raise FrontmatterError(f"duplicate key: {key}")
            data[key] = []
            open_list = key
            continue
        raise FrontmatterError(f"line matches no allowed form: {line!r}")
    for key, value in data.items():
        if isinstance(value, list) and not value:
            raise FrontmatterError(f"list head with zero items: {key}")
    return data, body


def normalize_body(body: str) -> str:
    """CONTRACT normalization: LF endings, per-line trailing whitespace
    stripped, Unicode NFC, leading/trailing blank lines stripped."""
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def entry_id(body: str) -> str:
    """First 12 hex chars of sha256 over the normalized body."""
    normalized = normalize_body(body)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
