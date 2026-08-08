"""The USER_GUIDE CLI tables must match the parser they document.

Both the option catalog and the per-command positional tables used to be
hand-maintained and had drifted badly — whole subcommands were missing,
and `excelheader` documented its dates as required when the parser makes
them optional. They are generated now, and these tests fail when
`cli/args.py` changes without regenerating them.

The positional *section* is only partly generated: each block's prose is
hand-written and must survive regeneration, which is asserted below.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.generate_option_catalog import (  # noqa: E402
    build_table,
    positional_table,
    regenerate,
    _subcommand_parsers,
)

GUIDE = REPO_ROOT / "USER_GUIDE.md"
HEADING = "## Command-Line Option Catalog (All Options)"
POSITIONAL_HEADING = "## Positional Arguments by Command"


def catalog_section() -> str:
    text = GUIDE.read_text()
    start = text.index(HEADING)
    match = re.search(r"^## ", text[start + len(HEADING):], re.M)
    end = start + len(HEADING) + (match.start() if match else len(text))
    return text[start:end]


def test_the_catalog_matches_the_parser():
    """Regenerate with: uv run python tools/generate_option_catalog.py"""
    assert catalog_section().rstrip("\n") == build_table().rstrip("\n")


def positional_section() -> str:
    text = GUIDE.read_text()
    start = text.index(POSITIONAL_HEADING)
    match = re.search(r"^## ", text[start + len(POSITIONAL_HEADING):], re.M)
    end = start + len(POSITIONAL_HEADING) + (match.start() if match else len(text))
    return text[start:end]


def test_the_guide_is_fully_regenerated():
    """Running the generator again must change nothing."""
    text = GUIDE.read_text()
    assert regenerate(text) == text


def test_every_command_with_positionals_has_a_table():
    section = positional_section()
    for name, sub in _subcommand_parsers().items():
        table = positional_table(sub)
        if table:
            assert table in section, f"{name} positional table missing or stale"


def test_regeneration_preserves_the_hand_written_prose():
    """Only tables are generated; the notes around them are not."""
    section = positional_section()
    for phrase in (
        "Generates an Excel workbook",          # excelheader block
        "The label columns are **not** frozen", # excelheader block
        "Generates the same workbook skeleton", # excelblockplan block
    ):
        assert phrase in section


def test_the_check_mode_agrees():
    result = subprocess.run(
        [sys.executable, "tools/generate_option_catalog.py", "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_every_row_has_five_columns():
    """A stray pipe in a help string would silently break the table."""
    rows = [
        line for line in catalog_section().splitlines()
        if line.startswith("| ") and not line.startswith("|---")
    ]
    assert rows
    for row in rows:
        # Cells are pipe-separated; escaped pipes inside a cell do not count.
        cells = re.split(r"(?<!\\)\|", row)
        assert len(cells) == 7, f"{len(cells) - 2} columns in: {row[:80]}"


def test_every_subcommand_appears_somewhere():
    section = catalog_section()
    for command in ("weekly", "gantt", "pit", "candybar", "blockplan", "exportdata"):
        assert f"`{command}`" in section


def test_gantt_options_are_listed():
    """The view this catalog regeneration was prompted by."""
    section = catalog_section()
    gantt_rows = [
        line for line in section.splitlines() if "`gantt`" in line
    ]
    assert len(gantt_rows) > 20
    for flag in ("--WBS", "--weekends", "--milestones", "--includenotes", "--theme"):
        assert any(line.startswith(f"| `{flag}`") for line in gantt_rows), flag


@pytest.mark.parametrize(
    "option,expected",
    [
        ("--outputfile", "`-o` for `exportdata`"),   # per-command short flag
        ("--weekends", "choices `0, 1, 2, 3, 4`"),   # choices rendered
    ],
)
def test_notable_rows_render_their_detail(option, expected):
    row = next(
        line for line in catalog_section().splitlines()
        if line.startswith(f"| `{option}`")
    )
    assert expected in row
