#!/usr/bin/env python3
"""
One-shot migrator that converts CalendarApp themes from the current
(text_styles + box_styles + line_styles + icon_styles + element_styles + axis +
style_rules with apply_to: day_box|duration|vertical_line + swimlane_rules +
per-visualizer inline swimlane/timeband styling) shape into the unified
style_rules schema described in design_unified_style_rules.html.

Per the design (§7.2 / §7.3 / §8.2 / §9.12 / §10.5 / §11.5) the migration is a
single clean break — the live loader will reject any legacy section after this
PR. This script exists so authors can run their themes through once; it is not
imported by the runtime loader.

Usage
-----
    uv run python tools/migrate_theme.py [FILE.yaml ...]
    uv run python tools/migrate_theme.py --in-place [FILE.yaml ...]
    uv run python tools/migrate_theme.py            # all config/themes/*.yaml

With no arguments, every YAML under config/themes/ is converted and written
to config/themes/<name>.converted.yaml so the original stays available for
diffing. With --in-place, the original is overwritten and a .bak copy is left
behind.

Transformations performed
-------------------------
  1.  text_styles.<n>   → style_rules: define: text,  as: <n>
      box_styles.<n>    → style_rules: define: box,   as: <n>
      line_styles.<n>   → style_rules: define: line,  as: <n>
      icon_styles.<n>   → style_rules: define: icon,  as: <n>
  2.  Embedded size_rules on a text style → flat style_rules with select.papersize
      base.size_rule                       → style_rules on text:base
  3.  element_styles.<ec-name>: { foo_style: bar } → style_rules entry
        apply_to: element, select.element, style.use
  4.  apply_to: day_box        → apply_to: box:day
      apply_to: duration       → apply_to: box:duration
      apply_to: vertical_line  → apply_to: box:vline
      apply_to: event          → apply_to: box:event  (and text:event_name from nested text:)
  5.  Property renames everywhere a `style:` block is emitted:
        fill_color       → fill
        stroke_color     → stroke
        stroke_dasharray → dasharray
        timeline_fill_color → fill on box:swimlane_content
        font_size        → size  (inside size_rule and embedded size_rules)
  6.  swimlane_rules entries → style_rules with apply_to: lane, style.swimlane
  7.  blockplan.swimlanes[i].(fill_color / timeline_fill_color / label_*) →
        style_rules entries on box:swimlane_heading / box:swimlane_content /
        text:swimlane_label, keyed by select.swimlane = lane name.
  8.  blockplan.swimlanes[i].match → apply_to: lane rule with the same predicates.
  9.  axis: stanza dissolved per design §8.2.
 10.  Timeband catalog: blockplan.top_time_bands + .bottom_time_bands +
        compact_plan.time_bands + excelheader.top_time_bands are deduplicated
        by structural keys; a top-level time_bands map is emitted; placement
        lists become lists of references.  Per-band styling lifts into
        style_rules on box:band / text:band_label, keyed by select.band.
        excel_font_name / excel_font_size move into excelheader.band_fonts.
 11.  Nested style.text sub-bags inside content rules are flattened into peer
        rules with apply_to: text:<role> using the role-to-target table.
 12.  Section-purpose comments per design §11.5 are emitted at the top of every
        top-level section.

The converter is conservative: every diagnostic it emits goes to stderr and
prefixes lines with "warn:" or "drop:" so authors can grep for them.

Limitations
-----------
* The converter is one-shot; it doesn't try to be idempotent. Running it on
  already-converted output will silently no-op most of the transformations.
* YAML comments in the input are not preserved — the output is regenerated.
* Anchor / alias YAML constructs are not expected in CalendarApp themes; if
  they appear the result may not be what you want.

"""

from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml

# ─── PyYAML dict-order preservation ─────────────────────────────────────────

class _OrderedDumper(yaml.SafeDumper):
    """SafeDumper that keeps insertion order and indents lists nicely."""

    def increase_indent(self, flow=False, indentless=False):  # type: ignore[override]
        return super().increase_indent(flow, False)


def _ordered_dict_representer(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


_OrderedDumper.add_representer(OrderedDict, _ordered_dict_representer)
_OrderedDumper.add_representer(dict, _ordered_dict_representer)


# Force PyYAML to load mappings as regular dicts (insertion-ordered in 3.7+).
class _OrderedLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node):
    loader.flatten_mapping(node)
    return dict(loader.construct_pairs(node))


_OrderedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


# ─── Property and target rename tables ──────────────────────────────────────

PROPERTY_RENAMES: dict[str, str] = {
    "fill_color": "fill",
    "stroke_color": "stroke",
    "stroke_dasharray": "dasharray",
}

# legacy apply_to value -> unified target string
TARGET_RENAMES: dict[str, str] = {
    "day_box": "box:day",
    "duration": "box:duration",
    "vertical_line": "box:vline",
    "event": "box:event",
}

# Role names found in style.text.<role> sub-bags map to text target tokens.
# Source: USER_GUIDE.md "Text Element Reference" table (lines 1158-1172).
TEXT_ROLE_TARGETS: dict[str, str] = {
    "event_name": "text:event_name",
    "event_notes": "text:event_notes",
    "event_date": "text:event_date",
    "duration_name": "text:event_name",
    "duration_notes": "text:event_notes",
    "duration_start_date": "text:duration_date",
    "duration_end_date": "text:duration_date",
    "day_number": "text:day_number",
    "week_number": "text:week_number",
    "month_indicator": "text:month_title",
    "holiday_title": "text:holiday_title",
}

