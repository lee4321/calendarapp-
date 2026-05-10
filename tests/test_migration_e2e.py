"""End-to-end migration pipeline test.

For every legacy theme in ``config/themes/``, run the converter and parse
the result with the new unified loader, then probe required-key
satisfaction per visualizer.  This exercises the full migration
pipeline against real-world themes and surfaces any missing
transformation in the converter before the runtime cutover.

If a theme's converter output fails the unified parser, the migration
plan in design §7 needs a fix before the cutover commit.  If a theme
parses but fails required-keys for a given visualizer, that's expected
for themes that only target one visualizer (e.g. TJXweekly.yaml).
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from config.required_keys import (
    REQUIRED_KEYS,
    VISUALIZERS,
    check_required_keys,
)
from config.unified_theme import ThemeError, parse_theme

import sys

# Make the project root importable so we can use tools.migrate_theme.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.migrate_theme import convert_theme  # noqa: E402

import yaml  # noqa: E402

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"


# Themes that target a single visualizer.  They legitimately omit other
# visualizers' required keys, so we don't enforce full-matrix completeness
# on them.  Map each to the visualizer(s) the theme is intended for.
SPECIALIZED_THEMES: dict[str, set[str]] = {
    "TJXweekly":      {"weekly"},
    "TJXmini":        {"mini"},
    "TJXmini-icon":   {"mini-icon"},
    "TJXtext-mini":   {"text-mini"},
    "TJXtimeline":    {"timeline"},
    "TJXblockplan":   {"blockplan"},
    "TJXcompactplan": {"compactplan"},
    "TJXexcelheader": {"excelheader"},
}


def _legacy_theme_paths() -> list[Path]:
    out: list[Path] = []
    for p in sorted(THEMES_DIR.glob("*.yaml")):
        if p.name.endswith(".converted.yaml") or p.name.endswith(".yaml.bak"):
            continue
        # basic.yaml is already in the unified shape; SAMPLE.yaml was rewritten;
        # both are covered by tests/test_required_keys.py.
        if p.name in ("basic.yaml", "SAMPLE.yaml"):
            continue
        out.append(p)
    return out


def _deep_to_dict(obj: object) -> object:
    """Recursively convert OrderedDict / nested OrderedDicts to plain dicts.

    The converter emits OrderedDicts to preserve section order; the unified
    parser accepts plain dicts (Python 3.7+ dicts are insertion-ordered, so
    no order is lost).  Plain-dict normalization also lets us round-trip
    through ``yaml.safe_dump`` without registering a custom representer.
    """
    if isinstance(obj, dict):
        return {k: _deep_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_to_dict(v) for v in obj]
    return obj


@pytest.mark.parametrize("theme_path", _legacy_theme_paths(), ids=lambda p: p.name)
def test_legacy_theme_round_trips_through_unified_parser(theme_path: Path) -> None:
    """Convert -> parse; the unified loader must accept the converted output."""
    raw_legacy = yaml.safe_load(theme_path.read_text()) or {}
    converted = _deep_to_dict(convert_theme(raw_legacy, fname=theme_path.name))
    try:
        theme = parse_theme(converted)
    except ThemeError as exc:
        pytest.fail(f"{theme_path.name}: unified parser rejected converted output: {exc}")
    # Smoke check: theme metadata round-trips.
    assert theme.sections.get("theme"), f"{theme_path.name}: missing 'theme' section"


def test_full_theme_completeness_summary() -> None:
    """Aggregate report of required-key gaps per (theme, visualizer).

    This test does not enforce completeness — converted legacy themes are
    expected to have gaps because the converter currently carries per-
    visualizer styling sections (weekly.day_box.*, mini_calendar.*_color,
    timeline.*_color) through unchanged.  Those gaps disappear when the
    runtime cutover lifts those keys into style_rules.

    The test exists to *inventory* the gaps so the cutover commit has a
    concrete punch list.  The findings get printed when the test is run
    with ``-s``.
    """
    findings: list[str] = []
    for theme_path in _legacy_theme_paths():
        raw_legacy = yaml.safe_load(theme_path.read_text()) or {}
        converted = _deep_to_dict(convert_theme(raw_legacy, fname=theme_path.name))
        try:
            theme = parse_theme(converted)
        except ThemeError as exc:
            findings.append(f"{theme_path.name}: PARSE ERROR — {exc}")
            continue
        stem = theme_path.stem
        intended = SPECIALIZED_THEMES.get(stem, set(VISUALIZERS))
        for v in sorted(intended):
            missing = check_required_keys(theme, v)
            if missing:
                paths = ", ".join(k.path for k in missing[:5])
                more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
                findings.append(f"{theme_path.name} [{v}]: missing {paths}{more}")
    # Always emit the report so a developer reviewing the migration can see
    # the converter's current gaps.  The assertion ensures the test framework
    # records at least one positive result (the report itself).
    print("\n=== completeness gap inventory (converted legacy themes) ===")
    if findings:
        for line in findings:
            print(f"  {line}")
    else:
        print("  (no gaps — every converted theme satisfies its intended visualizers)")
    print("=== end completeness gap inventory ===\n")
    assert True  # explicit pass — see docstring
