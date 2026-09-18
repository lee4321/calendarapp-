"""
Compact Activities Plan SVG renderer.

Renders a compressed timeline with duration lines above/below a central axis
and milestone flag markers.  What each bar, flag and symbol stands for is
recorded as the chart draws it and written to the run's details document
(see :mod:`renderers.details_record`).
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

import arrow
import drawsvg

from config.config import get_font_path, resolve_continuation_icon
from renderers.svg_base import BaseSVGRenderer, _is_none_color
from renderers.text_utils import fit_lines, shrinktext, string_width, text_center_baseline
from shared.data_models import Event
from shared.date_utils import format_arrow_date, visible_days
from shared.day_classifier import classify_day
from shared.holiday_band import compute_holiday_band_days
from shared.icon_band import compute_icon_band_days
from shared.rule_engine import ColorRuleEngine, StyleEngine, StyleResult
from shared.timeband import (
    BandSegment as _BandSegment,
)
from shared.timeband import (
    build_segments as _build_band_segments,
)
from shared.timeband import (
    group_segments as _group_band_segments,
)

# Clear space kept after a milestone label before the next one may share
# its lane, and the label line height as a multiple of the font size.
_MILESTONE_LABEL_GAP = 6.0
_MILESTONE_LABEL_LINE_RATIO = 1.25
_MILESTONE_PENNANT_RATIO = 0.7

# Clear space between a milestone's stem and the icon standing in for its
# pennant, and between the topmost such icon and the header bands.
_MILESTONE_ICON_GAP = 0.5
_MILESTONE_ICON_HEADER_CLEARANCE = 1.0

# Clear space between the ink of two adjacent duration rows.
_DURATION_ROW_GAP = 1.5

# A bar's text: the clear space between its start icon and name, and the
# smallest a date or name may shrink to fit its column before the name is
# cut short (a date that still does not fit is left out).
_BAR_ICON_GAP = 1.5
_BAR_MIN_FONT_SIZE = 3.0

# Clear space between the top of the activity band and the lowest
# milestone pennant, so labels never land on a duration bar.
_MILESTONE_BAND_CLEARANCE = 3.0

# ─── Color helpers (named + hex → RGB → luminance) ──────────────────────────
# A small CSS-named-color → RGB table covering the values that turn up in the
# in-tree themes (palettes + theme.colors).  Anything outside this table that
# isn't a hex literal is treated as "unknown" — the contrast code then leaves
# the icon color alone, which preserves backward behaviour for exotic names.

_NAMED_COLORS: dict[str, tuple[int, int, int] | None] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "grey": (128, 128, 128),
    "gray": (128, 128, 128),
    "lightgrey": (211, 211, 211),
    "lightgray": (211, 211, 211),
    "darkgrey": (169, 169, 169),
    "darkgray": (169, 169, 169),
    "dimgrey": (105, 105, 105),
    "dimgray": (105, 105, 105),
    "slategrey": (112, 128, 144),
    "slategray": (112, 128, 144),
    "navy": (0, 0, 128),
    "midnightblue": (25, 25, 112),
    "blue": (0, 0, 255),
    "darkblue": (0, 0, 139),
    "steelblue": (70, 130, 180),
    "lightsteelblue": (176, 196, 222),
    "dodgerblue": (30, 144, 255),
    "deepskyblue": (0, 191, 255),
    "lightblue": (173, 216, 230),
    "powderblue": (176, 224, 230),
    "red": (255, 0, 0),
    "darkred": (139, 0, 0),
    "firebrick": (178, 34, 34),
    "tomato": (255, 99, 71),
    "coral": (255, 127, 80),
    "salmon": (250, 128, 114),
    "pink": (255, 192, 203),
    "gold": (255, 215, 0),
    "goldenrod": (218, 165, 32),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),
    "darkorange": (255, 140, 0),
    "green": (0, 128, 0),
    "darkgreen": (0, 100, 0),
    "limegreen": (50, 205, 50),
    "mediumseagreen": (60, 179, 113),
    "springgreen": (0, 255, 127),
    "bisque": (255, 228, 196),
    "purple": (128, 0, 128),
    "darkmagenta": (139, 0, 139),
    "deeppink": (255, 20, 147),
    "mediumpurple": (147, 112, 219),
    "none": None,
    "transparent": None,
}


def _color_to_rgb(value: str | None) -> tuple[int, int, int] | None:
    """Resolve a CSS color string to (r, g, b) ints; return ``None`` for unknown.

    Accepts ``#rgb``, ``#rrggbb``, and the named-color subset above.  Case
    insensitive; whitespace is stripped.
    """
    if not value:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            try:
                return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16))
            except ValueError:
                return None
        if len(h) == 6:
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except ValueError:
                return None
        return None
    return _NAMED_COLORS.get(s)


def _colors_equivalent(a: str | None, b: str | None) -> bool:
    """True when ``a`` and ``b`` resolve to the same RGB tuple.

    Returns False whenever either color is unknown to ``_color_to_rgb`` —
    callers should treat the colors as distinct in that case to preserve
    existing rendering.
    """
    ra = _color_to_rgb(a)
    rb = _color_to_rgb(b)
    return ra is not None and rb is not None and ra == rb


def _contrast_color(bg: str | None, *, dark: str = "black", light: str = "white") -> str:
    """Pick a foreground color (``dark`` or ``light``) that contrasts ``bg``.

    Uses the standard 0.2126 R + 0.7152 G + 0.0722 B luminance formula on the
    8-bit RGB values.  Unknown / transparent backgrounds default to ``dark``
    (same as picking against white).
    """
    rgb = _color_to_rgb(bg)
    if rgb is None:
        return dark
    r, g, b = rgb
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return light if luminance < 128 else dark


def _resolve_icon_on_bar(
    *,
    style_override: str | None,
    configured: str,
    bar_color: str,
) -> str:
    """Pick an icon color that won't disappear against its bar background.

    Precedence:
      1. ``style_override`` (a rule-engine explicit color) always wins.
      2. ``configured`` (the theme's icon:duration color) is used when set —
         unless it matches the bar color, in which case we swap to a
         contrasting color so the glyph stays visible.
      3. Bar color as a last resort, swapped to a contrasting color so the
         glyph never paints navy-on-navy.
    """
    if style_override:
        return style_override
    candidate = configured if configured else bar_color
    if _colors_equivalent(candidate, bar_color):
        return _contrast_color(bar_color)
    return candidate


def _resolve_style_rules(config: CalendarConfig) -> list:
    """Source the raw style_rules list for StyleEngine.

    Prefers the parsed UnifiedTheme (``config.theme``) so the renderer no
    longer depends on the legacy ``theme_style_rules`` decompiler bridge.
    """
    theme = getattr(config, "theme", None)
    if theme is not None:
        rules = theme.sections.get("style_rules")
        if isinstance(rules, list):
            return rules
    return list(getattr(config, "theme_style_rules", None) or [])


def _nwd_fill_for_classes(
    classes: frozenset[str],
    config: CalendarConfig,
) -> str | None:
    """Resolve a non-workday fill override for a single-day cell.

    Priority: federal_holiday → company_holiday → weekend.  Returns ``None``
    when the day has no non-workday classes or no override is configured.
    """
    if not classes:
        return None
    if "federal_holiday" in classes and config.compactplan_federal_holiday_fill_color:
        return config.compactplan_federal_holiday_fill_color
    if "company_holiday" in classes and config.compactplan_company_holiday_fill_color:
        return config.compactplan_company_holiday_fill_color
    if "weekend" in classes and config.compactplan_weekend_fill_color:
        return config.compactplan_weekend_fill_color
    return None


def _nwd_fill_opacity_for_classes(
    classes: frozenset[str],
    config: CalendarConfig,
) -> float | None:
    if not classes:
        return None
    if "federal_holiday" in classes and config.compactplan_federal_holiday_fill_color:
        return config.compactplan_federal_holiday_fill_opacity
    if "company_holiday" in classes and config.compactplan_company_holiday_fill_color:
        return config.compactplan_company_holiday_fill_opacity
    if "weekend" in classes and config.compactplan_weekend_fill_color:
        return config.compactplan_weekend_fill_opacity
    return None


def _nwd_icon_for_classes(classes: frozenset[str], config: CalendarConfig) -> tuple[str, str] | None:
    if not classes:
        return None
    if "federal_holiday" in classes and config.compactplan_federal_holiday_icon:
        return (
            config.compactplan_federal_holiday_icon,
            config.compactplan_federal_holiday_fill_color or config.nonworkday_fill_color,
        )
    if "company_holiday" in classes and config.compactplan_company_holiday_icon:
        return (
            config.compactplan_company_holiday_icon,
            config.compactplan_company_holiday_fill_color or config.nonworkday_fill_color,
        )
    if "weekend" in classes and config.compactplan_weekend_icon:
        return (
            config.compactplan_weekend_icon,
            config.compactplan_weekend_fill_color or config.nonworkday_fill_color,
        )
    return None


if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PlacedDuration:
    """A duration line positioned on a rendering row."""

    event: Event
    color: str
    x1: float
    x2: float
    row_y: float
    continues: bool = False  # True when the event extends beyond the timeline end date
    starts_early: bool = False  # True when the event begins before the timeline start date
    icon_name: str | None = None  # icon drawn at the start (left) of the line
    style: StyleResult | None = None


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class CompactPlanRenderer(BaseSVGRenderer):
    """Renderer for compact activities plan visualization."""

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def _render_content(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list]:
        area_x, area_y, area_w, area_h = coordinates.get("CompactPlanArea", (0.0, 0.0, config.pageX, config.pageY))

        range_start = str(config.userstart or config.adjustedstart)
        range_end = str(config.userend or config.adjustedend)
        start = arrow.get(range_start, "YYYYMMDD").date()
        end = arrow.get(range_end, "YYYYMMDD").date()
        if end < start:
            start, end = end, start

        visible_days = self._visible_days(start, end, int(config.weekend_style))
        if not visible_days:
            return 0, []

        n_vis = len(visible_days)
        px_per_day = area_w / n_vis

        # Build fast date → x lookup (left edge of day's slot)
        day_x: dict[date, float] = {d: area_x + i * px_per_day for i, d in enumerate(visible_days)}

        # Geometry constants
        time_bands = list(getattr(config, "compactplan_time_bands", []) or [])
        bands_h = sum(self._band_row_h(band, config) for band in time_bands)

        # header_bottom_y is the gap (pts) between the header bands and the
        # topmost duration line or milestone.
        header_gap = float(getattr(config, "compactplan_header_bottom_y", None) or 0.0)

        line_w = float(config.compactplan_duration_line_width)

        # ------------------------------------------------------------------
        # PHASE 1 — Place duration rows.
        # Axis is fixed at the vertical centre of the content area so that
        # the greedy row-placement algorithm has a stable reference point.
        # ------------------------------------------------------------------
        axis_y = area_y + area_h / 2.0

        # Pre-load icon SVG cache so continuation icons and milestone icons can be drawn.
        self._load_icon_svg_cache(db)

        evt_objects = [Event.from_dict(e) if isinstance(e, dict) else e for e in events]
        self._style_engine = StyleEngine(_resolve_style_rules(config))
        self._color_rules = ColorRuleEngine(config.compactplan_color_rules, owner="compact_plan.color_rules")
        group_color_map = self._assign_group_colors(evt_objects, config)
        durations = [e for e in evt_objects if e.is_duration and not e.milestone]
        milestones = [e for e in evt_objects if e.milestone]
        self._note_visible_days(day.strftime("%Y%m%d") for day in visible_days)
        for rule_color in self._color_rules.colors:
            self._note_color(rule_color, "Color rule", "compact_plan.color_rules")
        for group, group_color in group_color_map.items():
            self._note_color(group_color, group or "(no group)", "group palette")

        placed = self._place_durations(
            durations,
            group_color_map,
            day_x,
            area_x,
            area_x + area_w,
            px_per_day,
            config,
            axis_y,
        )
        milestone_lanes = self._place_milestone_labels(milestones, day_x, px_per_day, config, area_x + area_w)
        # Duration rows sit both above and below the axis, and milestone
        # labels ride at the stem tip — so a stem only as tall as the
        # configured flag height plants its label in the middle of the bars.
        # Lift the base stem clear of the topmost row; the label lanes then
        # stack above that.
        ms_stem_base = float(config.compactplan_milestone_flag_height)
        if placed:
            band_top_offset = axis_y - (min(p.row_y for p in placed) - line_w / 2.0)
            ms_stem_base = max(ms_stem_base, band_top_offset + _MILESTONE_BAND_CLEARANCE)

        # ------------------------------------------------------------------
        # PHASE 2 — Compute actual content bounds from placed rows and flags.
        # Duration lines are centred on row_y; milestone stems reach up from
        # the axis by ms_stem_base plus their label lane.
        # ------------------------------------------------------------------
        if placed:
            min_content_y = min(p.row_y for p in placed) - line_w / 2.0
            max_content_y = max(p.row_y for p in placed) + line_w / 2.0
        else:
            min_content_y = axis_y
            max_content_y = axis_y

        if milestones:
            # Staggered labels ride on taller stems, so the tallest lane in
            # use — not the configured flag height — sets the top edge.
            top_lane = max(milestone_lanes.values(), default=0)
            tallest_flag = self._milestone_flag_height(config, top_lane, ms_stem_base)
            min_content_y = min(min_content_y, axis_y - tallest_flag)
            max_content_y = max(max_content_y, axis_y)
            # An icon standing in for a pennant sits on the label's baseline
            # and so rises above the stem tip; the header must clear it, with
            # a point to spare so the band's rule does not sit on its edge.
            if any(self._milestone_icon_name(m, self._milestone_style(m, config)[1], config) for m in milestones):
                icon_rise = (
                    0.8 * self._milestone_icon_size(config)
                    - (float(config.compactplan_milestone_flag_height) * _MILESTONE_PENNANT_RATIO / 2.0)
                    + _MILESTONE_ICON_HEADER_CLEARANCE
                )
                min_content_y = min(min_content_y, axis_y - tallest_flag - max(0.0, icon_rise))

        # ------------------------------------------------------------------
        # PHASE 3 — Float the header relative to content bounds.
        # Header bottom is header_gap pts above the topmost content edge.
        # ------------------------------------------------------------------
        bands_y = min_content_y - header_gap - bands_h

        # Header bands at computed floating position
        self._draw_bands(
            config,
            time_bands,
            area_x,
            bands_y,
            area_w,
            start,
            end,
            visible_days,
            px_per_day,
            n_vis,
            events=evt_objects,
            db=db,
        )

        # Axis (optional)
        if bool(config.compactplan_show_axis):
            _axis_style = config.get_line_style("ec-axis-line")
            self._draw_line(
                area_x,
                axis_y,
                area_x + area_w,
                axis_y,
                stroke=_axis_style.color,
                stroke_width=config.compactplan_axis_width,
                stroke_dasharray=_axis_style.dasharray or None,
                stroke_opacity=_axis_style.opacity,
                css_class="ec-axis-line",
            )

        # Duration lines
        for p in placed:
            self._draw_line(
                p.x1,
                p.row_y,
                p.x2,
                p.row_y,
                **self._bar_stroke(p, config),
                css_class="ec-duration-bar",
            )
            self._note_bar(p)

        # Bar content — three columns per bar: start date | icon + name | end date.
        dur_icon_h = self._duration_icon_height(config)
        for p in placed:
            with self._event_scope(p.event):
                self._draw_bar_content(p, dur_icon_h, config)

        # Continuation icons — at the clamped ends of any duration line whose
        # event runs past the timeline: an "after" arrow ending at its right
        # edge, a "before" arrow starting at its left.
        show_continuation = bool(config.show_continuation_icon)
        has_continuations = any(p.continues for p in placed)
        has_early_starts = any(p.starts_early for p in placed)
        if show_continuation:
            for p in placed:
                bar_h = float(self._bar_stroke(p, config)["stroke_width"])
                with self._event_scope(p.event):
                    if p.continues:
                        self._draw_continuation_icon(config, p.x2, p.row_y, p.color, max_size=bar_h)
                    if p.starts_early:
                        self._draw_continuation_icon(config, p.x1, p.row_y, p.color, max_size=bar_h, before=True)

        # Milestones
        for m in milestones:
            with self._event_scope(m):
                self._draw_milestone(
                    m,
                    day_x,
                    px_per_day,
                    axis_y,
                    config,
                    label_lane=milestone_lanes.get(id(m), 0),
                    stem_base_h=ms_stem_base,
                    max_label_x=area_x + area_w,
                )

        # The bars as placed, for callers that measure the chart.
        self._placed_durations = placed
        # What the chart's symbols mean, for the run's details document.
        self._note_key_symbols(config, show_continuation and has_early_starts, show_continuation and has_continuations)

        # ------------------------------------------------------------------
        # REFIT — override the viewBox to the actual rendered vertical extent.
        # _shrink_drawing_to_content() runs before _render_content() and uses
        # only the coordinate dict, so it sees the full CompactPlanArea box
        # and cannot know the floating bands_y computed here.  We correct the
        # viewBox directly now that all bounds are known: the chart runs from
        # the top of the header bands to the lowest ink below the axis.
        # ------------------------------------------------------------------
        if config.shrink_to_content:
            chart_bottom = self._chart_bottom(config, placed, max_content_y, axis_y)
            content_w = round(area_w, 4)
            content_h = round(max(1.0, chart_bottom - bands_y), 4)
            vb_x = round(area_x, 4)
            vb_y = round(bands_y, 4)
            self.drawing.view_box = (vb_x, vb_y, content_w, content_h)
            self.drawing.width = content_w
            self.drawing.height = content_h
            self._content_bbox_svg = (area_x, bands_y, area_x + area_w, chart_bottom)

        return 0, []

    # ------------------------------------------------------------------
    # Band / column header drawing
    # ------------------------------------------------------------------

    @staticmethod
    def _band_row_h(band: dict[str, Any], config: CalendarConfig) -> float:
        """Row height for one band: its own ``row_height``, else the
        view-wide ``compact_plan.band_row_height``."""
        if band.get("row_height") is not None:
            return float(band["row_height"])
        return float(config.compactplan_band_row_height)

    def _draw_bands(
        self,
        config: CalendarConfig,
        time_bands: list[dict],
        area_x: float,
        area_y: float,
        area_w: float,
        start: date,
        end: date,
        visible_days: list[date],
        px_per_day: float,
        n_vis: int,
        events: list[Event] | None = None,
        db: CalendarDB | None = None,
    ) -> None:
        """Draw the header band stack from ``area_y`` down.

        Each band is a ``compact_plan.bands`` entry, usually resolved from
        the shared ``time_bands:`` catalog.  Keys read here:

          unit          any unit of shared/timeband.py, plus "icon" (glyphs
                        from ``icon_rules``) and "holiday" (each holiday's
                        own country flag; ``nonworkdays_only`` hides
                        observances that do not close the office).
          row_height    this row's height; else ``compact_plan.band_row_height``.
          show_every    draw every N segments as one cell, labelled by its
                        first (date/dow cells never merge across a week).
          week_start    weekday a week begins on, for week and merged
                        date/dow cells (default Monday).
          fill_color / alt_fill_color   alternating cell fills.
          text_align    left | center | right label alignment.
          icon_rules / icon_height      "icon" and "holiday" bands.
        """
        font_name = self._resolve_font(getattr(config, "compactplan_text_font_name", None), config)
        _band_text_style = config.get_text_style("ec-label")
        text_color = str(_band_text_style.color)
        text_opacity = float(_band_text_style.opacity)
        _sep_style = config.get_line_style("ec-separator")
        _events: list[Event] = events or []

        # Per-day non-workday classes — used for date/dow band cells.
        _day_classes: dict[date, frozenset[str]] = (
            {d: classify_day(d, db, config) for d in visible_days} if db is not None else {}
        )
        _has_nwd_icons = bool(
            config.compactplan_federal_holiday_icon
            or config.compactplan_company_holiday_icon
            or config.compactplan_weekend_icon
        )
        if db is not None and _day_classes and _has_nwd_icons:
            self._load_icon_svg_cache(db)
        # A federal-holiday date/dow cell shows the flag of every country
        # closed that day — the same one-flag-per-country marks the holiday
        # band draws — not just the first holiday's.
        _holiday_flags = (
            compute_holiday_band_days(visible_days, db, config, nonworkdays_only=True)
            if config.compactplan_federal_holiday_icon and db is not None
            else {}
        )

        def separator(x1: float, y1: float, x2: float, y2: float) -> None:
            self._draw_line(
                x1,
                y1,
                x2,
                y2,
                stroke=_sep_style.color,
                stroke_width=_sep_style.width,
                stroke_opacity=_sep_style.opacity,
                stroke_dasharray=_sep_style.dasharray,
                css_class="ec-separator",
            )

        row_y = area_y
        for band_idx, band in enumerate(time_bands):
            row_h = self._band_row_h(band, config)
            unit = str(band.get("unit", "week")).strip().lower()
            font_size = float(getattr(config, "compactplan_text_font_size", None) or max(7.0, row_h * 0.35))

            # ── Per-day glyph bands — one cell per visible day ──────────────
            # "icon" takes its glyphs from the band's icon_rules; "holiday"
            # takes them from the holiday rows themselves, so each country
            # brings its own flag and adding a country needs no theme edit.
            if unit in {"icon", "holiday"}:
                if unit == "holiday":
                    # No color is passed with the flag: a country flag is
                    # already multi-colored, and recoloring it would make two
                    # countries indistinguishable.
                    holiday_days = (
                        compute_holiday_band_days(
                            visible_days,
                            db,
                            config,
                            nonworkdays_only=bool(band.get("nonworkdays_only", False)),
                        )
                        if db is not None
                        else {}
                    )
                    day_icon_map = {day: [(mark.icon, None) for mark in marks] for day, marks in holiday_days.items()}
                else:
                    icon_rules = list(band.get("icon_rules") or [])
                    day_icon_map = compute_icon_band_days(_events, icon_rules, visible_days)
                icon_h = float(band.get("icon_height") or row_h * 0.65)
                fill = str(band.get("fill_color") or "none")
                day_cells = [
                    (
                        self._seg_x(d, visible_days, area_x, area_w, n_vis, px_per_day),
                        px_per_day,
                        day_icon_map.get(d, []),
                    )
                    for d in visible_days
                ]
                self._draw_icon_band_row(
                    day_cells,
                    row_y,
                    row_h,
                    icon_h,
                    fill,
                    css_class="ec-band-cell",
                    fill_opacity=config.get_box_style("ec-band-cell").fill_opacity,
                )
                separator(area_x, row_y + row_h, area_x + area_w, row_y + row_h)
                row_y += row_h
                continue

            segments = self._build_segments(band, start, end, config, visible_days, band_idx, db=db)
            cells = _group_band_segments(segments, band, week_start_default=0)

            fill_color = str(band.get("fill_color") or "none")
            alt_fill_color = str(band.get("alt_fill_color") or "none")

            # text_align per band: "left" (default) | "center" | "right"
            text_align = str(band.get("text_align", "left")).strip().lower()
            if text_align not in {"left", "center", "right"}:
                text_align = "left"

            for cell_idx, cell in enumerate(cells):
                first_seg, last_seg = cell[0], cell[-1]
                x1 = self._seg_x(first_seg.start, visible_days, area_x, area_w, n_vis, px_per_day)
                x2 = self._seg_x(last_seg.end_exclusive, visible_days, area_x, area_w, n_vis, px_per_day)
                seg_w = max(0.0, x2 - x1)
                if seg_w <= 0:
                    continue

                fill = alt_fill_color if cell_idx % 2 else fill_color
                fill_opacity: float | None = None

                # Non-workday override for single-day date/dow cells.
                _is_single_day = (
                    unit in {"date", "dow"} and len(cell) == 1 and (first_seg.end_exclusive - first_seg.start).days == 1
                )
                _nwd_icons: list[tuple[str, str]] = []
                if _is_single_day and _day_classes:
                    _day_cls = _day_classes.get(first_seg.start, frozenset())
                    _nwd_fill = _nwd_fill_for_classes(_day_cls, config)
                    if _nwd_fill:
                        fill = _nwd_fill
                        fill_opacity = _nwd_fill_opacity_for_classes(_day_cls, config)
                    _nwd_icon_result = _nwd_icon_for_classes(_day_cls, config)
                    if _nwd_icon_result:
                        # Prefer the holidays' own country flags over the
                        # static config icon.
                        _icon_color = _nwd_icon_result[1]
                        _flags = _holiday_flags.get(first_seg.start) if "federal_holiday" in _day_cls else None
                        _nwd_icons = [(mark.icon, _icon_color) for mark in _flags] if _flags else [_nwd_icon_result]

                if not _is_none_color(fill):
                    self._draw_rect(
                        x1,
                        row_y,
                        seg_w,
                        row_h,
                        fill=fill,
                        fill_opacity=fill_opacity if fill_opacity is not None else 1.0,
                        css_class="ec-band-cell",
                    )

                # Vertical divider at the left edge of every cell after the
                # first — gives one stroke per cell boundary (N-1 dividers for
                # N cells), inheriting the ec-separator line style.
                if cell_idx > 0:
                    separator(x1, row_y, x1, row_y + row_h)

                if _nwd_icons:
                    self._draw_cell_icons(
                        _nwd_icons,
                        x1,
                        seg_w,
                        row_y,
                        row_h,
                        row_h * 0.65,
                        css_class="ec-nwd-icon",
                    )

                # Label text, vertically centered in the band row.
                # When a non-workday icon is drawn, suppress the date label so
                # the icon isn't overprinted (matches blockplan behavior).
                if _nwd_icons:
                    continue
                label = first_seg.label
                if label:
                    text_y = row_y + row_h * 0.72
                    pad = 2.0
                    if text_align == "center":
                        text_x = x1 + seg_w / 2.0
                        anchor = "middle"
                    elif text_align == "right":
                        text_x = x2 - pad
                        anchor = "end"
                    else:  # left
                        text_x = x1 + pad
                        anchor = "start"
                    self._draw_text(
                        text_x,
                        text_y,
                        label,
                        font_name,
                        font_size,
                        fill=text_color,
                        fill_opacity=text_opacity,
                        anchor=anchor,
                        max_width=seg_w - pad * 2,
                        css_class="ec-label",
                    )

            # Draw thin separator line below each band row
            separator(area_x, row_y + row_h, area_x + area_w, row_y + row_h)
            row_y += row_h

    # ------------------------------------------------------------------
    # Segment generation (week / month / fiscal_quarter / interval / date)
    # ------------------------------------------------------------------

    def _build_segments(
        self,
        band: dict[str, Any],
        start: date,
        end: date,
        config: CalendarConfig,
        visible_days: list[date],
        band_idx: int,
        db: CalendarDB | None = None,
    ) -> list[_BandSegment]:
        return _build_band_segments(
            band,
            start,
            end,
            config,
            visible_days=visible_days,
            db=db,
            week_start_default=0,
            fiscal_year_start_month_default=int(getattr(config, "blockplan_fiscal_year_start_month", 2) or 2),
        )

    # ------------------------------------------------------------------
    # Group color / icon assignment
    # ------------------------------------------------------------------

    def _note_bar(self, p: _PlacedDuration) -> None:
        """Record a placed bar: its color, where the color came from, its clipping."""
        from renderers.details_record import DRAWN_PARTIAL

        note = self._details_note(p.event)
        if note is None:
            return
        engine = getattr(self, "_color_rules", None)
        if p.style is not None and p.style.fill_color:
            source = "style rule"
        elif engine and engine.assign(p.event) is not None:
            source = "color rule"
        elif p.event.color:
            source = "event color"
        else:
            source = "group palette"
        note.assigned_color = p.color
        note.color_source = source
        note.continues_before = note.continues_before or p.starts_early
        note.continues_after = note.continues_after or p.continues
        with self._event_scope(p.event):
            self._note_mark("bar", p.color)
        if p.starts_early or p.continues:
            note.mark_drawn(DRAWN_PARTIAL)

    def _note_key_symbols(self, config: CalendarConfig, early_starts: bool, continuations: bool) -> None:
        """Record the chart's symbols, each with the meaning the key gives it."""
        from renderers.details_record import IconUse, mark

        record = self._details
        if record is None:
            return
        legend_color = str(config.get_text_style("ec-legend-text").color)
        if early_starts:
            name, _size, configured = self._continuation_icon_style(config, before=True)
            record.add_symbol(
                IconUse(name.strip().lower(), configured or legend_color, "continuation_before"),
                str(config.compactplan_continuation_before_legend_text or "activity began earlier"),
            )
        if continuations:
            name, _size, configured = self._continuation_icon_style(config)
            record.add_symbol(
                IconUse(name.strip().lower(), configured or legend_color, "continuation_after"),
                str(config.compactplan_continuation_legend_text or "activity continues"),
            )
        if config.compactplan_show_axis_legend and config.compactplan_show_axis:
            axis = config.get_line_style("ec-axis-line")
            record.add_symbol(mark("bar", axis.color, "axis"), str(config.compactplan_legend_axis_text or "timeline"))

    def _assign_group_colors(self, events: list[Event], config: CalendarConfig) -> dict[str, str]:
        palette: list[str] = list(config.compactplan_palette) or ["steelblue"]
        groups = sorted({(e.resource_group or "").strip() for e in events if e.is_duration and not e.milestone})
        return {g: palette[i % len(palette)] for i, g in enumerate(groups)}

    def _assign_bar_color(self, evt: Event, group_color_map: dict[str, str]) -> str:
        """A bar's color.

        The theme's ``compact_plan.color_rules`` are tried in order and the
        first match colors the bar.  A bar none matches gets the default
        assignment: its own ``Color``, else its resource group's palette
        color.  (A style rule's ``fill_color`` still layers over either.)
        """
        engine = getattr(self, "_color_rules", None)
        matched = engine.assign(evt) if engine else None
        if matched is not None:
            return matched[1]
        group = (evt.resource_group or "").strip()
        return evt.color or group_color_map.get(group, "steelblue")

    # ------------------------------------------------------------------
    # Greedy row placement
    # ------------------------------------------------------------------

    def _place_durations(
        self,
        durations: list[Event],
        group_color_map: dict[str, str],
        day_x: dict[date, float],
        timeline_x: float,
        timeline_x_end: float,
        px_per_day: float,
        config: CalendarConfig,
        axis_y: float,
    ) -> list[_PlacedDuration]:
        from config.config import ICON_SETS

        axis_padding = float(config.compactplan_axis_padding)
        line_w = float(config.compactplan_duration_line_width)

        # Build per-duration icon list (one unique icon per line, cycling by index).
        show_dur_icons = bool(getattr(config, "compactplan_show_duration_icons", True))
        list_name = str(getattr(config, "compactplan_duration_icon_list", "darksquare") or "darksquare")
        icon_list: list[str] = ICON_SETS.get(list_name, []) if show_dur_icons else []

        # Rows must clear whatever is actually drawn on them.  The configured
        # spacing is a request, not a licence to overlap.  A bar's start icon
        # and text are capped at its height, so the bar is a row's ink.
        lane_spacing = max(float(config.compactplan_lane_spacing), line_w + _DURATION_ROW_GAP)

        # Sort by start date for deterministic placement and stable icon assignment.
        sorted_durations = sorted(durations, key=lambda e: e.start)

        # row_occupancy[i] = list of (x1, x2) intervals already placed in row i
        row_occupancy: list[list[tuple[float, float]]] = []

        placed: list[_PlacedDuration] = []
        first_day = min(day_x) if day_x else None

        for evt_idx, evt in enumerate(sorted_durations):
            start_d = self._parse_date(evt.start)
            end_d = self._parse_date(evt.end)
            if start_d is None or end_d is None:
                continue

            x1 = self._date_to_x(start_d, day_x, timeline_x, px_per_day)
            starts_early = first_day is not None and start_d < first_day
            x2_raw = self._date_to_x(end_d, day_x, timeline_x, px_per_day) + px_per_day
            continues = x2_raw > timeline_x_end
            x2 = min(x2_raw, timeline_x_end)

            color = self._assign_bar_color(evt, group_color_map)
            _style_engine = getattr(self, "_style_engine", None)
            _sr = _style_engine.evaluate_event(evt) if _style_engine is not None else None
            if _sr is not None and _sr.fill_color:
                color = _sr.fill_color

            # Assign a unique icon to each duration by cycling through the list.
            icon_name: str | None = icon_list[evt_idx % len(icon_list)] if icon_list else None

            # Find the first row that (a) has no x-overlap with this event, and
            # (b) whose y-position is at least line_w away from every other row
            # that DOES have x-overlapping events.  Without (b), same-side rows
            # that are only lane_spacing apart in y can visually overlap when
            # lane_spacing < line_w, or when antialiasing blurs the gap.
            target_row = None
            for row_idx, occupied in enumerate(row_occupancy):
                if self._overlaps(x1, x2, occupied):
                    continue
                candidate_y = self._row_y(row_idx, axis_y, axis_padding, lane_spacing)
                visually_clear = all(
                    abs(candidate_y - self._row_y(ri, axis_y, axis_padding, lane_spacing)) >= line_w
                    for ri, occ in enumerate(row_occupancy)
                    if ri != row_idx and self._overlaps(x1, x2, occ)
                )
                if visually_clear:
                    target_row = row_idx
                    break
            if target_row is None:
                row_occupancy.append([])
                target_row = len(row_occupancy) - 1

            row_occupancy[target_row].append((x1, x2))

            # Row Y: even rows above axis, odd rows below
            row_y = self._row_y(target_row, axis_y, axis_padding, lane_spacing)
            placed.append(
                _PlacedDuration(
                    event=evt,
                    color=color,
                    x1=x1,
                    x2=x2,
                    row_y=row_y,
                    continues=continues,
                    starts_early=starts_early,
                    icon_name=icon_name,
                    style=_sr,
                )
            )

        return placed

    # ------------------------------------------------------------------
    # Milestone drawing
    # ------------------------------------------------------------------

    def _milestone_x(self, start_d: date, day_x: dict[date, float], px_per_day: float) -> float:
        """Centre x of the day column a milestone falls in."""
        if start_d in day_x:
            return day_x[start_d] + px_per_day / 2.0
        return self._date_to_x(start_d, day_x, day_x.get(start_d, 0.0), px_per_day) + px_per_day / 2.0

    def _place_milestone_labels(
        self,
        milestones: list[Event],
        day_x: dict[date, float],
        px_per_day: float,
        config: CalendarConfig,
        max_label_x: float | None = None,
    ) -> dict[int, int]:
        """
        Assign each milestone a label lane so labels never overlap.

        Every label used to be drawn at one fixed y beside its pennant, so any
        two milestones close together in time wrote their names on top of each
        other.  Labels are packed into lanes the same way durations are packed
        into rows: walk them left to right and take the first lane whose
        occupied x-intervals this label clears.  The lane then raises that
        milestone's stem, so the label rides at its own pennant and stays
        visibly tied to its date.

        Returns {id(event): lane index}; lane 0 is the original height.
        """
        if not config.compactplan_show_milestone_labels:
            return {}

        font_name = self._resolve_font(
            getattr(config, "compactplan_name_text_font_name", None),
            config,
            italic=True,
        )
        font_size = float(getattr(config, "compactplan_name_text_font_size", None) or 8.0)
        try:
            font_path = get_font_path(font_name)
        except Exception:
            font_path = None

        dated: list[tuple[float, float, int]] = []
        for evt in milestones:
            start_d = self._parse_date(evt.start)
            if start_d is None or not evt.task_name:
                continue
            x = self._milestone_x(start_d, day_x, px_per_day)
            mark_w = self._milestone_mark_width(evt, config)
            try:
                text_w = (
                    string_width(evt.task_name, font_path, font_size)
                    if font_path
                    else font_size * 0.5 * len(evt.task_name)
                )
            except Exception:
                text_w = font_size * 0.5 * len(evt.task_name)
            # The label starts past the pennant (or icon); keep a gap so
            # adjacent labels in one lane never touch.  Near the right edge
            # the drawing code flips the label to the left of the stem, so
            # pack the interval it will actually occupy.
            if max_label_x is not None and x + mark_w + 3.0 + text_w > max_label_x:
                x1 = x - 3.0 - text_w - _MILESTONE_LABEL_GAP
                x2 = x
            else:
                x1 = x
                x2 = x + mark_w + 3.0 + text_w + _MILESTONE_LABEL_GAP
            dated.append((x1, x2, id(evt)))

        lanes: list[list[tuple[float, float]]] = []
        assigned: dict[int, int] = {}
        for x1, x2, key in sorted(dated):
            target = None
            for lane_idx, occupied in enumerate(lanes):
                if not self._overlaps(x1, x2, occupied):
                    target = lane_idx
                    break
            if target is None:
                lanes.append([])
                target = len(lanes) - 1
            lanes[target].append((x1, x2))
            assigned[key] = target
        return assigned

    def _draw_milestone(
        self,
        evt: Event,
        day_x: dict[date, float],
        px_per_day: float,
        axis_y: float,
        config: CalendarConfig,
        label_lane: int = 0,
        stem_base_h: float | None = None,
        max_label_x: float | None = None,
    ) -> None:
        start_d = self._parse_date(evt.start)
        if start_d is None:
            return

        x = self._milestone_x(start_d, day_x, px_per_day)

        color, _sr = self._milestone_style(evt, config)
        flag_w = float(config.compactplan_milestone_flag_width)
        # A milestone in a higher label lane gets a longer stem so its name
        # clears the labels below it and still rides on its own pennant.
        # Only the stem grows: the pennant and the icon keep their configured
        # size, or milestones would appear to change importance by lane.
        base_h = float(config.compactplan_milestone_flag_height)
        stem_h = self._milestone_flag_height(config, label_lane, stem_base_h)
        pennant_h = base_h * _MILESTONE_PENNANT_RATIO
        # The label's baseline: centred on the pennant at the top of the stem.
        label_y = axis_y - stem_h + pennant_h / 2.0

        # An icon takes the pennant's place at the stem tip, on the label's
        # baseline; the stem stays, so the icon is still planted on its date.
        icon_name = self._milestone_icon_name(evt, _sr, config)
        if icon_name:
            self._draw_milestone_stem(x, axis_y, stem_h, color)
            self._draw_icon_svg(
                icon_name,
                x + _MILESTONE_ICON_GAP,
                label_y,
                self._milestone_icon_size(config),
                anchor="start",
                color=_sr.icon_color or color,
                css_class="ec-milestone-marker",
                box_token="box:milestone",
                box_ctx=self._event_ctx(evt),
            )
        else:
            self._draw_flag_marker(x, axis_y, stem_h, flag_w, color, pennant_h)
            self._note_mark("flag", color, "milestone")

        # Milestone label
        if config.compactplan_show_milestone_labels and evt.task_name:
            _name_style = config.get_text_style("ec-event-name")
            font_name = self._resolve_font(
                getattr(config, "compactplan_name_text_font_name", None), config, italic=True
            )
            font_size = float(getattr(config, "compactplan_name_text_font_size", None) or 8.0)
            label_color = str(_name_style.color)
            label_opacity = float(_name_style.opacity)
            label_font, _, label_color, label_opacity = _sr.text_override(
                "event_name",
                font=font_name,
                color=label_color,
                opacity=label_opacity,
            )
            label_x = x + self._milestone_mark_width(evt, config) + 3.0
            # A milestone near the end of the range would otherwise run its
            # label off the page; flip it to the left of the stem instead.
            anchor = "start"
            if max_label_x is not None:
                try:
                    text_w = string_width(evt.task_name, get_font_path(label_font), font_size)
                except Exception:
                    text_w = 0.0
                if text_w and label_x + text_w > max_label_x:
                    label_x = x - 3.0
                    anchor = "end"
            self._draw_text(
                label_x,
                label_y,
                evt.task_name,
                label_font,
                font_size,
                fill=label_color,
                fill_opacity=label_opacity,
                anchor=anchor,
                css_class="ec-event-name",
            )

    @staticmethod
    def _milestone_label_step(config: CalendarConfig) -> float:
        """Vertical distance between milestone label lanes (one text line)."""
        font_size = float(getattr(config, "compactplan_name_text_font_size", None) or 8.0)
        return font_size * _MILESTONE_LABEL_LINE_RATIO

    @classmethod
    def _milestone_flag_height(
        cls,
        config: CalendarConfig,
        label_lane: int,
        base: float | None = None,
    ) -> float:
        """
        Stem height for a milestone in ``label_lane``.

        ``base`` is the lane-0 stem length, raised by the caller to clear the
        activity band; it falls back to the configured flag height.
        """
        if base is None:
            base = float(config.compactplan_milestone_flag_height)
        return base + max(0, label_lane) * cls._milestone_label_step(config)

    def _draw_milestone_stem(self, x: float, axis_y: float, stem_h: float, color: str) -> None:
        """A milestone's stem, standing *stem_h* up from its foot on the axis."""
        # Vertical stem
        self._draw_line(x, axis_y, x, axis_y - stem_h, stroke=color, stroke_width=1.0, css_class="ec-milestone-marker")
        # Short horizontal foot tick at axis
        self._draw_line(
            x - 1.0, axis_y, x + 1.0, axis_y, stroke=color, stroke_width=1.0, css_class="ec-milestone-marker"
        )

    def _draw_flag_marker(
        self,
        x: float,
        axis_y: float,
        flag_h: float,
        flag_w: float,
        color: str,
        pennant_h: float | None = None,
    ) -> None:
        """
        Draw a flag-on-stem milestone marker matching the reference SVG design.

        ``flag_h`` is the stem length; ``pennant_h`` sizes the pennant and
        defaults to a fixed share of it.  Staggered labels pass the two
        separately so a taller stem does not also inflate the pennant.
        """
        stem_top = axis_y - flag_h
        self._draw_milestone_stem(x, axis_y, flag_h, color)

        # Pennant: a parallelogram/trapezoid to the right of stem tip
        if pennant_h is None:
            pennant_h = flag_h * _MILESTONE_PENNANT_RATIO
        p_top = stem_top
        p_bot = stem_top + pennant_h
        indent = flag_w * 0.23  # taper indent at attachment points

        path = drawsvg.Path(
            stroke=color,
            stroke_width=1.0,
            fill="none",
            stroke_linejoin="round",
        )
        path.M(x, p_top + indent)
        path.L(x + flag_w * 0.4, p_top + indent)
        path.L(x + flag_w, p_top + pennant_h * 0.2)
        path.L(x + flag_w, p_bot - pennant_h * 0.2)
        path.L(x + flag_w * 0.4, p_bot - indent)
        path.L(x, p_bot - indent)
        path.Z()
        self.drawing.append(path)

    # ------------------------------------------------------------------
    # Mark styling — shared by the chart and its key, so a swatch on the
    # key page is painted exactly as the bar it stands for.
    # ------------------------------------------------------------------

    @staticmethod
    def _bar_stroke(p: _PlacedDuration, config: CalendarConfig) -> dict[str, Any]:
        """A duration bar's stroke: style-rule overrides over the theme's."""
        rule = p.style or StyleResult()
        theme = config.get_line_style("ec-duration-bar")
        return {
            "stroke": rule.stroke_color if rule.stroke_color is not None else p.color,
            "stroke_width": (
                rule.stroke_width if rule.stroke_width is not None else float(config.compactplan_duration_line_width)
            ),
            "stroke_dasharray": (
                rule.stroke_dasharray if rule.stroke_dasharray is not None else (theme.dasharray or None)
            ),
            "stroke_opacity": (rule.stroke_opacity if rule.stroke_opacity is not None else theme.opacity),
        }

    @staticmethod
    def _duration_icon_height(config: CalendarConfig) -> float:
        """Size of a bar's start icon.

        Theme-declared `icon:duration size:` overrides the per-visualizer
        default; falls back to compactplan_duration_icon_height when absent.
        """
        style = config.get_icon_style("ec-duration-icon")
        return float(style.size if style.size is not None else config.compactplan_duration_icon_height)

    def _draw_start_icon(
        self,
        p: _PlacedDuration,
        x: float,
        center_y: float,
        size: float,
        config: CalendarConfig,
    ) -> None:
        """Draw a bar's start icon from *x*, centred on *center_y*."""
        if not p.icon_name:
            return
        rule = p.style or StyleResult()
        # Contrast-swap when the configured icon color matches the bar
        # color, otherwise the glyph paints invisibly against its own bar
        # (the user-reported navy-on-navy case).
        color = _resolve_icon_on_bar(
            style_override=rule.icon_color,
            configured=str(config.get_icon_style("ec-duration-icon").color or "").strip(),
            bar_color=p.color,
        )
        self._draw_icon_svg(
            rule.icon if rule.icon is not None else p.icon_name,
            x,
            self._icon_baseline(center_y, size),
            size,
            anchor="start",
            color=color,
            css_class="ec-duration-icon",
            box_token="box:duration",
            box_ctx=self._event_ctx(p.event),
        )

    @staticmethod
    def _bar_columns(p: _PlacedDuration, config: CalendarConfig) -> tuple[float, float, float, float]:
        """A bar's column edges: ``(x1, middle start, middle end, x2)``.

        The start and end date columns are each
        ``compactplan_duration_date_column_ratio`` of the bar's width -- the
        same width whether or not a date is shown in them -- and the middle
        column, holding the icon and name, takes the rest.
        """
        ratio = min(max(float(config.compactplan_duration_date_column_ratio), 0.0), 0.5)
        date_w = (p.x2 - p.x1) * ratio
        return p.x1, p.x1 + date_w, p.x2 - date_w, p.x2

    def _draw_bar_content(self, p: _PlacedDuration, icon_h: float, config: CalendarConfig) -> None:
        """Fill a bar's three columns, each centred on the bar's centre line.

        Dates and name are sized to the bar's height, then shrunk to fit
        their column; a name that still does not fit is cut short, a date
        is left out.  A continuing bar's arrow takes the end of the end
        column, so its date fits beside it.
        """
        from renderers.details_record import KIND_DATE_OMITTED, KIND_NAME_TRUNCATED

        x1, mid_x1, mid_x2, x2 = self._bar_columns(p, config)
        stroke = self._bar_stroke(p, config)
        bar_h = float(stroke["stroke_width"])
        font_name = self._resolve_font(config.compactplan_name_text_font_name, config)
        font_size = min(float(config.compactplan_name_text_font_size or 8.0), bar_h)
        try:
            font_path = get_font_path(font_name)
        except KeyError:
            font_path = ""

        def draw_date(value: str, left: float, right: float) -> None:
            day = self._parse_date(value)
            if day is None or not font_path:
                return
            label = format_arrow_date(arrow.get(day), str(config.compactplan_duration_date_format))
            color = config.compactplan_duration_date_color or _contrast_color(stroke["stroke"])
            status = self._draw_fitted_text(
                label,
                left,
                right,
                p.row_y,
                font_name,
                font_path,
                font_size,
                color,
                "ec-duration-date",
                truncate=False,
                opacity=config.get_text_style("ec-duration-date").opacity,
            )
            if status == "omitted":
                self._note_exception(
                    KIND_DATE_OMITTED,
                    p.event.task_name or "",
                    str(value)[:8],
                    detail=f"{label} did not fit its bar",
                    event=p.event,
                )

        if config.compactplan_duration_show_start_date:
            start_left = x1
            if p.starts_early and config.show_continuation_icon:
                start_left += min(self._continuation_icon_style(config, before=True)[1], bar_h)
            draw_date(p.event.start, start_left, mid_x1)
        if config.compactplan_duration_show_end_date:
            end_right = x2
            if p.continues and config.show_continuation_icon:
                end_right -= min(self._continuation_icon_style(config)[1], bar_h)
            draw_date(p.event.end, mid_x2, end_right)

        text_x = mid_x1
        icon_size = min(icon_h, bar_h, mid_x2 - mid_x1)
        if config.compactplan_show_duration_icons and p.icon_name and icon_size > 0:
            self._draw_start_icon(p, mid_x1, p.row_y, icon_size, config)
            text_x += icon_size + _BAR_ICON_GAP
        if font_path:
            color = config.compactplan_duration_name_color or _contrast_color(stroke["stroke"])
            status = self._draw_fitted_text(
                (p.event.task_name or "").strip(),
                text_x,
                mid_x2,
                p.row_y,
                font_name,
                font_path,
                font_size,
                color,
                "ec-event-name",
                truncate=True,
                opacity=config.get_text_style("ec-event-name").opacity,
            )
            if status != "drawn" and (p.event.task_name or "").strip():
                self._note_exception(
                    KIND_NAME_TRUNCATED,
                    p.event.task_name or "",
                    str(p.event.start)[:8],
                    detail="shortened to fit its bar" if status == "truncated" else "no room on its bar",
                    event=p.event,
                )

    def _draw_fitted_text(
        self,
        text: str,
        left: float,
        right: float,
        center_y: float,
        font_name: str,
        font_path: str,
        font_size: float,
        color: str,
        css_class: str,
        *,
        truncate: bool,
        opacity: float = 1.0,
    ) -> str:
        """Draw *text* between *left* and *right*, centred on *center_y*.

        The text shrinks toward :data:`_BAR_MIN_FONT_SIZE` to fit; past that
        it is cut short with an ellipsis when *truncate* (a name, drawn from
        *left*), else not drawn (a date, centred in its column).

        Returns ``"drawn"``, ``"truncated"`` or ``"omitted"``, so the caller
        can report what the bar could not show.
        """
        width = right - left
        if not text or width <= 0:
            return "omitted"
        size = shrinktext(text, width, font_path, font_size, min_fontsize=_BAR_MIN_FONT_SIZE)

        def measure(s: str) -> float:
            return string_width(s, font_path, size)

        shortened = False
        if measure(text) > width:
            if not truncate:
                return "omitted"
            lines = fit_lines(text, width, 1, measure)
            text = lines[0] if lines else ""
            if not text or measure(text) > width:
                return "omitted"
            shortened = True
        x, anchor = (left, "start") if truncate else ((left + right) / 2.0, "middle")
        self._draw_text(
            x,
            text_center_baseline(center_y, font_path, size),
            text,
            font_name,
            size,
            fill=color,
            fill_opacity=opacity,
            anchor=anchor,
            css_class=css_class,
        )
        return "truncated" if shortened else "drawn"

    @staticmethod
    def _continuation_icon_style(config: CalendarConfig, *, before: bool = False) -> tuple[str, float, str]:
        """``(icon, size, configured color)`` of a continuation icon.

        Theme `icon:continuation` (bound to ec-continuation-icon) takes
        precedence; each field falls back to the global continuation_*
        config keys when the theme is silent.  The theme's single icon name
        is the "after" arrow's; the *before* arrow always reads
        continuation_icon_before, as blockplan's does.  Size and color are
        shared by both.
        """
        style = config.get_icon_style("ec-continuation-icon")
        if before:
            name = resolve_continuation_icon(config.continuation_icon_before, "horizontal", "arrow-left")
        else:
            name = str(
                style.icon or resolve_continuation_icon(config.continuation_icon_after, "horizontal", "arrow-right")
            )
        size = float(style.size if style.size is not None else (config.continuation_icon_height or 8.0))
        color = (style.color or config.continuation_icon_color or "").strip()
        return name, size, color

    def _draw_continuation_icon(
        self,
        config: CalendarConfig,
        x: float,
        center_y: float,
        bar_color: str | None,
        max_size: float | None = None,
        *,
        before: bool = False,
    ) -> None:
        """Draw a continuation icon centred on *center_y*: the "after" arrow
        ending at *x*, or the *before* arrow starting at it.

        On a bar it contrast-swaps against *bar_color* like the start
        icons do; standing alone (``bar_color`` None) it takes the
        configured color, else the legend text's.
        """
        name, size, configured = self._continuation_icon_style(config, before=before)
        if max_size is not None:
            size = min(size, max_size)
        if bar_color is None:
            color = configured or str(config.get_text_style("ec-legend-text").color)
        else:
            color = _resolve_icon_on_bar(style_override=None, configured=configured, bar_color=bar_color)
        self._draw_icon_svg(
            name,
            x,
            self._icon_baseline(center_y, size),
            size,
            anchor="start" if before else "end",
            color=color,
            css_class="ec-continuation-icon",
            details_role="continuation_before" if before else "continuation_after",
        )

    def _milestone_style(self, evt: Event, config: CalendarConfig) -> tuple[str, StyleResult]:
        """A milestone's marker color, and the style rules it matched."""
        engine = getattr(self, "_style_engine", None)
        rule = engine.evaluate_event(evt) if engine is not None else StyleResult()
        color = rule.fill_color or evt.color or config.get_element_color("ec-milestone-marker", "black")
        return color, rule

    def _milestone_icon_name(self, evt: Event, rule: StyleResult, config: CalendarConfig) -> str | None:
        """The icon a milestone is marked with instead of a pennant, if any.

        A style rule's icon, then the event's own, then the theme's
        ``compact_plan.milestone_icon``.  ``None`` -- a flag -- when none is
        named or the name is not in the icons table.  The chart and its key
        both ask here, so the key never shows a mark the chart did not.
        """
        name = rule.icon if rule.icon is not None else (evt.icon or getattr(config, "compactplan_milestone_icon", None))
        return name if self._resolve_icon_svg(name) else None

    @classmethod
    def _milestone_icon_size(cls, config: CalendarConfig) -> float:
        """Size of a milestone icon: the flag's height, but never taller than
        a label lane, so icons in neighbouring lanes cannot touch."""
        return min(
            float(config.compactplan_milestone_flag_height),
            cls._milestone_label_step(config),
        )

    def _milestone_mark_width(self, evt: Event, config: CalendarConfig) -> float:
        """How far right of the stem a milestone's pennant or icon reaches."""
        _, rule = self._milestone_style(evt, config)
        if self._milestone_icon_name(evt, rule, config):
            return _MILESTONE_ICON_GAP + self._milestone_icon_size(config)
        return float(config.compactplan_milestone_flag_width)

    def _chart_bottom(
        self,
        config: CalendarConfig,
        placed: list[_PlacedDuration],
        content_bottom: float,
        axis_y: float,
    ) -> float:
        """Lowest ink the chart drew: its bars and the axis.

        A bar's icons and text are capped at its height, so nothing on
        the bottom row reaches past the bar's own edge.
        """
        bottom = content_bottom
        if placed:
            half = float(config.compactplan_duration_line_width) / 2.0
            bottom = max(bottom, max(p.row_y for p in placed) + half)
        if config.compactplan_show_axis:
            bottom = max(bottom, axis_y + float(config.compactplan_axis_width) / 2.0)
        return bottom

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Day-axis visibility lives in shared/date_utils.visible_days().
    _visible_days = staticmethod(visible_days)

    @staticmethod
    def _seg_x(
        d: date,
        visible_days: list[date],
        area_x: float,
        area_w: float,
        n_vis: int,
        px_per_day: float,
    ) -> float:
        """X position of a date boundary within the visible-day scale."""
        count = bisect_left(visible_days, d)
        ratio = max(0.0, min(1.0, count / max(1, n_vis)))
        return area_x + ratio * area_w

    @staticmethod
    def _date_to_x(
        d: date,
        day_x: dict[date, float],
        fallback_x: float,
        px_per_day: float,
    ) -> float:
        """Left-edge x for a date; clamps to nearest visible day if not visible."""
        if d in day_x:
            return day_x[d]
        # Find closest visible day before d
        if day_x:
            visible = sorted(day_x.keys())
            idx = bisect_left(visible, d)
            if idx == 0:
                return day_x[visible[0]]
            return day_x[visible[idx - 1]] + px_per_day
        return fallback_x

    @staticmethod
    def _parse_date(date_str: str) -> date | None:
        """Parse YYYYMMDD or ISO date string → date; returns None on failure."""
        if not date_str:
            return None
        s = str(date_str).replace("-", "")
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _overlaps(x1: float, x2: float, occupied: list[tuple[float, float]]) -> bool:
        """Return True if interval [x1, x2) overlaps any interval in occupied."""
        return any(x1 < ox2 and x2 > ox1 for ox1, ox2 in occupied)

    @staticmethod
    def _row_y(row_idx: int, axis_y: float, axis_padding: float, lane_spacing: float) -> float:
        """Y coordinate for row index: even=above axis, odd=below."""
        half = row_idx // 2
        if row_idx % 2 == 0:
            return axis_y - axis_padding - half * lane_spacing
        else:
            return axis_y + axis_padding + half * lane_spacing

    @staticmethod
    def _resolve_font(font_setting: str | None, config: CalendarConfig, italic: bool = False) -> str:
        """Resolve a font name: explicit setting → base config font → safe fallback."""
        from config.config import FONT_REGISTRY, Fonts

        if font_setting:
            if font_setting in FONT_REGISTRY:
                return font_setting
        # Try notes/base compactplan font from config
        if italic:
            candidates = [
                getattr(config, "compactplan_notes_text_font_name", None),
                getattr(config, "compactplan_text_font_name", None),
            ]
        else:
            candidates = [getattr(config, "compactplan_text_font_name", None)]
        for c in candidates:
            if c and c in FONT_REGISTRY:
                return c
        return Fonts.RC_LIGHT
