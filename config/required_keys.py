"""
Required-key registry and missing-key error formatting.

Implements design §11.2 (Error reporting for missing required settings)
in conjunction with §11.4 (basic.yaml as the example-value source).

The registry enumerates every theme YAML key that the runtime requires,
annotated with:

  * ``path``        — dotted key path, e.g. ``"mini_calendar.title_format"``
                      or ``"style_rules:text:day_number"`` for token tokens
  * ``kind``        — ``"setting"`` (a key in a section) or ``"token"`` (a
                      style_rules entry with ``define:``)
  * ``type_hint``   — short type description shown in the error
  * ``used_by``     — set of visualizer names that consume the value
  * ``description`` — one-line purpose, optional

``check_required_keys(theme, visualizer)`` returns the list of registry
entries whose value is missing from the loaded theme, scoped by the active
visualizer (lazy validation per §11.2).

``format_missing_key_error(missing, theme_origin)`` produces the
human-readable error block.  Example values are read from
``config/themes/basic.yaml`` so the error message and the reference theme
never drift apart (§11.4).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from config.unified_theme import UnifiedTheme

# Path to the bundled minimum-viable theme that supplies example values.
BASIC_YAML_PATH: Path = (
    Path(__file__).resolve().parent / "themes" / "basic.yaml"
)


# Visualizer identifiers as accepted by the CLI subcommand and by
# ``select.visualizer`` in style_rules.
VISUALIZERS: frozenset[str] = frozenset({
    "weekly",
    "mini",
    "mini-icon",
    "text-mini",
    "timeline",
    "blockplan",
    "compactplan",
    "excelheader",
})


# All-visualizer used_by set (every renderer needs the key).
_ALL: frozenset[str] = VISUALIZERS

# SVG renderers (everything except XLSX and text-mini).
_SVG: frozenset[str] = frozenset(VISUALIZERS - {"excelheader", "text-mini"})


@dataclass(frozen=True)
class RequiredKey:
    path: str
    kind: str               # "setting" | "token"
    type_hint: str
    used_by: frozenset[str]
    description: str = ""


# ─── Registry ───────────────────────────────────────────────────────────────
#
# Order matters: error messages list keys in registry order so the developer
# sees them grouped by section.  Add to this list when adding a new required
# field; if the field is optional, do not add it here.


REQUIRED_KEYS: tuple[RequiredKey, ...] = (
    # ── Theme metadata ──
    RequiredKey("theme.name",        "setting", "str", _ALL,
                "Theme display name shown in --theme listings"),
    RequiredKey("theme.version",     "setting", "str", _ALL,
                "Theme schema version (use \"3.0\" for the unified schema)"),

    # ── base ──
    RequiredKey("base.font_family",  "setting", "str", _SVG,
                "Default font name; resolved against the registry in fonts/"),
    RequiredKey("base.default_missing_icon", "setting", "str", _SVG,
                "Fallback icon name when an event references an unknown icon"),

    # ── layout ──
    RequiredKey("layout.margin.top",    "setting", "str | float", _ALL),
    RequiredKey("layout.margin.right",  "setting", "str | float", _ALL),
    RequiredKey("layout.margin.bottom", "setting", "str | float", _ALL),
    RequiredKey("layout.margin.left",   "setting", "str | float", _ALL),

    # ── events / durations ──
    RequiredKey("events.item_placement_order", "setting", "list[str]", _SVG),

    # ── fiscal ──
    RequiredKey("fiscal.label_format",     "setting", "str", _SVG),
    RequiredKey("fiscal.end_label_format", "setting", "str", _SVG),

    # ── colors ──
    RequiredKey("colors.month_palette",  "setting", "str (DB palette name)", _SVG),
    RequiredKey("colors.fiscal_palette", "setting", "str (DB palette name)", _SVG),
    RequiredKey("colors.group_palette",  "setting", "str (DB palette name)", _SVG),

    # ── weekly ──
    RequiredKey("weekly.week_numbers.label_format", "setting", "str", frozenset({"weekly"})),
    RequiredKey("weekly.overflow.icon",             "setting", "str", frozenset({"weekly"})),

    # ── mini_calendar / mini / mini-icon ──
    RequiredKey("mini_calendar.title_format", "setting", "str (Arrow format)",
                frozenset({"mini", "mini-icon"})),
    RequiredKey("mini_calendar.week_number_label_format", "setting", "str",
                frozenset({"mini", "mini-icon"})),
    RequiredKey("mini_calendar.icon_set", "setting", "str",
                frozenset({"mini-icon"})),

    # ── mini_details ──
    RequiredKey("mini_details.output_suffix", "setting", "str", frozenset({"mini"})),
    RequiredKey("mini_details.title_text",    "setting", "str", frozenset({"mini"})),
    RequiredKey("mini_details.headers",       "setting", "list[str]", frozenset({"mini"})),
    RequiredKey("mini_details.column_widths", "setting", "list[float]", frozenset({"mini"})),

    # ── text_mini ──
    RequiredKey("text_mini.cell_width",        "setting", "int", frozenset({"text-mini"})),
    RequiredKey("text_mini.month_gap",         "setting", "int", frozenset({"text-mini"})),
    RequiredKey("text_mini.event_symbols",     "setting", "list[str]", frozenset({"text-mini"})),
    RequiredKey("text_mini.milestone_symbols", "setting", "list[str]", frozenset({"text-mini"})),
    RequiredKey("text_mini.holiday_symbols",   "setting", "list[str]", frozenset({"text-mini"})),
    RequiredKey("text_mini.nonworkday_symbols", "setting", "list[str]", frozenset({"text-mini"})),

    # ── timeline ──
    RequiredKey("timeline.tick_label_format",   "setting", "str", frozenset({"timeline"})),
    RequiredKey("timeline.today_label_text",    "setting", "str", frozenset({"timeline"})),
    RequiredKey("timeline.marker_radius",       "setting", "float", frozenset({"timeline"})),
    RequiredKey("timeline.icon_size",           "setting", "float", frozenset({"timeline"})),
    RequiredKey("timeline.callout_offset_y",    "setting", "float", frozenset({"timeline"})),
    RequiredKey("timeline.duration_offset_y",   "setting", "float", frozenset({"timeline"})),
    RequiredKey("timeline.duration_lane_gap_y", "setting", "float", frozenset({"timeline"})),

    # ── blockplan ──
    RequiredKey("blockplan.fiscal_year_start_month", "setting", "int", frozenset({"blockplan"})),
    RequiredKey("blockplan.week_start",              "setting", "int", frozenset({"blockplan"})),
    RequiredKey("blockplan.label_column_ratio",      "setting", "float", frozenset({"blockplan"})),
    RequiredKey("blockplan.band_row_height",         "setting", "float", frozenset({"blockplan"})),
    RequiredKey("blockplan.lane_match_mode",         "setting", "first | all",
                frozenset({"blockplan"})),
    RequiredKey("blockplan.show_unmatched_lane",     "setting", "bool", frozenset({"blockplan"})),
    RequiredKey("blockplan.unmatched_lane_name",     "setting", "str", frozenset({"blockplan"})),
    RequiredKey("blockplan.swimlanes",               "setting", "list[{name}]",
                frozenset({"blockplan"})),

    # ── compact_plan ──
    RequiredKey("compact_plan.legend_area_ratio", "setting", "float (0-1)",
                frozenset({"compactplan"})),

    # ── excelheader ──
    RequiredKey("excelheader.font_name",        "setting", "str (system font name)",
                frozenset({"excelheader"})),
    RequiredKey("excelheader.font_size",        "setting", "int", frozenset({"excelheader"})),
    RequiredKey("excelheader.band_row_height",  "setting", "float", frozenset({"excelheader"})),

    # ── time_bands (catalog must exist; may be empty if no placements reference it) ──
    # (No required keys — time_bands is required only insofar as placement lists
    # reference it.  Placement references are validated by the parser.)

    # ── style_rules tokens ──
    # Text tokens required by SVG renderers
    RequiredKey("style_rules:text:base",            "token", "text token", _SVG),
    RequiredKey("style_rules:text:heading",         "token", "text token", _SVG),
    RequiredKey("style_rules:text:body",            "token", "text token", _SVG),
    RequiredKey("style_rules:text:caption",         "token", "text token", _SVG),
    RequiredKey("style_rules:text:label",           "token", "text token", _SVG),
    RequiredKey("style_rules:text:day_number",      "token", "text token",
                frozenset({"weekly", "mini", "mini-icon"})),
    RequiredKey("style_rules:text:month_title",     "token", "text token",
                frozenset({"weekly", "mini", "mini-icon"})),
    RequiredKey("style_rules:text:week_number",     "token", "text token",
                frozenset({"weekly", "mini", "mini-icon"})),
    RequiredKey("style_rules:text:event_name",      "token", "text token", _SVG),
    RequiredKey("style_rules:text:event_notes",     "token", "text token", _SVG),
    RequiredKey("style_rules:text:event_date",      "token", "text token", _SVG),
    RequiredKey("style_rules:text:duration_date",   "token", "text token", _SVG),
    RequiredKey("style_rules:text:holiday_title",   "token", "text token", _SVG),
    RequiredKey("style_rules:text:today_label",     "token", "text token",
                frozenset({"timeline", "blockplan", "compactplan"})),
    RequiredKey("style_rules:text:fiscal_label",    "token", "text token",
                frozenset({"weekly", "blockplan"})),
    RequiredKey("style_rules:text:swimlane_label",  "token", "text token",
                frozenset({"blockplan"})),
    RequiredKey("style_rules:text:band_label",      "token", "text token",
                frozenset({"blockplan", "compactplan"})),
    RequiredKey("style_rules:text:milestone_label", "token", "text token",
                frozenset({"timeline", "blockplan", "compactplan"})),

    # Box tokens
    RequiredKey("style_rules:box:default",          "token", "box token", _SVG),
    RequiredKey("style_rules:box:cell",             "token", "box token", _SVG),
    RequiredKey("style_rules:box:header",           "token", "box token", _SVG),
    RequiredKey("style_rules:box:callout",          "token", "box token",
                frozenset({"timeline"})),
    RequiredKey("style_rules:box:day",              "token", "box token",
                frozenset({"weekly", "mini", "mini-icon"})),
    RequiredKey("style_rules:box:event",            "token", "box token", _SVG),
    RequiredKey("style_rules:box:duration",         "token", "box token", _SVG),
    RequiredKey("style_rules:box:milestone",        "token", "box token",
                frozenset({"timeline", "blockplan", "compactplan"})),
    RequiredKey("style_rules:box:vline",            "token", "box token",
                frozenset({"blockplan"})),
    RequiredKey("style_rules:box:swimlane_heading", "token", "box token",
                frozenset({"blockplan"})),
    RequiredKey("style_rules:box:swimlane_content", "token", "box token",
                frozenset({"blockplan"})),
    RequiredKey("style_rules:box:band",             "token", "box token",
                frozenset({"blockplan", "compactplan"})),

    # Line tokens
    RequiredKey("style_rules:line:grid",      "token", "line token", _SVG),
    RequiredKey("style_rules:line:axis",      "token", "line token",
                frozenset({"timeline", "blockplan", "compactplan"})),
    RequiredKey("style_rules:line:today",     "token", "line token",
                frozenset({"timeline", "blockplan", "compactplan"})),
    RequiredKey("style_rules:line:separator", "token", "line token", _SVG),

    # Icon tokens
    RequiredKey("style_rules:icon:event",     "token", "icon token", _SVG),
    RequiredKey("style_rules:icon:duration",  "token", "icon token", _SVG),
    RequiredKey("style_rules:icon:milestone", "token", "icon token",
                frozenset({"timeline", "blockplan", "compactplan"})),
    RequiredKey("style_rules:icon:overflow",  "token", "icon token",
                frozenset({"weekly"})),
)


# ─── Lookup helpers ─────────────────────────────────────────────────────────


def _get_path(d: dict, path: str) -> object | None:
    """Walk a dotted path through nested dicts.  Returns None if not found."""
    cur: object = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def _token_defined(theme: UnifiedTheme, token_path: str) -> bool:
    """``token_path`` is ``style_rules:<kind>:<name>``."""
    _, _, token = token_path.partition(":")
    # token is now '<kind>:<name>'
    return token in theme.defined_tokens()


# ─── Public API ─────────────────────────────────────────────────────────────


def check_required_keys(
    theme: UnifiedTheme, visualizer: str,
) -> list[RequiredKey]:
    """Return registry entries whose value is missing for ``visualizer``.

    Scoping is lazy per design §11.2: a key is only checked when its
    ``used_by`` set includes the active visualizer.  This means a weekly
    render does not need ``compact_plan.legend_area_ratio`` and vice
    versa.
    """
    missing: list[RequiredKey] = []
    for req in REQUIRED_KEYS:
        if visualizer not in req.used_by:
            continue
        if req.kind == "setting":
            value = _get_path(theme.sections, req.path)
            if value is None:
                missing.append(req)
        elif req.kind == "token":
            if not _token_defined(theme, req.path):
                missing.append(req)
        # Unknown kind would be a registry bug; skip silently.
    return missing


def check_all_visualizers(theme: UnifiedTheme) -> dict[str, list[RequiredKey]]:
    """Convenience: run :func:`check_required_keys` for every visualizer."""
    return {v: check_required_keys(theme, v) for v in sorted(VISUALIZERS)}


# ─── Error formatting (design §11.2) ────────────────────────────────────────


_BASIC_THEME: UnifiedTheme | None = None


def _basic_theme() -> UnifiedTheme:
    """Lazy-load basic.yaml as a UnifiedTheme; cached."""
    global _BASIC_THEME
    if _BASIC_THEME is None:
        from config.unified_theme import load_theme_file
        _BASIC_THEME = load_theme_file(BASIC_YAML_PATH)
    return _BASIC_THEME


def _example_for(req: RequiredKey) -> str:
    """Return a YAML snippet showing how to add the missing key.

    The example value is read from basic.yaml so the error message and the
    reference theme stay in sync.
    """
    basic = _basic_theme()
    if req.kind == "setting":
        value = _get_path(basic.sections, req.path)
        if value is None:
            return f"# (no example value found in basic.yaml for {req.path})"
        # Reconstruct the nested mapping shape so the snippet is paste-ready.
        parts = req.path.split(".")
        nested: object = value
        for part in reversed(parts):
            nested = {part: nested}
        return yaml.safe_dump(nested, sort_keys=False, default_flow_style=False).strip()
    if req.kind == "token":
        _, _, token = req.path.partition(":")
        kind, _, name = token.partition(":")
        style = basic.resolve_token(token)
        snippet = {
            "style_rules": [{
                "name": f"define {token}",
                "define": kind,
                "as": name,
                "style": style or {"# add a style bag matching": basic.resolve_token(token)},
            }]
        }
        return yaml.safe_dump(snippet, sort_keys=False, default_flow_style=False).strip()
    return "# (unknown registry entry kind)"


def format_missing_key_error(
    missing: Iterable[RequiredKey],
    *,
    visualizer: str,
    theme_origin: str = "<theme>",
) -> str:
    """Render the §11.2 error block."""
    missing_list = list(missing)
    if not missing_list:
        return ""
    buf = io.StringIO()
    buf.write(
        f"error: theme {theme_origin!r} is missing {len(missing_list)} required "
        f"setting{'s' if len(missing_list) != 1 else ''} for visualizer "
        f"'{visualizer}'\n\n"
    )
    for req in missing_list:
        buf.write(f"  missing key:   {req.path}\n")
        buf.write(f"  kind:          {req.kind}\n")
        buf.write(f"  type:          {req.type_hint}\n")
        buf.write(f"  used by:       {', '.join(sorted(req.used_by))}\n")
        if req.description:
            buf.write(f"  description:   {req.description}\n")
        buf.write(f"  reference:     config/themes/basic.yaml\n")
        buf.write("\n")
        buf.write("  add to your theme:\n\n")
        for line in _example_for(req).split("\n"):
            buf.write(f"    {line}\n")
        buf.write("\n")
    return buf.getvalue()


__all__ = [
    "BASIC_YAML_PATH",
    "REQUIRED_KEYS",
    "RequiredKey",
    "VISUALIZERS",
    "check_all_visualizers",
    "check_required_keys",
    "format_missing_key_error",
]
