"""Helpers for parsing and chunking unified diffs."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


DIFF_GIT_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class DiffLine:
    """A single line of a diff hunk, with its position in the new file."""

    content: str
    new_lineno: Optional[int]
    old_lineno: Optional[int]
    kind: str  # "add", "del", "context"


@dataclass
class FileDiff:
    """The parsed diff for a single file."""

    path: str
    old_path: str
    is_binary: bool = False
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    lines: List[DiffLine] = field(default_factory=list)
    raw: str = ""

    def added_line_numbers(self) -> List[int]:
        return [line.new_lineno for line in self.lines if line.kind == "add" and line.new_lineno]


def parse_diff(diff_text: str) -> List[FileDiff]:
    """Parse a unified diff (as produced by the GitHub compare/PR diff API) into FileDiff objects."""
    if not diff_text:
        return []

    files: List[FileDiff] = []
    current: Optional[FileDiff] = None
    current_raw_lines: List[str] = []
    old_lineno = new_lineno = 0

    def flush():
        if current is not None:
            current.raw = "\n".join(current_raw_lines)
            files.append(current)

    for raw_line in diff_text.splitlines():
        match = DIFF_GIT_RE.match(raw_line)
        if match:
            flush()
            current_raw_lines = [raw_line]
            old_path, new_path = match.group(1), match.group(2)
            current = FileDiff(path=new_path, old_path=old_path)
            old_lineno = new_lineno = 0
            continue

        if current is None:
            continue

        current_raw_lines.append(raw_line)

        if raw_line.startswith("Binary files") or "GIT binary patch" in raw_line:
            current.is_binary = True
        elif raw_line.startswith("new file mode"):
            current.is_new = True
        elif raw_line.startswith("deleted file mode"):
            current.is_deleted = True
        elif raw_line.startswith("rename from") or raw_line.startswith("rename to"):
            current.is_renamed = True
        elif raw_line.startswith("@@"):
            hunk_match = HUNK_HEADER_RE.match(raw_line)
            if hunk_match:
                old_lineno = int(hunk_match.group(1))
                new_lineno = int(hunk_match.group(2))
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            current.lines.append(DiffLine(raw_line, new_lineno, None, "add"))
            new_lineno += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            current.lines.append(DiffLine(raw_line, None, old_lineno, "del"))
            old_lineno += 1
        elif raw_line.startswith(("+++", "---", "index ", "similarity index", "old mode", "new mode")):
            continue
        else:
            current.lines.append(DiffLine(raw_line, new_lineno, old_lineno, "context"))
            old_lineno += 1
            new_lineno += 1

    flush()
    return files


def truncate_file_diff(raw: str, max_chars: int) -> str:
    """Truncate an individual file's diff text if it is excessively large."""
    if len(raw) <= max_chars:
        return raw
    truncated = raw[:max_chars]
    return truncated + f"\n... [diff truncated, {len(raw) - max_chars} more characters omitted] ..."


def build_prompt_diff(files: List[FileDiff], max_files: int, max_file_chars: int, max_total_chars: int) -> str:
    """Build a size-bounded textual representation of the diff suitable for a prompt.

    Skips binary files, truncates individual large files, and stops once the overall
    character budget is exhausted (with a note about how many files were omitted).
    """
    parts: List[str] = []
    total = 0
    omitted = 0

    for index, file_diff in enumerate(files):
        if index >= max_files:
            omitted += len(files) - index
            break

        if file_diff.is_binary:
            entry = f"diff --git a/{file_diff.old_path} b/{file_diff.path}\n[binary file, contents omitted]"
        else:
            entry = truncate_file_diff(file_diff.raw, max_file_chars)

        if total + len(entry) > max_total_chars:
            omitted += len(files) - index
            break

        parts.append(entry)
        total += len(entry)

    text = "\n\n".join(parts)
    if omitted:
        text += f"\n\n... [{omitted} additional changed file(s) omitted due to size limits] ..."
    return text
