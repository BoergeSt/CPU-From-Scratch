#!/usr/bin/env python3
# Checks Markdown tables in docs/ against CLAUDE.md's ~100-character
# uniform-rendered-width convention: every row in a GFM table is padded to
# the widest cell per column (render-markdown.nvim doesn't wrap cells), so
# a table's real on-screen width isn't its raw source line length.

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def table_blocks(lines: list[str]) -> list[tuple[int, int, list[str]]]:
    """Return (start_line, end_line, rows) for each contiguous run of '|' lines."""
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        if lines[i].strip().startswith("|"):
            start = i
            while i < n and lines[i].strip().startswith("|"):
                i += 1
            blocks.append((start + 1, i, lines[start:i]))
        else:
            i += 1
    return blocks


def rendered_width(rows: list[str]) -> int:
    """Uniform rendered width: each column padded to its widest cell, GFM-style."""
    table_rows = [r.strip().strip("|").split("|") for r in rows]
    cells = [[c.strip() for c in row] for row in table_rows]
    ncols = len(cells[0])
    col_widths = [0] * ncols
    for row in cells:
        for i, c in enumerate(row):
            if i < ncols:
                col_widths[i] = max(col_widths[i], len(c))
    # Each column: "| " + content + " " -> width + 3; plus one closing "|".
    return sum(col_widths) + ncols * 3 + 1


def check_file(path: Path, max_width: int) -> list[tuple[int, int, int]]:
    """Return (start_line, end_line, width) for every table exceeding max_width."""
    lines = path.read_text().splitlines()
    violations = []
    for start, end, rows in table_blocks(lines):
        if len(rows) < 2:
            continue  # a lone '|' line isn't a table
        width = rendered_width(rows)
        if width > max_width:
            violations.append((start, end, width))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Markdown files to check (default: every docs/**/*.md)",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=100,
        help="maximum uniform rendered table width in characters (default: 100)",
    )
    args = parser.parse_args()

    paths = args.paths or sorted(Path("docs").rglob("*.md"))

    found = False
    for path in paths:
        for start, end, width in check_file(path, args.max_width):
            found = True
            print(f"{path}:{start}-{end}: table renders at {width} chars "
                  f"(limit {args.max_width})")

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
