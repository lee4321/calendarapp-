"""Tests for the required-key registry + missing-key error formatting (§11.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.required_keys import (
    REQUIRED_KEYS,
    RequiredKey,
    VISUALIZERS,
    check_all_visualizers,
    check_required_keys,
    format_missing_key_error,
)
from config.unified_theme import parse_theme, load_theme_file

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"


# ─── basic.yaml is the CI completeness probe (§11.4) ────────────────────────


def test_basic_yaml_satisfies_every_visualizer() -> None:
    """basic.yaml must render every subcommand with no missing-key errors."""
    theme = load_theme_file(THEMES_DIR / "basic.yaml")
    failures = check_all_visualizers(theme)
    bad = {v: keys for v, keys in failures.items() if keys}
    assert not bad, (
        "basic.yaml is missing required keys for visualizers: "
        + "; ".join(f"{v}={[k.path for k in keys]}" for v, keys in bad.items())
    )


def test_sample_yaml_satisfies_every_visualizer() -> None:
    """SAMPLE.yaml is the complete annotated reference; it too must pass."""
    theme = load_theme_file(THEMES_DIR / "SAMPLE.yaml")
    failures = check_all_visualizers(theme)
    bad = {v: keys for v, keys in failures.items() if keys}
    assert not bad, (
        "SAMPLE.yaml is missing required keys for visualizers: "
        + "; ".join(f"{v}={[k.path for k in keys]}" for v, keys in bad.items())
    )


# ─── lazy-by-visualizer scoping ────────────────────────────────────────────


def test_visualizer_specific_keys_not_checked_for_other_visualizers() -> None:
    """A theme missing compact_plan.* should still pass for weekly."""
    raw = {
        "theme": {"name": "x", "version": "3.0"},
        "base": {"font_family": "Roboto-Regular", "default_missing_icon": "x"},
        "layout": {"margin": {"top": 1, "right": 1, "bottom": 1, "left": 1}},
        "events": {"item_placement_order": ["priority"]},
        "fiscal": {"label_format": "{period_short}", "end_label_format": "End"},
        "colors": {"month_palette": "Greys", "fiscal_palette": "Greys",
                   "group_palette": "Greys"},
        "weekly": {"week_numbers": {"label_format": "W"}, "overflow": {"icon": "x"}},
        # Token definitions weekly needs
        "style_rules": [
            {"define": "text", "as": name,
             "style": {"font": "Roboto-Regular", "size": 8, "color": "black"}}
            for name in (
                "base", "heading", "body", "caption", "label",
                "day_number", "month_title", "week_number",
                "event_name", "event_notes", "event_date", "duration_date",
                "holiday_title", "fiscal_label",
            )
        ] + [
            {"define": "box", "as": name, "style": {"fill": "white"}}
            for name in ("default", "cell", "header", "day", "event", "duration")
        ] + [
            {"define": "line", "as": name, "style": {"color": "grey", "width": 0.5, "opacity": 1.0}}
            for name in ("grid", "separator")
        ] + [
            {"define": "icon", "as": name, "style": {"icon": "x", "color": "black", "size": 8}}
            for name in ("event", "duration", "overflow")
        ],
    }
    theme = parse_theme(raw)
    # No mini_calendar, no timeline, no blockplan, no compact_plan...
    weekly_missing = check_required_keys(theme, "weekly")
    assert weekly_missing == [], (
        f"weekly should pass with just weekly-related keys; missing: {[k.path for k in weekly_missing]}"
    )
    # ...but mini should complain.
    mini_missing = check_required_keys(theme, "mini")
    paths = {k.path for k in mini_missing}
    assert "mini_calendar.title_format" in paths


# ─── error formatting ──────────────────────────────────────────────────────


def test_format_missing_key_error_mentions_keys_and_example() -> None:
    """The error block lists each missing key and a paste-ready example value."""
    missing = [
        RequiredKey(
            path="mini_calendar.title_format",
            kind="setting",
            type_hint="str (Arrow format)",
            used_by=frozenset({"mini", "mini-icon"}),
            description="",
        ),
    ]
    err = format_missing_key_error(missing, visualizer="mini", theme_origin="my.yaml")
    assert "my.yaml" in err
    assert "mini_calendar.title_format" in err
    assert "MMMM YYYY" in err  # example value pulled from basic.yaml
    assert "config/themes/basic.yaml" in err
    # Lazy formatting only emits sections for the missing keys.
    assert err.count("missing key:") == 1


def test_format_missing_key_error_handles_tokens() -> None:
    missing = [
        RequiredKey(
            path="style_rules:text:day_number",
            kind="token",
            type_hint="text token",
            used_by=frozenset({"weekly", "mini"}),
            description="",
        ),
    ]
    err = format_missing_key_error(missing, visualizer="weekly")
    assert "style_rules:text:day_number" in err
    assert "define: text" in err
    assert "as: day_number" in err


def test_format_missing_key_error_empty() -> None:
    assert format_missing_key_error([], visualizer="weekly") == ""


# ─── registry sanity ───────────────────────────────────────────────────────


def test_registry_paths_unique() -> None:
    seen: set[str] = set()
    for req in REQUIRED_KEYS:
        assert req.path not in seen, f"duplicate registry entry: {req.path}"
        seen.add(req.path)


def test_registry_used_by_subset_of_visualizers() -> None:
    for req in REQUIRED_KEYS:
        unknown = req.used_by - VISUALIZERS
        assert not unknown, (
            f"{req.path}: used_by has unknown visualizers {unknown}"
        )


@pytest.mark.parametrize("visualizer", sorted(VISUALIZERS))
def test_every_visualizer_has_at_least_one_required_key(visualizer: str) -> None:
    """Every CLI visualizer should appear in some used_by set."""
    keys_for = [req for req in REQUIRED_KEYS if visualizer in req.used_by]
    assert keys_for, f"visualizer '{visualizer}' has no required keys defined"
