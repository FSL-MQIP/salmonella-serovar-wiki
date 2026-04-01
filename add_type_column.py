#!/usr/bin/env python3
"""
Add 'Type' column to the outbreak table in all serovar markdown files.

Rules:
- Only modifies the table under '## Human/Animal Outbreaks'
- Header row: appends '| Type |'
- Separator row: appends '| --- |'
- Data rows (starting with '|' but NOT footnote lines starting with '<sup>'): appends '| Human |'
- Footnote lines (starting with '<sup>') are left untouched
- Files with no outbreak table (just text) are skipped
- Tables under other sections (Border Rejections, Recalls, etc.) are NOT touched
- Normalises data rows that are missing a trailing '|'
"""

import glob
import re
import sys
from pathlib import Path

SEROVARS_DIR = Path("docs/serovars")

# The outbreak section header (exact, case-sensitive)
OUTBREAK_HEADER = "## Human/Animal Outbreaks"

# The expected outbreak table header cells
OUTBREAK_TABLE_HEADER_PATTERN = re.compile(
    r"^\|\s*Year\s*\|", re.IGNORECASE
)


def is_table_row(line: str) -> bool:
    """True for any line that starts with '|' (ignoring leading whitespace)."""
    return line.lstrip().startswith("|")


def is_footnote_line(line: str) -> bool:
    """True for lines that are HTML footnote lines like <sup>...</sup>."""
    stripped = line.strip()
    return stripped.startswith("<sup>")


def is_separator_row(line: str) -> bool:
    """True for table separator rows like '| --- | --- | --- |'."""
    # A separator row contains only |, -, space, and :
    inner = line.strip().strip("|")
    return bool(re.match(r"^[\s\-:|]+$", inner))


def ensure_trailing_pipe(line: str) -> str:
    """Ensure a table row ends with '|'. Preserves trailing newline."""
    nl = ""
    if line.endswith("\n"):
        nl = "\n"
        line = line[:-1]
    stripped = line.rstrip()
    if not stripped.endswith("|"):
        stripped = stripped + " |"
    return stripped + nl


def process_file(path: Path) -> bool:
    """
    Process a single markdown file.
    Returns True if the file was modified.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    # Find the '## Human/Animal Outbreaks' section
    outbreak_section_idx = None
    for i, line in enumerate(lines):
        if line.strip() == OUTBREAK_HEADER:
            outbreak_section_idx = i
            break

    if outbreak_section_idx is None:
        return False  # No outbreak section at all

    # Find the table header inside the outbreak section.
    # We look from outbreak_section_idx+1 until the next ## heading.
    table_header_idx = None
    next_section_idx = None

    for i in range(outbreak_section_idx + 1, len(lines)):
        line = lines[i]
        # Detect next section heading
        if line.startswith("## ") and i > outbreak_section_idx:
            next_section_idx = i
            break
        if OUTBREAK_TABLE_HEADER_PATTERN.match(line):
            table_header_idx = i
            break

    if table_header_idx is None:
        return False  # No outbreak table found (just text)

    # Determine the end of the outbreak table.
    # The table spans from table_header_idx until we hit a line that is
    # neither a table row nor a footnote line (or we reach the next section).
    table_end_idx = table_header_idx
    for i in range(table_header_idx, len(lines)):
        line = lines[i]
        if next_section_idx is not None and i >= next_section_idx:
            break
        if i == table_header_idx:
            table_end_idx = i
            continue
        # A blank line ends the table
        if line.strip() == "":
            break
        if is_table_row(line) or is_footnote_line(line):
            table_end_idx = i
        else:
            break

    # Check whether 'Type' column already exists in header (idempotency guard)
    header_line = lines[table_header_idx]
    if re.search(r"\|\s*Type\s*\|", header_line, re.IGNORECASE):
        return False  # Already done

    # Now modify lines from table_header_idx to table_end_idx (inclusive)
    for i in range(table_header_idx, table_end_idx + 1):
        line = lines[i]

        # Footnote lines: skip entirely
        if is_footnote_line(line):
            continue

        if not is_table_row(line):
            continue

        nl = "\n" if line.endswith("\n") else ""
        raw = line.rstrip("\n")

        if i == table_header_idx:
            # Header row — ensure trailing pipe, then append '| Type |'
            raw = raw.rstrip()
            if not raw.endswith("|"):
                raw += " |"
            raw += " Type |"
        elif is_separator_row(line):
            # Separator row
            raw = raw.rstrip()
            if not raw.endswith("|"):
                raw += " |"
            raw += " --- |"
        else:
            # Data row — normalize trailing pipe, then append '| Human |'
            raw = raw.rstrip()
            if not raw.endswith("|"):
                raw += " |"
            raw += " Human |"

        lines[i] = raw + nl

    new_text = "".join(lines)
    if new_text == text:
        return False

    path.write_text(new_text, encoding="utf-8")
    return True


def main():
    md_files = sorted(SEROVARS_DIR.rglob("*.md"))
    # Exclude index.md files
    md_files = [f for f in md_files if f.name != "index.md"]

    modified = []
    skipped_no_section = []
    skipped_no_table = []
    skipped_already_done = []

    for path in md_files:
        result = process_file(path)
        if result:
            modified.append(path)
        # (we don't separately track skip reasons here — keep it simple)

    print(f"Modified {len(modified)} file(s):")
    for p in modified:
        print(f"  {p}")

    print(f"\nTotal serovar files scanned: {len(md_files)}")
    print(f"Files modified: {len(modified)}")
    print(f"Files unchanged: {len(md_files) - len(modified)}")


if __name__ == "__main__":
    main()
