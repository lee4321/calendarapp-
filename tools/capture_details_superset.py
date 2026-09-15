#!/usr/bin/env python
"""
Freeze what the companion SVG pages listed, for tests/test_details_superset.py.

The details document replaced the gantt details, weekly overflow, mini /
mini-icon / candybar details and compactplan key pages.  Before those pages
were removed, this tool rendered each one and recorded everything it wrote
-- every section, row cell, sub-line, row mark and note -- into
``tests/fixtures/details_superset.json``.  The test renders the same cases
and asserts the details document still says all of it, so the document
stays a superset of the pages after they are gone.

It needs the pages' writer (renderers/details_page.py) to run, so it can
only be re-run against a checkout from before their removal.

    uv run python tools/capture_details_superset.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "details_superset.json"

#: view → ecalendar argv (after the script name).  The capture also passes
#: the flag that turned each page on; the test does not need it.
CASES: dict[str, list[str]] = {
    "gantt": ["gantt", "20260101", "20260331", "-th", "default"],
    "weekly": ["weekly", "20260101", "20260331", "-th", "default"],
    "mini": ["mini", "20260101", "20261231", "-th", "default"],
    "mini-icon": ["mini-icon", "20260101", "20261231", "-th", "default"],
    "candybar": ["candybar", "20260101", "20261231", "-th", "default"],
    "compactplan": ["compactplan", "20260309", "20260424", "-th", "default"],
}

#: Flags that turned a page on, where it was not on by default.
_PAGE_FLAGS: dict[str, list[str]] = {"weekly": ["--overflow"]}


def capture(view: str, argv: list[str]) -> dict:
    from renderers.details_page import DetailsPageWriter, as_columns  # ty: ignore[unresolved-import]

    import ecalendar

    sections: list[dict] = []
    original = (DetailsPageWriter.section, DetailsPageWriter.row, DetailsPageWriter.note)

    def section(self, title, columns):
        sections.append({"title": title, "columns": [c.heading for c in as_columns(columns)], "rows": [], "notes": []})
        return original[0](self, title, columns)

    def row(self, cells, columns, sub_line=None, mark=None):
        sections[-1]["rows"].append(
            {
                "cells": [str(cell or "") for cell in cells],
                "sub_line": str(sub_line[1] or "") if sub_line else "",
                "name_column": sub_line[0] if sub_line else None,
                "mark": mark is not None,
            }
        )
        return original[1](self, cells, columns, sub_line, mark)

    def note(self, text):
        if sections:
            sections[-1]["notes"].append(str(text))
        return original[2](self, text)

    stem = f"_superset_capture_{view.replace('-', '_')}"
    DetailsPageWriter.section, DetailsPageWriter.row, DetailsPageWriter.note = section, row, note
    try:
        rc = ecalendar.run(["ecalendar.py", *argv, *_PAGE_FLAGS.get(view, []), "-of", f"{stem}.svg", "--quiet"])
    finally:
        DetailsPageWriter.section, DetailsPageWriter.row, DetailsPageWriter.note = original
        shutil.rmtree(REPO_ROOT / "output" / stem, ignore_errors=True)
    if rc != 0:
        raise SystemExit(f"{view}: ecalendar exited {rc}")
    return {"argv": argv, "sections": sections}


def main() -> int:
    import os

    os.chdir(REPO_ROOT)
    fixture = {view: capture(view, argv) for view, argv in CASES.items()}
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = sum(len(s["rows"]) for case in fixture.values() for s in case["sections"])
    print(f"captured {rows} rows from {len(fixture)} pages into {FIXTURE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
