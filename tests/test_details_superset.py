"""The details document says everything the retired companion pages said.

``tests/fixtures/details_superset.json`` holds what the gantt details,
weekly overflow, mini / mini-icon / candybar details and compactplan key
pages wrote before they were removed (see
``tools/capture_details_superset.py``).  Each case is rendered again with a
theme whose details columns cover every column those pages had, and every
value they wrote must appear in the document:

* each non-empty cell, and each part of each sub-line (an event's notes,
  its end date);
* each note ("Every item was drawn as scheduled.");
* each row the page gave a mark -- a bar swatch, a milestone flag, a
  holiday icon, a symbol -- must be a row in the document carrying an
  icon image.

Values are compared as the document writes them (escaped for a table
cell); flags the pages spelled "True" / "Yes" are carried by the document's
icons and Type column instead, so they are not compared as text.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from renderers.markdown_details import escape_cell

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = json.loads((REPO_ROOT / "tests" / "fixtures" / "details_superset.json").read_text(encoding="utf-8"))

#: Page text that is a flag or a placeholder, not information.
_NOT_VALUES = {"", "True", "Yes", "—"}

#: Every column the pages had, in the details column schema: the gantt task
#: table as-is, plus ISO dates, the type and the key mark for the calendar
#: listings, and start / end for the overflow report.
_EXCEPTION_COLUMNS = [
    {"field": "issue", "header": "Issue"},
    {"field": "task", "header": "Task"},
    {"field": "date", "header": "Date", "date_format": "YYYY-MM-DD"},
    {"field": "start", "header": "Start", "date_format": "YYYY-MM-DD"},
    {"field": "end", "header": "End", "date_format": "YYYY-MM-DD"},
    {"field": "ref", "header": "Ref"},
    {"field": "detail", "header": "Detail"},
]


def _superset_theme(tmp_path: Path) -> Path:
    theme = yaml.safe_load((REPO_ROOT / "config" / "themes" / "default.yaml").read_text(encoding="utf-8"))
    columns = [dict(column) for column in theme["gantt"]["columns"]]
    columns += [
        {"field": "marker", "header": "Key"},
        {"field": "start_date", "header": "Start ISO", "date_format": "YYYY-MM-DD"},
        {"field": "end_date", "header": "End ISO", "date_format": "YYYY-MM-DD"},
        {"field": "category", "header": "Type"},
    ]
    markdown = theme["details"]["markdown"]
    markdown["columns"] = columns
    markdown["exception_columns"] = _EXCEPTION_COLUMNS
    path = tmp_path / "superset.yaml"
    path.write_text(yaml.safe_dump(theme, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _render(view: str, argv: list[str], theme: Path) -> str:
    stem = f"_superset_{view.replace('-', '_')}"
    args = list(argv)
    args[args.index("-th") + 1] = str(theme)
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    folder = REPO_ROOT / "output" / stem
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "ecalendar.py"), *args, "--outputfile", f"{stem}.svg", "--quiet"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        return (folder / f"{stem}.md").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _sub_line_values(text: str) -> list[str]:
    values = []
    for part in text.split(" | "):
        part = part.strip()
        values.append(part.removeprefix("End: "))
    return values


@pytest.mark.parametrize("view", sorted(FIXTURE))
def test_details_document_lists_everything_the_page_did(view: str, tmp_path: Path) -> None:
    case = FIXTURE[view]
    document = _render(view, case["argv"], _superset_theme(tmp_path))
    table_lines = [line for line in document.splitlines() if line.startswith("|")]

    missing: list[str] = []
    unmarked: list[str] = []
    for section in case["sections"]:
        for note in section["notes"]:
            if escape_cell(note) not in document:
                missing.append(f"{section['title']}: note {note!r}")
        for row in section["rows"]:
            values = [cell for cell in row["cells"]] + _sub_line_values(row["sub_line"])
            for value in values:
                if value.strip() in _NOT_VALUES:
                    continue
                if escape_cell(value) not in document:
                    missing.append(f"{section['title']}: {value!r}")
            if row["mark"]:
                index = row["name_column"]
                label = row["cells"][index] if index is not None else next((c for c in row["cells"] if c), "")
                needle = escape_cell(label)
                if not any(needle in line and "![" in line for line in table_lines):
                    unmarked.append(f"{section['title']}: {label!r}")

    assert not missing, f"{view}: the details document leaves out {len(missing)} value(s): {missing[:10]}"
    assert not unmarked, f"{view}: rows the page marked have no icon in the document: {unmarked[:10]}"
