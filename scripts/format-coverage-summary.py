#!/usr/bin/env python3
# Renders `just coverage-machine`/`just coverage-all`'s per-core summary as
# an aligned table. Reads blocks on stdin, one per core:
#   ### <module>\t<ok|FAILED>
#   <raw `just coverage` output for that core, including
#    `verilator_coverage --annotate`'s "Coverage Summary:" block>
#   ### <next module>\t...
#
# Only coverage categories with a nonzero total become columns -- this
# project enables --coverage-line --coverage-toggle (CLAUDE.md), which in
# practice also populates branch, while expr/fsm_state/fsm_arc stay 0/0.
# Dropping zero-total categories rather than hardcoding line/toggle/branch
# means the table adapts if that flag set ever changes.

from __future__ import annotations

import re
import sys

BLOCK_RE = re.compile(r"^### (.+?)\t(.+)$", re.M)
CATEGORY_RE = re.compile(r"^\s*(\w+)\s*:\s*[\d.]+%\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", re.M)

Row = tuple[str, str, dict[str, tuple[int, int]]]


def parse_blocks(text: str) -> list[Row]:
    markers = list(BLOCK_RE.finditer(text))
    rows: list[Row] = []
    for i, m in enumerate(markers):
        module, status = m.group(1), m.group(2)
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        body = text[start:end]
        categories: dict[str, tuple[int, int]] = {}
        for cat, hit, total in CATEGORY_RE.findall(body):
            if int(total) > 0 and cat not in categories:
                categories[cat] = (int(hit), int(total))
        rows.append((module, status, categories))
    return rows


def render(rows: list[Row]) -> str:
    categories: list[str] = []
    for _, _, cats in rows:
        for cat in cats:
            if cat not in categories:
                categories.append(cat)

    headers = ["MODULE", "STATUS"] + [c.upper() for c in categories]
    table = []
    for module, status, cats in rows:
        row = [module, status]
        for cat in categories:
            if cat in cats:
                hit, total = cats[cat]
                pct = 100.0 * hit / total
                row.append(f"{pct:5.1f}% ({hit}/{total})")
            else:
                row.append("-")
        table.append(row)

    widths = [len(h) for h in headers]
    for row in table:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [fmt_row(headers), fmt_row(["-" * w for w in widths])]
    lines += [fmt_row(row) for row in table]
    return "\n".join(lines)


def main() -> int:
    text = sys.stdin.read()
    rows = parse_blocks(text)
    if not rows:
        return 0
    print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
