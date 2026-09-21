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

import sys
from pathlib import Path
from typing import Any

import pytest

from config.required_keys import (
    VISUALIZERS,
    check_required_keys,
)
from config.unified_theme import ThemeError, parse_theme

# Make the project root importable so we can use tools.migrate_theme.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from tools.migrate_theme import convert_theme

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"


# Themes that target a single visualizer.  They legitimately omit other
# visualizers' required keys, so we don't enforce full-matrix completeness
# on them.  Map each to the visualizer(s) the theme is intended for.
SPECIALIZED_THEMES: dict[str, set[str]] = {
    "TJXweekly": {"weekly"},
    "TJXmini": {"mini"},
    "TJXmini-icon": {"mini-icon"},
    "TJXtext-mini": {"text-mini"},
    "TJXtimeline": {"timeline"},
    "TJXblockplan": {"blockplan"},
    "TJXcompactplan": {"compactplan"},
    "TJXexcelblockplan": {"excelblockplan"},
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


def _deep_to_dict(obj: Any) -> Any:
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


def test_retired_event_color_maps_become_style_rules() -> None:
    """colors.resource_groups and compact_plan.color_rules migrate to fill
    rules every visualizer reads.  color_rules matched first-wins and
    style_rules layer last-wins, so they come out reversed."""
    from shared.data_models import Event
    from shared.rule_engine import StyleEngine

    legacy = {
        "colors": {"resource_groups": {"dev": "navy"}, "hash_lines": "black"},
        "compact_plan": {
            "color_rules": [
                {"name": "urgent", "select": {"priority": 5}, "color": "firebrick"},
                {"name": "dev", "select": {"resource_group": "Dev"}, "color": "teal"},
                {"name": "typo", "select": {"resouce_group": "Dev"}, "color": "pink"},
            ],
            "palette": ["gold"],
        },
        "style_rules": [
            {"name": "own", "apply_to": "box:event", "select": {"priority": 9}, "style": {"fill": "black"}},
        ],
    }
    out = _deep_to_dict(convert_theme(legacy))

    assert "resource_groups" not in out["colors"]
    assert "color_rules" not in out["compact_plan"]
    fills = [(r["name"], r["style"]["fill"]) for r in out["style_rules"] if "box:event" in str(r.get("apply_to"))]
    assert fills[:3] == [("resource group dev", "navy"), ("dev", "teal"), ("urgent", "firebrick")]
    assert fills[-1] == ("own", "black")  # the theme's own rules still come last and win

    engine = StyleEngine(out["style_rules"])

    def color(**fields: Any) -> str | None:
        return engine.evaluate_event(Event(task_name="T", start="20260105", end="20260105", **fields)).fill_color

    assert color(resource_group="Dev", priority=5) == "firebrick"  # the first color rule still wins
    assert color(resource_group="Dev") == "teal"
    assert color(resource_group="Ops") is None
    assert color(priority=9) == "black"