# Section-purpose comments emitted per design §11.5
SECTION_COMMENTS: dict[str, str] = {
    "theme": (
        "Theme metadata: name, version, description; surfaced by --theme lookup\n"
        "and the SVG <desc> element."
    ),
    "base": (
        "Theme-wide defaults: default font family and default missing-icon name."
    ),
    "events": (
        "Event placement policy (item_placement_order); no styling."
    ),
    "durations": (
        "Duration placement / geometry; no styling."
    ),
    "fiscal": (
        "Fiscal calendar semantics: label format and year offset."
    ),
    "colors": (
        "Palette name references (month_palette, fiscal_palette, group_palette)\n"
        "and structural holiday attributes."
    ),
    "layout": (
        "Page margins (numeric points or unit-suffixed values like 0.5in)."
    ),
    "watermark": (
        "Watermark text content and rotation; styling lives in style_rules."
    ),
    "header": "Header non-styling config (text content references); styling lives in style_rules.",
    "footer": "Footer non-styling config (text content references); styling lives in style_rules.",
    "weekly": (
        "Weekly visualizer non-styling config: week-number format, day-name\n"
        "format, overflow icon name."
    ),
    "mini_calendar": (
        "Mini visualizer non-styling config: title format, layout dimensions,\n"
        "icon-set name."
    ),
    "mini_details": (
        "Mini-details non-styling config: column widths, header text,\n"
        "output suffix."
    ),
    "text_mini": (
        "text-mini glyph-set declarations; not an SVG renderer."
    ),
    "timeline": (
        "Timeline non-styling config: tick-label format, axis/callout/lane\n"
        "geometry, today-line content."
    ),
    "timeline_events": "Timeline event geometry (box width/height).",
    "timeline_durations": "Timeline duration geometry (box width/height, lane gap).",
    "blockplan": (
        "Blockplan non-styling config: swimlane name list, label-column ratio,\n"
        "lane match policy, fiscal-year start."
    ),
    "compact_plan": (
        "compactplan non-styling config: axis-relative duration/legend geometry."
    ),
    "excelheader": (
        "XLSX-only config: band-row geometry, system-font names per band\n"
        "(deliberate exception, not style_rules), and Excel cell-border\n"
        "vertical lines."
    ),
    "time_bands": (
        "Shared band catalog referenced by blockplan / compactplan / excelheader\n"
        "placement lists. See design §10."
    ),
    "style_rules": (
        "All visual styling.  Each rule has a select + apply_to + style triple.\n"
        "See design §4 (Unified rule schema) and USER_GUIDE.md Complex Structures\n"
        "Reference for the full vocabulary."
    ),
}

# Canonical order top-level sections are emitted in.
SECTION_ORDER: list[str] = [
    "theme",
    "base",
    "layout",
    "header",
    "footer",
    "events",
    "durations",
    "watermark",
    "fiscal",
    "colors",
    "weekly",
    "mini_calendar",
    "mini_details",
    "text_mini",
    "timeline",
    "timeline_events",
    "timeline_durations",
    "compact_plan",
    "blockplan",
    "excelheader",
    "time_bands",
    "style_rules",
]

# Legacy top-level sections that disappear after migration.
RETIRED_SECTIONS: set[str] = {
    "text_styles",
    "box_styles",
    "line_styles",
    "icon_styles",
    "element_styles",
    "axis",
    "swimlane_rules",
    "icons",
    "patterns",
}

# Keys that survive on the "base" section after migration.
BASE_RETAINED_KEYS: set[str] = {
    "font_family",
    "default_missing_icon",
}

# Section keys that legacy themes set but the unified runtime never reads —
# either because no SECTION_MAPPINGS entry exists for them, or because the
# unified element-binding rules emitted by this migrator (e.g. icon:event
# bound to ec-event-icon) supersede them.  Stripping them at migration time
# keeps the converted YAML legible and matches the post-audit shape of
# TJXcompactplan.yaml (commit 5dce0a66).
#
# Each entry is a leaf key, optionally with a one-level dotted parent
# ("text.font_color") for keys nested inside a sub-bag.
_DEAD_LEGACY_KEYS: dict[str, frozenset[str]] = {
    # No SECTION_MAPPINGS entry under theme_engine — only header.left.* /
    # center.* / right.* (and the footer equivalents) are mapped.  Top-level
    # font_family / font_color on header/footer were always inert.
    "header":       frozenset({"font_family", "font_color"}),
    "footer":       frozenset({"font_family", "font_color"}),
    # Superseded by element bindings in style_rules.
    "events":       frozenset({"icon_color"}),
    "durations":    frozenset({"icon_color", "stroke_dasharray"}),
    "watermark":    frozenset({"color"}),
    "compact_plan": frozenset({
        # → line:axis bound to ec-axis-line
        "axis_color", "axis_dasharray", "axis_opacity",
        # → icon:milestone bound to ec-milestone-marker / ec-milestone-flag
        "milestone_color",
        # → line:axis bound to ec-duration-bar
        "duration_opacity", "duration_stroke_dasharray",
        # → icon:duration bound to ec-duration-icon
        "duration_icon_color",
        # → text:label bound to ec-label
        "text.font_color", "text.font_opacity",
        # → text:body_secondary bound to ec-event-name
        "name_text.font_color", "name_text.font_opacity",
        # Unread by the renderer.
        "palette_name",
        "milestone_list_date_color",
        "milestone_list_section_gap", "continuation_section_gap",
    }),
}


