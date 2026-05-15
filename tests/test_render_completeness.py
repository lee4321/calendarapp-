"""
CI completeness probe — every visualizer must render against both reference
themes (basic.yaml, SAMPLE.yaml) over a small fixture date range.

This is the test the design calls for in §11.3 / §11.4:

    > a test invokes every subcommand against SAMPLE.yaml over a small
    > fixture date range; any missing-key error fails the build.

The same probe runs against basic.yaml to guarantee the minimum-viable
theme stays minimum-viable: if a default ever creeps back into
CalendarConfig, basic.yaml drifts out of sync and this test catches it.

The test is intentionally permissive about renderer output — it only
checks that the subcommand exits 0 and produces a non-empty output
file.  Visual regression testing is a separate concern.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = REPO_ROOT / "config" / "themes"


# Subcommand metadata per design §11.3 / §11.4.
#
#   ext:          output filename suffix
#   accepts_theme: True when the subcommand accepts ``--theme``; text-mini
#                  is intentionally non-themed (renders pure-glyph output)
#                  so it gets exercised once with the default config.
#   output_dir:   where ecalendar writes the result.  Weekly/mini/timeline/
#                  blockplan/compactplan run their --outputfile through
#                  ecalendar._to_output_dir_path which strips any directory
#                  component and forces output to ``output/<basename>``.
#                  Excelheader writes to whatever path is given.
SUBCOMMAND_META: dict[str, dict[str, object]] = {
    "weekly":      {"ext": ".svg",  "accepts_theme": True,  "output_dir": "output"},
    "mini":        {"ext": ".svg",  "accepts_theme": True,  "output_dir": "output"},
    "mini-icon":   {"ext": ".svg",  "accepts_theme": True,  "output_dir": "output"},
    "text-mini":   {"ext": ".txt",  "accepts_theme": False, "output_dir": "output"},
    "timeline":    {"ext": ".svg",  "accepts_theme": True,  "output_dir": "output"},
    "blockplan":   {"ext": ".svg",  "accepts_theme": True,  "output_dir": "output"},
    "compactplan": {"ext": ".svg",  "accepts_theme": True,  "output_dir": "output"},
    "excelheader": {"ext": ".xlsx", "accepts_theme": True,  "output_dir": None},
}


REFERENCE_THEMES = ("basic", "SAMPLE")


@pytest.fixture
def fixture_dates() -> tuple[str, str]:
    """A small but representative date range: one calendar month, weekdays only."""
    return ("20260101", "20260131")


def _parametrize_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for subcommand, meta in sorted(SUBCOMMAND_META.items()):
        if meta["accepts_theme"]:
            for theme in REFERENCE_THEMES:
                cases.append((subcommand, theme))
        else:
            # Non-themed subcommand: probe once with the empty theme sentinel.
            cases.append((subcommand, ""))
    return cases


@pytest.mark.parametrize(
    "subcommand,theme", _parametrize_cases(), ids=lambda x: x or "default",
)
def test_subcommand_renders(
    subcommand: str,
    theme: str,
    fixture_dates: tuple[str, str],
    tmp_path: Path,
) -> None:
    """Every (subcommand, reference-theme) pair must render cleanly."""
    meta = SUBCOMMAND_META[subcommand]
    start, end = fixture_dates
    theme_tag = theme or "default"
    basename = f"_completeness_{subcommand}_{theme_tag}{meta['ext']}"

    if meta["output_dir"]:
        actual_output = REPO_ROOT / str(meta["output_dir"]) / basename
        outputfile_arg = basename
    else:
        actual_output = tmp_path / basename
        outputfile_arg = str(actual_output)
    actual_output.parent.mkdir(parents=True, exist_ok=True)
    actual_output.unlink(missing_ok=True)

    cmd = [
        sys.executable,
        str(REPO_ROOT / "ecalendar.py"),
        subcommand,
        start,
        end,
        "--outputfile", outputfile_arg,
        "--quiet",
    ]
    if theme:
        cmd.extend(["--theme", theme])
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
        )
        label = f"{subcommand}" + (f" on theme {theme!r}" if theme else "")
        assert result.returncode == 0, (
            f"{label} exited {result.returncode}.\nstderr:\n{result.stderr}"
        )
        assert actual_output.exists(), (
            f"{label} produced no output file at {actual_output}"
        )
        assert actual_output.stat().st_size > 0, (
            f"{label} produced an empty output file"
        )
    finally:
        actual_output.unlink(missing_ok=True)
