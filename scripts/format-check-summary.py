#!/usr/bin/env python3
# Renders `just check-machine`/`just check-all`'s per-core summary as an
# aligned table. Reads TSV on stdin, one line per core:
#   <module>\t<ok|FAILED>\t<detail>
# where <detail> is either "TESTS=N PASS=N FAIL=N SKIP=N" or
# "LINT/BUILD FAILED" (no counts available -- rendered as "-").

from __future__ import annotations

import re
import sys

FIELD_RE = re.compile(r"TESTS=(\d+) PASS=(\d+) FAIL=(\d+) SKIP=(\d+)")

HEADERS = ["MODULE", "STATUS", "TESTS", "PASS", "FAIL", "SKIP"]
NUMERIC_COLS = {2, 3, 4, 5}


def parse_row(line: str) -> list[str]:
    module, status, detail = line.rstrip("\n").split("\t", 2)
    match = FIELD_RE.search(detail)
    counts = list(match.groups()) if match else ["-", "-", "-", "-"]
    return [module, status, *counts]


def render(rows: list[list[str]]) -> str:
    widths = [len(h) for h in HEADERS]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "  ".join(
            cell.rjust(widths[i]) if i in NUMERIC_COLS else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        )

    lines = [fmt_row(HEADERS), fmt_row(["-" * w for w in widths])]
    lines += [fmt_row(row) for row in rows]
    return "\n".join(lines)


def main() -> int:
    rows = [parse_row(line) for line in sys.stdin if line.strip()]
    if not rows:
        return 0
    print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