def _strip_dead_keys(section: str, data: Any) -> Any:
    """Return ``data`` with keys listed in :data:`_DEAD_LEGACY_KEYS` removed.

    Supports one-level dotted entries (``text.font_color``) so a nested
    sub-bag can be pruned without dropping the whole sub-bag.  Non-dict
    inputs pass through unchanged.  Returns ``None`` when stripping leaves
    nothing meaningful behind, so the caller can skip writing an empty
    section header.
    """
    dead = _DEAD_LEGACY_KEYS.get(section)
    if not isinstance(data, dict):
        return data
    if not dead:
        return data
    leaf_drops: set[str] = {k for k in dead if "." not in k}
    nested_drops: dict[str, set[str]] = {}
    for k in dead:
        if "." in k:
            parent, _, child = k.partition(".")
            nested_drops.setdefault(parent, set()).add(child)
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k in leaf_drops:
            continue
        if k in nested_drops and isinstance(v, dict):
            sub = {sk: sv for sk, sv in v.items() if sk not in nested_drops[k]}
            if sub:
                out[k] = sub
            continue
        out[k] = v
    return out if out else None


# ─── Helpers ────────────────────────────────────────────────────────────────


def _warn(msg: str, *, fname: str = "") -> None:
    prefix = f"warn[{fname}]: " if fname else "warn: "
    print(prefix + msg, file=sys.stderr)


def _drop(msg: str, *, fname: str = "") -> None:
    prefix = f"drop[{fname}]: " if fname else "drop: "
    print(prefix + msg, file=sys.stderr)


def _rename_props(style: dict[str, Any]) -> dict[str, Any]:
    """Apply property renames (fill_color → fill, etc.) recursively-shallow."""
    out: dict[str, Any] = {}
    for k, v in style.items():
        nk = PROPERTY_RENAMES.get(k, k)
        out[nk] = v
    return out


def _slug(s: str) -> str:
    """Turn a human label into a stable catalog key."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", s.strip()).strip("_").lower()
    return s or "band"


def _canonical_band_signature(band: dict[str, Any]) -> tuple:
    """Structural fingerprint of a timeband for deduplication across visualizers."""
    keep = (
        "unit", "label", "label_format", "date_format", "interval_days",
        "prefix", "start_index", "max_index", "anchor_date", "target_date",
        "start_date", "skip_weekends", "skip_nonworkdays", "show_every",
    )
    return tuple((k, _hashable(band.get(k))) for k in keep)


def _hashable(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_hashable(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _hashable(val)) for k, val in v.items()))
    return v


# ─── Per-section converters ─────────────────────────────────────────────────


def _convert_text_styles(src: dict[str, Any]) -> list[dict[str, Any]]:
    """text_styles.<name> -> [define:text,as:name] + size_rules expansions."""
    rules: list[dict[str, Any]] = []
    for name, props in (src or {}).items():
        if not isinstance(props, dict):
            continue
        body = {k: v for k, v in props.items() if k != "size_rules"}
        # Property renames inside a text style
        body = {("size" if k == "font_size" else k): v for k, v in body.items()}
        rules.append({
            "name": f"define text:{name}",
            "define": "text",
            "as": name,
            "style": body,
        })
        for sr in props.get("size_rules", []) or []:
            when = (sr.get("when") or {})
            new_style: dict[str, Any] = {}
            for k, v in sr.items():
                if k == "when":
                    continue
                if k == "font_size":
                    new_style["size"] = v
                else:
                    new_style[k] = v
            rules.append({
                "name": f"text:{name} — papersize override",
                "apply_to": f"text:{name}",
                "select": when,
                "style": new_style,
            })
    return rules


def _convert_token_section(src: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """box_styles / line_styles / icon_styles -> define rules."""
    rules: list[dict[str, Any]] = []
    for name, props in (src or {}).items():
        if not isinstance(props, dict):
            continue
        body = _rename_props(props)
        rules.append({
            "name": f"define {kind}:{name}",
            "define": kind,
            "as": name,
            "style": body,
        })
    return rules


def _convert_element_styles(src: dict[str, Any], *, fname: str) -> list[dict[str, Any]]:
    """element_styles.<ec-name>: { foo_style: bar } -> element binding rule."""
    rules: list[dict[str, Any]] = []
    for ec_name, binding in (src or {}).items():
        if not isinstance(binding, dict):
            _warn(f"element_styles.{ec_name} is not a mapping; skipped", fname=fname)
            continue
        # Special handling: milestone markers were force-fit onto line_style.
        # Per design §7.3, they convert to icon:milestone with a warning if any
        # property other than `color` survives the line_style binding.
        is_milestone_marker = ec_name in ("ec-milestone-marker", "ec-milestone-flag")
        target_token: str | None = None
        extra_style: dict[str, Any] = {}

        for bk, bv in binding.items():
            if bk == "text_style":
                target_token = f"text:{bv}"
            elif bk == "box_style":
                target_token = f"box:{bv}"
            elif bk == "line_style":
                if is_milestone_marker:
                    target_token = "icon:milestone"
                    if ec_name == "ec-milestone-flag":
                        extra_style["icon"] = "flag"
                else:
                    target_token = f"line:{bv}"
            elif bk == "icon_style":
                target_token = f"icon:{bv}"
            else:
                # treat remaining keys as inline style overrides
                extra_style[PROPERTY_RENAMES.get(bk, bk)] = bv

        if target_token is None:
            _warn(f"element_styles.{ec_name} has no token binding; skipped", fname=fname)
            continue

        style: dict[str, Any] = {"use": target_token}
        style.update(extra_style)
        rules.append({
            "name": f"bind {ec_name} -> {target_token}",
            "apply_to": "element",
            "select": {"element": ec_name},
            "style": style,
        })
    return rules


def _convert_axis_stanza(
    axis: dict[str, Any],
    timeline: dict[str, Any],
    *,
    fname: str,
) -> list[dict[str, Any]]:
    """Per design §8.2: dissolve axis: into element bindings, tokens, or no-ops."""
    if not isinstance(axis, dict):
        return []
    rules: list[dict[str, Any]] = []

    if axis.get("line_style"):
        rules.append({
            "name": "bind ec-axis-line",
            "apply_to": "element",
            "select": {"element": "ec-axis-line"},
            "style": {"use": f"line:{axis['line_style']}"},
        })

    tick = axis.get("tick") or {}
    if isinstance(tick, dict):
        if tick.get("color"):
            rules.append({
                "name": "define line:tick",
                "define": "line",
                "as": "tick",
                "style": {"color": tick["color"], "width": 0.5, "opacity": 1.0},
            })
            rules.append({
                "name": "bind ec-axis-tick",
                "apply_to": "element",
                "select": {"element": "ec-axis-tick"},
                "style": {"use": "line:tick"},
            })
        if tick.get("label_style"):
            rules.append({
                "name": "bind ec-tick-label",
                "apply_to": "element",
                "select": {"element": "ec-tick-label"},
                "style": {"use": f"text:{tick['label_style']}"},
            })
        if "date_format" in tick:
            tl = (timeline or {}).get("tick_label_format")
            if tl is not None and tl != tick["date_format"]:
                _warn(
                    "axis.tick.date_format disagrees with timeline.tick_label_format; "
                    "keeping the timeline value",
                    fname=fname,
                )
            _drop("axis.tick.date_format (kept under timeline.tick_label_format)", fname=fname)

    today = axis.get("today") or {}
    if isinstance(today, dict):
        if today.get("line_style"):
            rules.append({
                "name": "bind ec-today-line",
                "apply_to": "element",
                "select": {"element": "ec-today-line"},
                "style": {"use": f"line:{today['line_style']}"},
            })
        if today.get("label_color"):
            rules.append({
                "name": "today label color",
                "apply_to": "text:today_label",
                "style": {"color": today["label_color"]},
            })
        if "label_text" in today:
            tl = (timeline or {}).get("today_label_text")
            if tl is not None and tl != today["label_text"]:
                _warn(
                    "axis.today.label_text disagrees with timeline.today_label_text; "
                    "keeping the timeline value",
                    fname=fname,
                )
            _drop("axis.today.label_text (kept under timeline.today_label_text)", fname=fname)

    return rules


def _convert_base_size_rule(base: dict[str, Any]) -> list[dict[str, Any]]:
    sr_list = base.get("size_rule") if isinstance(base, dict) else None
    if not sr_list:
        return []
    rules = []
    for sr in sr_list:
        when = sr.get("when", {})
        body = {("size" if k == "font_size" else k): v for k, v in sr.items() if k != "when"}
        rules.append({
            "name": "base font — papersize override",
            "apply_to": "text:base",
            "select": when,
            "style": body,
        })
    return rules


def _flatten_text_subbag(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per design §9.12: nested style.text → peer rules with apply_to: text:<role>."""
    out: list[dict[str, Any]] = []
    for rule in rules:
        style = rule.get("style") or {}
        text_block = style.get("text") if isinstance(style, dict) else None
        if not isinstance(text_block, dict):
            out.append(rule)
            continue
        # Copy the rule without the text block (and without the flat text
        # shorthand keys; they expand into peer rules too).
        flat_text_shorthand = {
            k: style[k] for k in ("font", "font_size", "font_color", "font_opacity")
            if k in style
        }
        base_style = {
            k: v for k, v in style.items()
            if k not in ("text", "font", "font_size", "font_color", "font_opacity")
        }
        if base_style:
            base_rule = dict(rule)
            base_rule["style"] = _rename_props(base_style)
            out.append(base_rule)
        for role, role_style in text_block.items():
            target = TEXT_ROLE_TARGETS.get(role)
            if target is None:
                _warn(f"unknown style.text.{role} role; emitted with text:{role}")
                target = f"text:{role}"
            # Property rename inside role_style for shorthand keys
            merged = dict(flat_text_shorthand)
            if isinstance(role_style, dict):
                merged.update(role_style)
            # Property name normalization: font_color -> color, font_size -> size, font -> font
            normalized: dict[str, Any] = {}
            for k, v in merged.items():
                if k == "font_color":
                    normalized["color"] = v
                elif k == "font_size":
                    normalized["size"] = v
                elif k == "font_opacity":
                    normalized["opacity"] = v
                else:
                    normalized[k] = v
            peer = {
                "name": f"{rule.get('name', '')} — {role}".strip(" —"),
                "apply_to": target,
                "select": rule.get("select", {}),
                "style": normalized,
            }
            out.append(peer)
    return out


def _convert_style_rules(rules: list[Any]) -> list[dict[str, Any]]:
    """Walk existing style_rules: retarget, rename props, flatten text sub-bag."""
    converted: list[dict[str, Any]] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        new = dict(rule)
        # apply_to: rename day_box/duration/vertical_line/event -> box:* targets
        at = rule.get("apply_to")
        if isinstance(at, list):
            new["apply_to"] = [TARGET_RENAMES.get(t, t) for t in at]
        elif isinstance(at, str):
            new["apply_to"] = TARGET_RENAMES.get(at, at)
        # style: property renames; the flatten pass picks up nested text:
        style = rule.get("style")
        if isinstance(style, dict):
            new["style"] = _rename_props(style)
        converted.append(new)
    return _flatten_text_subbag(converted)


def _convert_swimlane_rules(rules: list[Any]) -> list[dict[str, Any]]:
    """swimlane_rules -> apply_to: lane, style: {swimlane: name}."""
    out: list[dict[str, Any]] = []
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        out.append({
            "name": r.get("name", "route swimlane"),
            "apply_to": "lane",
            "select": r.get("select", {}),
            "style": {"swimlane": r.get("apply_to", "")},
        })
    return out


def _convert_swimlane_visuals(swimlanes: list[Any], *, fname: str) -> list[dict[str, Any]]:
    """Per design §9.9: lift swimlane visual props into style_rules entries."""
    out: list[dict[str, Any]] = []
    for lane in swimlanes or []:
        if not isinstance(lane, dict):
            continue
        lane_name = lane.get("name")
        if not lane_name:
            continue
        select = {"swimlane": lane_name}
        if lane.get("fill_color") not in (None, "none"):
            out.append({
                "name": f"swimlane {lane_name} — heading",
                "apply_to": "box:swimlane_heading",
                "select": select,
                "style": {"fill": lane["fill_color"]},
            })
        if lane.get("timeline_fill_color") not in (None, "none"):
            out.append({
                "name": f"swimlane {lane_name} — content",
                "apply_to": "box:swimlane_content",
                "select": select,
                "style": {"fill": lane["timeline_fill_color"]},
            })
        label_style: dict[str, Any] = {}
        if lane.get("label_color") is not None:
            label_style["color"] = lane["label_color"]
        if lane.get("label_align_h") is not None:
            label_style["align_h"] = lane["label_align_h"]
        if lane.get("label_align_v") is not None:
            label_style["align_v"] = lane["label_align_v"]
        if lane.get("label_rotation") is not None:
            label_style["rotation"] = lane["label_rotation"]
        if label_style:
            out.append({
                "name": f"swimlane {lane_name} — label",
                "apply_to": "text:swimlane_label",
                "select": select,
                "style": label_style,
            })
        if isinstance(lane.get("match"), dict):
            out.append({
                "name": f"route to swimlane {lane_name}",
                "apply_to": "lane",
                "select": dict(lane["match"]),
                "style": {"swimlane": lane_name},
            })
    return out


def _strip_swimlane_visuals(swimlanes: list[Any]) -> list[dict[str, Any]]:
    """Keep only structural keys (name, split_ratio) on each lane."""
    out: list[dict[str, Any]] = []
    for lane in swimlanes or []:
        if not isinstance(lane, dict):
            continue
        keep = {}
        for k in ("name", "split_ratio"):
            if k in lane:
                keep[k] = lane[k]
        out.append(keep)
    return out


# ─── Timeband catalog (design §10) ──────────────────────────────────────────


_BAND_STRUCTURAL_KEYS: tuple[str, ...] = (
    "unit", "label", "label_format", "date_format", "interval_days",
    "prefix", "start_index", "max_index", "anchor_date", "target_date",
    "start_date", "skip_weekends", "skip_nonworkdays", "show_every",
    "label_values",
)
_BAND_GEOMETRY_KEYS: tuple[str, ...] = ("row_height",)
_BAND_STYLE_KEYS: tuple[str, ...] = (
    "fill_color", "alt_fill_color", "font_color", "font_size",
    "label_color", "label_fill_color", "label_align_h",
    "font", "font_opacity", "label_font", "label_font_size",
    "label_opacity", "stroke_color",
)
_BAND_XLSX_KEYS: tuple[str, ...] = ("excel_font_name", "excel_font_size")


def _band_structural(b: dict[str, Any]) -> dict[str, Any]:
    return {k: b[k] for k in _BAND_STRUCTURAL_KEYS if k in b}


def _band_style(b: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in _BAND_STYLE_KEYS:
        if k in b:
            out[PROPERTY_RENAMES.get(k, k)] = b[k]
    return out


class _TimebandCatalog:
    """Accumulator that deduplicates bands by structural signature."""

    def __init__(self) -> None:
        self._by_sig: dict[tuple, str] = {}
        self._entries: dict[str, dict[str, Any]] = {}
        self._used_labels: set[str] = set()

    def _make_key(self, band: dict[str, Any]) -> str:
        base = _slug(band.get("label") or band.get("unit") or "band")
        key = base
        i = 2
        while key in self._used_labels and self._entries.get(key) is not None:
            key = f"{base}_{i}"
            i += 1
        self._used_labels.add(key)
        return key

    def ingest(self, band: dict[str, Any]) -> str:
        sig = _canonical_band_signature(band)
        if sig in self._by_sig:
            return self._by_sig[sig]
        key = self._make_key(band)
        self._by_sig[sig] = key
        self._entries[key] = _band_structural(band)
        return key

    def to_yaml_mapping(self) -> OrderedDict:
        if not self._entries:
            return OrderedDict()
        out: OrderedDict[str, Any] = OrderedDict()
        for k, v in self._entries.items():
            out[k] = v
        return out


def _convert_timebands(
    *,
    blockplan: dict[str, Any] | None,
    compact_plan: dict[str, Any] | None,
    excelheader: dict[str, Any] | None,
    catalog: _TimebandCatalog,
) -> tuple[
    dict[str, list[dict[str, Any] | str]],  # blockplan placements
    list[dict[str, Any] | str] | None,        # compact_plan.bands
    list[dict[str, Any] | str] | None,        # excelheader.top_bands
    dict[str, dict[str, Any]],                  # excelheader.band_fonts
    list[dict[str, Any]],                       # style_rules entries for band styling
]:
    """Walk every legacy band list, deduplicate into the catalog, return refs."""
    style_rules: list[dict[str, Any]] = []
    seen_styling_for: set[str] = set()

    def _process_list(bands: list[Any] | None, visualizer: str) -> list[dict[str, Any] | str]:
        refs: list[dict[str, Any] | str] = []
        if not isinstance(bands, list):
            return refs
        for b in bands:
            if not isinstance(b, dict):
                continue
            key = catalog.ingest(b)
            ref: dict[str, Any] | str
            geo = {gk: b[gk] for gk in _BAND_GEOMETRY_KEYS if gk in b}
            if geo:
                geo_with_band = OrderedDict([("band", key)])
                for k, v in geo.items():
                    geo_with_band[k] = v
                ref = dict(geo_with_band)
            else:
                ref = key
            refs.append(ref)
            style = _band_style(b)
            if style and key not in seen_styling_for:
                seen_styling_for.add(key)
                box_style = {k: v for k, v in style.items() if k in ("fill", "stroke", "fill_palette", "dasharray")}
                text_style: dict[str, Any] = {}
                if "font_color" in b:
                    text_style["color"] = b["font_color"]
                if "label_color" in b:
                    text_style.setdefault("color", b["label_color"])
                if "font_size" in b:
                    text_style["size"] = b["font_size"]
                if "font" in b:
                    text_style["font"] = b["font"]
                if box_style:
                    style_rules.append({
                        "name": f"band {key} — segment",
                        "apply_to": "box:band",
                        "select": {"band": key},
                        "style": box_style,
                    })
                if text_style:
                    style_rules.append({
                        "name": f"band {key} — label",
                        "apply_to": "text:band_label",
                        "select": {"band": key},
                        "style": text_style,
                    })
        return refs

    blockplan_placements: dict[str, list[dict[str, Any] | str]] = {}
    if isinstance(blockplan, dict):
        for src_key, dst_key in (("top_time_bands", "top_bands"), ("bottom_time_bands", "bottom_bands"), ("time_bands", "bands")):
            placements = _process_list(blockplan.get(src_key), "blockplan")
            if placements:
                blockplan_placements[dst_key] = placements

    compact_placements: list[dict[str, Any] | str] | None = None
    if isinstance(compact_plan, dict):
        cp = _process_list(compact_plan.get("time_bands"), "compactplan")
        if cp:
            compact_placements = cp

    excel_placements: list[dict[str, Any] | str] | None = None
    excel_band_fonts: dict[str, dict[str, Any]] = {}
    if isinstance(excelheader, dict):
        bands = excelheader.get("top_time_bands") or []
        ep = _process_list(bands, "excelheader")
        if ep:
            excel_placements = ep
        # Move excel_font_name / excel_font_size into band_fonts keyed by catalog
        for b in bands:
            if not isinstance(b, dict):
                continue
            xfont = {k: b[k] for k in _BAND_XLSX_KEYS if k in b}
            if xfont:
                key = catalog.ingest(b)
                excel_band_fonts[key] = xfont

    return blockplan_placements, compact_placements, excel_placements, excel_band_fonts, style_rules


# ─── Top-level converter ────────────────────────────────────────────────────


def convert_theme(src: dict[str, Any], *, fname: str = "") -> OrderedDict:
    """Produce the unified theme dict from a legacy theme dict."""
    out: OrderedDict[str, Any] = OrderedDict()
    style_rules: list[dict[str, Any]] = []

    # 1. theme metadata, unchanged
    if isinstance(src.get("theme"), dict):
        out["theme"] = dict(src["theme"])

    # 2. base — strip size_rule (becomes style_rules), keep retained keys
    if isinstance(src.get("base"), dict):
        base_raw = src["base"]
        kept = {k: v for k, v in base_raw.items() if k in BASE_RETAINED_KEYS}
        if kept:
            out["base"] = kept
        style_rules.extend(_convert_base_size_rule(base_raw))

    # 3. layout / header / footer / events / durations / watermark / fiscal / colors
    #    Non-styling content carries through; styling lifts into style_rules.
    #    _strip_dead_keys drops keys the unified runtime no longer reads
    #    (see _DEAD_LEGACY_KEYS); a section that empties out is skipped.
    for sec in ("layout", "header", "footer", "events", "durations", "watermark", "fiscal", "colors"):
        if sec in src and src[sec] is not None:
            stripped = _strip_dead_keys(sec, src[sec])
            if stripped is not None:
                out[sec] = stripped

    # 4. Token definitions (text_styles, box_styles, line_styles, icon_styles)
    style_rules.extend(_convert_text_styles(src.get("text_styles") or {}))
    style_rules.extend(_convert_token_section(src.get("box_styles") or {}, "box"))
    style_rules.extend(_convert_token_section(src.get("line_styles") or {}, "line"))
    style_rules.extend(_convert_token_section(src.get("icon_styles") or {}, "icon"))

    # 5. Axis stanza dissolution
    style_rules.extend(_convert_axis_stanza(src.get("axis"), src.get("timeline") or {}, fname=fname))

    # 6. Element styles -> binding rules
    style_rules.extend(_convert_element_styles(src.get("element_styles") or {}, fname=fname))

    # 7. Per-visualizer non-styling config (weekly, mini_calendar, …) carries through
    #    minus its styling keys; the per-visualizer keys are very heterogeneous so
    #    we copy as-is and rely on the live loader's validation to catch the diff.
    #    _strip_dead_keys removes unified-runtime-superseded keys (see
    #    _DEAD_LEGACY_KEYS); compact_plan gets a second strip pass below
    #    after band-placement assembly, because its loop also drops time_bands.
    for sec in ("weekly", "mini_calendar", "mini_details", "text_mini",
                "timeline", "timeline_events", "timeline_durations",
                "compact_plan"):
        if sec in src and src[sec] is not None:
            stripped = _strip_dead_keys(sec, src[sec])
            if stripped is not None:
                out[sec] = stripped

    # 8. Blockplan — split swimlane visuals out, then keep the rest (sans timebands)
    blockplan_in = src.get("blockplan") if isinstance(src.get("blockplan"), dict) else None
    excelheader_in = src.get("excelheader") if isinstance(src.get("excelheader"), dict) else None
    compact_in = src.get("compact_plan") if isinstance(src.get("compact_plan"), dict) else None

    # 9. Timeband catalog consolidation (design §10)
    catalog = _TimebandCatalog()
    bp_placements, cp_placements, ex_placements, ex_band_fonts, band_style_rules = _convert_timebands(
        blockplan=blockplan_in, compact_plan=compact_in, excelheader=excelheader_in, catalog=catalog,
    )
    style_rules.extend(band_style_rules)

    if blockplan_in is not None:
        bp_out: OrderedDict[str, Any] = OrderedDict()
        for k, v in blockplan_in.items():
            if k in ("top_time_bands", "bottom_time_bands", "time_bands"):
                continue
            if k == "swimlanes":
                style_rules.extend(_convert_swimlane_visuals(v, fname=fname))
                bp_out["swimlanes"] = _strip_swimlane_visuals(v)
                continue
            bp_out[k] = v
        for dst_key, refs in bp_placements.items():
            bp_out[dst_key] = refs
        out["blockplan"] = bp_out

    if excelheader_in is not None:
        eh_out: OrderedDict[str, Any] = OrderedDict()
        for k, v in excelheader_in.items():
            if k == "top_time_bands":
                continue
            eh_out[k] = v
        if ex_placements is not None:
            eh_out["top_bands"] = ex_placements
        if ex_band_fonts:
            eh_out["band_fonts"] = ex_band_fonts
        out["excelheader"] = eh_out

    if compact_in is not None and cp_placements is not None:
        # _strip_dead_keys removes superseded-by-style_rules and unread keys;
        # we additionally drop the legacy time_bands sub-bag because the
        # placements are emitted as `bands:` below.
        stripped = _strip_dead_keys("compact_plan", compact_in) or {}
        cp_out = OrderedDict()
        for k, v in stripped.items():
            if k == "time_bands":
                continue
            cp_out[k] = v
        cp_out["bands"] = cp_placements
        out["compact_plan"] = cp_out

    # 10. Top-level time_bands catalog
    catalog_map = catalog.to_yaml_mapping()
    if catalog_map:
        out["time_bands"] = catalog_map

    # 11. Existing style_rules (retarget, rename, flatten text sub-bag)
    style_rules.extend(_convert_style_rules(src.get("style_rules") or []))

    # 12. swimlane_rules -> apply_to: lane rules
    style_rules.extend(_convert_swimlane_rules(src.get("swimlane_rules") or []))

    if style_rules:
        out["style_rules"] = style_rules

    # Warn on unrecognized retired sections (we silently drop most legacy bits;
    # this is a last-chance signal).
    for k in src:
        if k in RETIRED_SECTIONS or k in SECTION_ORDER or k == "base":
            continue
        _warn(f"unknown top-level key '{k}' carried through unchanged", fname=fname)
        out[k] = src[k]

    # Final pass: backfill any missing required keys from basic.yaml so the
    # converted theme is complete enough to load under the unified parser.
    # See design §11.4 — basic.yaml is the single source of truth for
    # "what's required, with a sensible default."
    _backfill_from_basic(out, fname=fname)

    return out


# ─── Backfill missing required keys from basic.yaml ─────────────────────────


_BASIC_CACHE: dict[str, Any] | None = None
_BASIC_TOKEN_CACHE: dict[str, dict[str, Any]] | None = None


def _basic_theme_data() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load basic.yaml once and cache the section dict + token style map."""
    global _BASIC_CACHE, _BASIC_TOKEN_CACHE
    if _BASIC_CACHE is None or _BASIC_TOKEN_CACHE is None:
        basic_path = Path(__file__).resolve().parent.parent / "config" / "themes" / "basic.yaml"
        raw = yaml.load(basic_path.read_text(), Loader=_OrderedLoader) or {}
        # Build a token map: "<kind>:<name>" -> style bag (last-write-wins; basic.yaml
        # only has unconditional definitions so this is fine).
        tokens: dict[str, dict[str, Any]] = {}
        for rule in (raw.get("style_rules") or []):
            if not isinstance(rule, dict):
                continue
            kind = rule.get("define")
            name = rule.get("as")
            style = rule.get("style") or {}
            if kind and name and isinstance(style, dict):
                tokens[f"{kind}:{name}"] = dict(style)
        _BASIC_CACHE = raw
        _BASIC_TOKEN_CACHE = tokens
    return _BASIC_CACHE, _BASIC_TOKEN_CACHE


def _ensure_nested_path(out: OrderedDict, path: str, value: Any) -> None:
    """Insert ``value`` at the dotted ``path`` in ``out``, creating parent maps."""
    parts = path.split(".")
    cur: Any = out
    for part in parts[:-1]:
        existing = cur.get(part)
        if not isinstance(existing, (dict, OrderedDict)):
            new_map: OrderedDict[str, Any] = OrderedDict()
            cur[part] = new_map
            cur = new_map
        else:
            cur = existing
    cur[parts[-1]] = value


def _read_path(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def _path_has_value(d: dict[str, Any], path: str) -> bool:
    """True if ``path`` exists AND its value is not None.

    Explicit ``null`` values in legacy themes (``base.default_missing_icon: null``,
    ``text_mini.event_symbols: null``) are treated as "absent" so the backfill
    replaces them — None is never a useful runtime value for a required key.
    """
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return cur is not None


def _backfill_from_basic(out: OrderedDict, *, fname: str) -> None:
    """Fill any required key still missing in ``out`` with the value from basic.yaml.

    Imports the required-keys registry from config.required_keys at call time
    to avoid a hard import cycle (config.required_keys imports unified_theme,
    not this module).
    """
    try:
        from config.required_keys import REQUIRED_KEYS  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        _warn(f"could not load required-keys registry for backfill: {exc}", fname=fname)
        return

    basic_sections, basic_tokens = _basic_theme_data()

    # Build the set of tokens already defined in out['style_rules'].
    defined_tokens: set[str] = set()
    for rule in out.get("style_rules", []) or []:
        if isinstance(rule, dict) and rule.get("define") and rule.get("as"):
            defined_tokens.add(f"{rule['define']}:{rule['as']}")

    style_rules = out.setdefault("style_rules", [])

    backfilled_settings: list[str] = []
    backfilled_tokens: list[str] = []
    for req in REQUIRED_KEYS:
        if req.kind == "setting":
            if _path_has_value(out, req.path):
                continue
            value = _read_path(basic_sections, req.path)
            if value is None:
                continue
            _ensure_nested_path(out, req.path, value)
            backfilled_settings.append(req.path)
        elif req.kind == "token":
            # path like "style_rules:text:day_number"
            _, _, token = req.path.partition(":")
            if token in defined_tokens:
                continue
            style = basic_tokens.get(token)
            if style is None:
                continue
            kind, _, name = token.partition(":")
            style_rules.append({
                "name": f"define {token}  # backfilled from basic.yaml",
                "define": kind,
                "as": name,
                "style": dict(style),
            })
            defined_tokens.add(token)
            backfilled_tokens.append(token)

    if backfilled_settings:
        _warn(
            f"backfilled {len(backfilled_settings)} required setting(s) from basic.yaml: "
            f"{', '.join(backfilled_settings[:6])}"
            + (f" (+{len(backfilled_settings) - 6} more)" if len(backfilled_settings) > 6 else ""),
            fname=fname,
        )
    if backfilled_tokens:
        _warn(
            f"backfilled {len(backfilled_tokens)} token(s) from basic.yaml: "
            f"{', '.join(backfilled_tokens[:6])}"
            + (f" (+{len(backfilled_tokens) - 6} more)" if len(backfilled_tokens) > 6 else ""),
            fname=fname,
        )


# ─── Emission with section-purpose comments ─────────────────────────────────


def _emit_section(section: str, value: Any) -> str:
    """Render one top-level section as YAML, preceded by its purpose comment."""
    header_line = f"# ─── {section} " + "─" * max(0, 70 - len(section)) + "\n"
    purpose = SECTION_COMMENTS.get(section)
    if purpose:
        purpose_block = "\n".join(f"# {line}" for line in purpose.split("\n")) + "\n"
    else:
        purpose_block = ""
    body = yaml.dump(
        {section: value},
        Dumper=_OrderedDumper,
        sort_keys=False,
        default_flow_style=False,
        width=120,
        allow_unicode=True,
    )
    return header_line + purpose_block + body + "\n"


def emit_theme(theme: OrderedDict) -> str:
    parts: list[str] = []
    parts.append("# Generated by tools/migrate_theme.py — see design_unified_style_rules.html\n\n")
    seen: set[str] = set()
    for section in SECTION_ORDER:
        if section not in theme:
            continue
        parts.append(_emit_section(section, theme[section]))
        seen.add(section)
    for k in theme:
        if k in seen:
            continue
        parts.append(_emit_section(k, theme[k]))
    return "".join(parts)


# ─── Driver ─────────────────────────────────────────────────────────────────


def _convert_file(path: Path, *, in_place: bool) -> Path:
    src = yaml.load(path.read_text(), Loader=_OrderedLoader) or {}
    converted = convert_theme(src, fname=path.name)
    output = emit_theme(converted)
    if in_place:
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(path.read_text())
        path.write_text(output)
        return path
    out_path = path.with_suffix(".converted.yaml")
    out_path.write_text(output)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else "")
    parser.add_argument("files", nargs="*", help="Theme YAML files to convert (default: all in-tree themes)")
    parser.add_argument("--in-place", action="store_true", help="Overwrite input files, leaving a .bak copy")
    parser.add_argument("--print", action="store_true", help="Print converted YAML to stdout instead of writing files")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        paths = sorted(
            p for p in (repo_root / "config" / "themes").glob("*.yaml")
            if not p.name.endswith(".converted.yaml")
        )

    exit_code = 0
    for p in paths:
        try:
            if args.print:
                src = yaml.load(p.read_text(), Loader=_OrderedLoader) or {}
                converted = convert_theme(src, fname=p.name)
                sys.stdout.write(f"# === {p.name} ===\n")
                sys.stdout.write(emit_theme(converted))
                sys.stdout.write("\n")
            else:
                out = _convert_file(p, in_place=args.in_place)
                try:
                    rel = out.resolve().relative_to(repo_root)
                except ValueError:
                    rel = out
                print(f"{p.name} -> {rel}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"error[{p.name}]: {exc}", file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
