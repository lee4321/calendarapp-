"""
Compact Activities Plan SVG renderer.

Renders a compressed timeline with duration lines above/below a central axis
and milestone flag markers.  The key is a companion page written beside the
chart (``<output>_key.svg``): the shared details listing, with each row
carrying the swatch, icon or flag that ties it to what the chart drew.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import arrow
import drawsvg

from config.config import get_font_path, resolve_continuation_icon
from renderers import event_listing
from renderers.details_page import (
    DetailsColumn,
    DetailsPageWriter,
    RowMark,
    details_output_path,
    numbered_page_path,
)
from renderers.svg_base import BaseSVGRenderer, _is_none_color
from renderers.text_utils import string_width

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

# Clear space between the top of the activity band and the lowest
# milestone pennant, so labels never land on a duration bar.
_MILESTONE_BAND_CLEARANCE = 3.0

# The key page's mark column: its heading, the narrowest it may be (it
# has to hold the heading), and the room the writer pads a cell with.
_KEY_COLUMN_HEADING = "Key"
_KEY_COLUMN_MIN_WIDTH = 20.0
_KEY_COLUMN_PADDING = 8.0
from shared.data_models import Event
from shared.date_utils import visible_days
from shared.day_classifier import classify_day
from shared.holiday_band import compute_holiday_band_days
from shared.icon_band import compute_icon_band_days
from shared.rule_engine import StyleEngine, StyleResult
from shared.timeband import (
    BandSegment as _BandSegment,
    build_segments as _build_band_segments,
    group_segments as _group_band_segments,
)


# ─── Color helpers (named + hex → RGB → luminance) ──────────────────────────
# A small CSS-named-color → RGB table covering the values that turn up in the
# in-tree themes (palettes + theme.colors).  Anything outside this table that
# isn't a hex literal is treated as "unknown" — the contrast code then leaves
# the icon color alone, which preserves backward behaviour for exotic names.

_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),                "white": (255, 255, 255),
    "grey": (128, 128, 128),           "gray": (128, 128, 128),
    "lightgrey": (211, 211, 211),      "lightgray": (211, 211, 211),
    "darkgrey": (169, 169, 169),       "darkgray": (169, 169, 169),
    "dimgrey": (105, 105, 105),        "dimgray": (105, 105, 105),
    "slategrey": (112, 128, 144),      "slategray": (112, 128, 144),
    "navy": (0, 0, 128),               "midnightblue": (25, 25, 112),
    "blue": (0, 0, 255),               "darkblue": (0, 0, 139),
    "steelblue": (70, 130, 180),       "lightsteelblue": (176, 196, 222),
    "dodgerblue": (30, 144, 255),      "deepskyblue": (0, 191, 255),
    "lightblue": (173, 216, 230),      "powderblue": (176, 224, 230),
    "red": (255, 0, 0),                "darkred": (139, 0, 0),
    "firebrick": (178, 34, 34),        "tomato": (255, 99, 71),
    "coral": (255, 127, 80),           "salmon": (250, 128, 114),
    "pink": (255, 192, 203),
    "gold": (255, 215, 0),             "goldenrod": (218, 165, 32),
    "yellow": (255, 255, 0),
    "orange": (255, 165, 0),           "darkorange": (255, 140, 0),
    "green": (0, 128, 0),              "darkgreen": (0, 100, 0),
    "limegreen": (50, 205, 50),        "mediumseagreen": (60, 179, 113),
    "springgreen": (0, 255, 127),      "bisque": (255, 228, 196),
    "purple": (128, 0, 128),           "darkmagenta": (139, 0, 139),
    "deeppink": (255, 20, 147),        "mediumpurple": (147, 112, 219),
    "none": None,                       "transparent": None,
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


def _resolve_style_rules(config: "CalendarConfig") -> list:
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
    config: "CalendarConfig",
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
    config: "CalendarConfig",
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


def _nwd_icon_for_classes(
    classes: frozenset[str], config: "CalendarConfig"
) -> tuple[str, str] | None:
    if not classes:
        return None
    if "federal_holiday" in classes and config.compactplan_federal_holiday_icon:
        return (
            config.compactplan_federal_holiday_icon,
            config.compactplan_federal_holiday_fill_color or "#333333",
        )
    if "company_holiday" in classes and config.compactplan_company_holiday_icon:
        return (
            config.compactplan_company_holiday_icon,
            config.compactplan_company_holiday_fill_color or "#333333",
        )
    if "weekend" in classes and config.compactplan_weekend_icon:
        return (
            config.compactplan_weekend_icon,
            config.compactplan_weekend_fill_color or "#333333",
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
    icon_name: str | None = None  # icon drawn at the start (left) of the line
    style: StyleResult | None = None


@dataclass(frozen=True)
class _ChartKey:
    """What the chart drew, kept for the key page written after it.

    Attributes:
        listing: Every event as passed in, beside the :class:`Event` the
            chart read it as -- the listing reads the former, the marks
            the latter.
        placed: Drawn duration bars, by ``id()`` of their event.
        milestones: ``id()`` of every milestone given a flag.
        visible_days: The days on the axis, whose holidays the key lists.
        continuations: Whether any bar was drawn continuing off the end.
    """

    listing: list[tuple[Any, Event]]
    placed: dict[int, _PlacedDuration]
    milestones: frozenset[int]
    visible_days: list[date]
    continuations: bool


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class CompactPlanRenderer(BaseSVGRenderer):
    """Renderer for compact activities plan visualization."""

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def render(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ):
        self._chart_key: _ChartKey | None = None
        result = super().render(config, coordinates, events, db)
        if config.compactplan_show_legend and self._chart_key is not None:
            # The key paginates, so it is worth as many pages as it took.
            result.page_count += self._render_key_svg(config, coordinates, db)
        return result

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        area_x, area_y, area_w, area_h = coordinates.get(
            "CompactPlanArea", (0.0, 0.0, config.pageX, config.pageY)
        )

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
        day_x: dict[date, float] = {
            d: area_x + i * px_per_day for i, d in enumerate(visible_days)
        }

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
        group_color_map = self._assign_group_colors(evt_objects, config)
        durations = [e for e in evt_objects if e.is_duration and not e.milestone]
        milestones = [e for e in evt_objects if e.milestone]

        placed = self._place_durations(
            durations, group_color_map, day_x, area_x, area_x + area_w,
            px_per_day, config, axis_y,
        )
        milestone_lanes = self._place_milestone_labels(
            milestones, day_x, px_per_day, config, area_x + area_w
        )
        # Duration rows sit both above and below the axis, and milestone
        # labels ride at the stem tip — so a stem only as tall as the
        # configured flag height plants its label in the middle of the bars.
        # Lift the base stem clear of the topmost row; the label lanes then
        # stack above that.
        ms_stem_base = float(config.compactplan_milestone_flag_height)
        if placed:
            band_top_offset = axis_y - (
                min(p.row_y for p in placed) - line_w / 2.0
            )
            ms_stem_base = max(
                ms_stem_base, band_top_offset + _MILESTONE_BAND_CLEARANCE
            )

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
            tallest_flag = self._milestone_flag_height(
                config, top_lane, ms_stem_base
            )
            min_content_y = min(min_content_y, axis_y - tallest_flag)
            max_content_y = max(max_content_y, axis_y)
            # An icon standing in for a pennant sits on the label's baseline
            # and so rises above the stem tip; the header must clear it, with
            # a point to spare so the band's rule does not sit on its edge.
            if any(
                self._milestone_icon_name(m, self._milestone_style(m, config)[1], config)
                for m in milestones
            ):
                icon_rise = 0.8 * self._milestone_icon_size(config) - (
                    float(config.compactplan_milestone_flag_height)
                    * _MILESTONE_PENNANT_RATIO / 2.0
                ) + _MILESTONE_ICON_HEADER_CLEARANCE
                min_content_y = min(
                    min_content_y, axis_y - tallest_flag - max(0.0, icon_rise)
                )

        # ------------------------------------------------------------------
        # PHASE 3 — Float the header relative to content bounds.
        # Header bottom is header_gap pts above the topmost content edge.
        # ------------------------------------------------------------------
        bands_y = min_content_y - header_gap - bands_h

        # Header bands at computed floating position
        self._draw_bands(
            config, time_bands, area_x, bands_y, area_w, start, end,
            visible_days, px_per_day, n_vis,
            events=evt_objects,
            db=db,
        )

        # Axis (optional)
        if bool(config.compactplan_show_axis):
            _axis_style = config.get_line_style("ec-axis-line")
            self._draw_line(
                area_x, axis_y, area_x + area_w, axis_y,
                stroke=_axis_style.color,
                stroke_width=config.compactplan_axis_width,
                stroke_dasharray=_axis_style.dasharray or None,
                stroke_opacity=_axis_style.opacity,
                css_class="ec-axis-line",
            )

        # Duration lines
        for p in placed:
            self._draw_line(
                p.x1, p.row_y, p.x2, p.row_y,
                **self._bar_stroke(p, config),
                css_class="ec-duration-bar",
            )

        # Start icons — one unique icon at the left (start-date) end of each duration line.
        # Each duration gets its own icon by index, cycling through the configured list.
        dur_icon_h = self._duration_icon_height(config)
        if config.compactplan_show_duration_icons and dur_icon_h > 0:
            for p in placed:
                self._draw_start_icon(p, p.x1, p.row_y, dur_icon_h, config)

        # Continuation icons — drawn at the clamped right edge of any duration
        # line whose event extends beyond the timeline end date.
        show_continuation = bool(config.show_continuation_icon)
        has_continuations = any(p.continues for p in placed)
        if show_continuation and has_continuations:
            for p in placed:
                if p.continues:
                    self._draw_continuation_icon(config, p.x2, p.row_y, p.color)

        # Milestones
        for m in milestones:
            self._draw_milestone(
                m, day_x, px_per_day, axis_y, config,
                label_lane=milestone_lanes.get(id(m), 0),
                stem_base_h=ms_stem_base,
                max_label_x=area_x + area_w,
            )

        # The key -- what each bar, flag and symbol stands for -- is its own
        # page, written after the chart (see render()).  Keep what it has
        # to explain.
        self._chart_key = _ChartKey(
            listing=list(zip(events, evt_objects)),
            placed={id(p.event): p for p in placed},
            milestones=frozenset(
                id(m) for m in milestones if self._parse_date(m.start) is not None
            ),
            visible_days=visible_days,
            continuations=show_continuation and has_continuations,
        )

        # ------------------------------------------------------------------
        # REFIT — override the viewBox to the actual rendered vertical extent.
        # _shrink_drawing_to_content() runs before _render_content() and uses
        # only the coordinate dict, so it sees the full CompactPlanArea box
        # and cannot know the floating bands_y computed here.  We correct the
        # viewBox directly now that all bounds are known: the chart runs from
        # the top of the header bands to the lowest ink below the axis.
        # ------------------------------------------------------------------
        if config.shrink_to_content:
            chart_bottom = self._chart_bottom(
                config, placed, max_content_y, axis_y, dur_icon_h
            )
            content_w = round(area_w, 4)
            content_h = round(max(1.0, chart_bottom - bands_y), 4)
            vb_x = round(area_x, 4)
            vb_y = round(bands_y, 4)
            self._drawing.view_box = (vb_x, vb_y, content_w, content_h)
            self._drawing.width = content_w
            self._drawing.height = content_h
            self._content_bbox_svg = (area_x, bands_y, area_x + area_w, chart_bottom)

        return 0, []

    # ------------------------------------------------------------------
    # Band / column header drawing
    # ------------------------------------------------------------------

    @staticmethod
    def _band_row_h(band: dict[str, Any], config: "CalendarConfig") -> float:
        """Row height for one band: its own ``row_height``, else the
        view-wide ``compact_plan.band_row_height``."""
        if band.get("row_height") is not None:
            return float(band["row_height"])
        return float(config.compactplan_band_row_height)

    def _draw_bands(
        self,
        config: "CalendarConfig",
        time_bands: list[dict],
        area_x: float,
        area_y: float,
        area_w: float,
        start: date,
        end: date,
        visible_days: list[date],
        px_per_day: float,
        n_vis: int,
        events: "list[Event] | None" = None,
        db: "CalendarDB | None" = None,
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
        font_name = self._resolve_font(
            getattr(config, "compactplan_text_font_name", None), config
        )
        _band_text_style = config.get_text_style("ec-label")
        text_color = str(_band_text_style.color or "black")
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
        if _day_classes and _has_nwd_icons:
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
                x1, y1, x2, y2,
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
            font_size = float(
                getattr(config, "compactplan_text_font_size", None)
                or max(7.0, row_h * 0.35)
            )

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
                            visible_days, db, config,
                            nonworkdays_only=bool(band.get("nonworkdays_only", False)),
                        )
                        if db is not None
                        else {}
                    )
                    day_icon_map = {
                        day: [(mark.icon, None) for mark in marks]
                        for day, marks in holiday_days.items()
                    }
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
                    day_cells, row_y, row_h, icon_h, fill,
                    css_class="ec-band-cell",
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
                    unit in {"date", "dow"}
                    and len(cell) == 1
                    and (first_seg.end_exclusive - first_seg.start).days == 1
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
                        _flags = (
                            _holiday_flags.get(first_seg.start)
                            if "federal_holiday" in _day_cls
                            else None
                        )
                        _nwd_icons = (
                            [(mark.icon, _icon_color) for mark in _flags]
                            if _flags
                            else [_nwd_icon_result]
                        )

                if not _is_none_color(fill):
                    self._draw_rect(
                        x1, row_y, seg_w, row_h,
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
                        _nwd_icons, x1, seg_w, row_y, row_h, row_h * 0.65,
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
                        text_x, text_y, label,
                        font_name, font_size,
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
        config: "CalendarConfig",
        visible_days: list[date],
        band_idx: int,
        db: "CalendarDB | None" = None,
    ) -> list[_BandSegment]:
        return _build_band_segments(
            band, start, end, config,
            visible_days=visible_days,
            db=db,
            week_start_default=0,
            fiscal_year_start_month_default=int(
                getattr(config, "blockplan_fiscal_year_start_month", 2) or 2
            ),
        )

    # ------------------------------------------------------------------
    # Group color / icon assignment
    # ------------------------------------------------------------------

    def _assign_group_colors(
        self, events: list[Event], config: "CalendarConfig"
    ) -> dict[str, str]:
        palette: list[str] = list(config.compactplan_palette) or ["steelblue"]
        groups = sorted({
            (e.resource_group or "").strip() for e in events if e.is_duration and not e.milestone
        })
        return {g: palette[i % len(palette)] for i, g in enumerate(groups)}

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
        config: "CalendarConfig",
        axis_y: float,
    ) -> list[_PlacedDuration]:
        from config.config import ICON_SETS

        axis_padding = float(config.compactplan_axis_padding)
        line_w = float(config.compactplan_duration_line_width)

        # Build per-duration icon list (one unique icon per line, cycling by index).
        show_dur_icons = bool(getattr(config, "compactplan_show_duration_icons", True))
        list_name = str(
            getattr(config, "compactplan_duration_icon_list", "darksquare") or "darksquare"
        )
        icon_list: list[str] = ICON_SETS.get(list_name, []) if show_dur_icons else []

        # Rows must clear whatever is actually drawn on them.  The configured
        # spacing is a request, not a licence to overlap: a 5pt bar carrying an
        # 8pt start icon needs more than the 6pt default, or consecutive rows
        # collide and the icons of one row sit on the bar of the next.
        ink_h = line_w
        if icon_list:
            ink_h = max(
                ink_h,
                float(
                    config.get_icon_style("ec-duration-icon").size
                    or config.compactplan_duration_icon_height
                ),
            )
        lane_spacing = max(
            float(config.compactplan_lane_spacing), ink_h + _DURATION_ROW_GAP
        )

        # Sort by start date for deterministic placement and stable icon assignment.
        sorted_durations = sorted(durations, key=lambda e: e.start)

        # row_occupancy[i] = list of (x1, x2) intervals already placed in row i
        row_occupancy: list[list[tuple[float, float]]] = []

        placed: list[_PlacedDuration] = []

        for evt_idx, evt in enumerate(sorted_durations):
            start_d = self._parse_date(evt.start)
            end_d = self._parse_date(evt.end)
            if start_d is None or end_d is None:
                continue

            x1 = self._date_to_x(start_d, day_x, timeline_x, px_per_day)
            x2_raw = self._date_to_x(end_d, day_x, timeline_x, px_per_day) + px_per_day
            continues = x2_raw > timeline_x_end
            x2 = min(x2_raw, timeline_x_end)

            group_key = (evt.resource_group or "").strip()
            color = evt.color or group_color_map.get(group_key, "steelblue")
            _style_engine = getattr(self, "_style_engine", None)
            _sr = (
                _style_engine.evaluate_event(evt)
                if _style_engine is not None
                else None
            )
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
                    event=evt, color=color, x1=x1, x2=x2, row_y=row_y,
                    continues=continues, icon_name=icon_name, style=_sr,
                )
            )

        return placed

    # ------------------------------------------------------------------
    # Milestone drawing
    # ------------------------------------------------------------------

    def _milestone_x(
        self, start_d: date, day_x: dict[date, float], px_per_day: float
    ) -> float:
        """Centre x of the day column a milestone falls in."""
        if start_d in day_x:
            return day_x[start_d] + px_per_day / 2.0
        return (
            self._date_to_x(start_d, day_x, day_x.get(start_d, 0.0), px_per_day)
            + px_per_day / 2.0
        )

    def _place_milestone_labels(
        self,
        milestones: list[Event],
        day_x: dict[date, float],
        px_per_day: float,
        config: "CalendarConfig",
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
        font_size = float(
            getattr(config, "compactplan_name_text_font_size", None) or 8.0
        )
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
        config: "CalendarConfig",
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
                icon_name, x + _MILESTONE_ICON_GAP, label_y,
                self._milestone_icon_size(config),
                anchor="start", color=_sr.icon_color or color,
                css_class="ec-milestone-marker",
                box_token="box:milestone",
                box_ctx=self._event_ctx(evt),
            )
        else:
            self._draw_flag_marker(x, axis_y, stem_h, flag_w, color, pennant_h)

        # Milestone label
        if config.compactplan_show_milestone_labels and evt.task_name:
            _name_style = config.get_text_style("ec-event-name")
            font_name = self._resolve_font(
                getattr(config, "compactplan_name_text_font_name", None), config, italic=True
            )
            font_size = float(
                getattr(config, "compactplan_name_text_font_size", None) or 8.0
            )
            label_color = str(_name_style.color or "#595959")
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
                    text_w = string_width(
                        evt.task_name, get_font_path(label_font), font_size
                    )
                except Exception:
                    text_w = 0.0
                if text_w and label_x + text_w > max_label_x:
                    label_x = x - 3.0
                    anchor = "end"
            self._draw_text(
                label_x, label_y, evt.task_name,
                label_font, font_size,
                fill=label_color, fill_opacity=label_opacity,
                anchor=anchor,
                css_class="ec-event-name",
            )

    @staticmethod
    def _milestone_label_step(config: "CalendarConfig") -> float:
        """Vertical distance between milestone label lanes (one text line)."""
        font_size = float(
            getattr(config, "compactplan_name_text_font_size", None) or 8.0
        )
        return font_size * _MILESTONE_LABEL_LINE_RATIO

    @classmethod
    def _milestone_flag_height(
        cls,
        config: "CalendarConfig",
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

    def _draw_milestone_stem(
        self, x: float, axis_y: float, stem_h: float, color: str
    ) -> None:
        """A milestone's stem, standing *stem_h* up from its foot on the axis."""
        # Vertical stem
        self._draw_line(x, axis_y, x, axis_y - stem_h, stroke=color, stroke_width=1.0, css_class="ec-milestone-marker")
        # Short horizontal foot tick at axis
        self._draw_line(x - 1.0, axis_y, x + 1.0, axis_y, stroke=color, stroke_width=1.0, css_class="ec-milestone-marker")

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
        self._drawing.append(path)

    # ------------------------------------------------------------------
    # Mark styling — shared by the chart and its key, so a swatch on the
    # key page is painted exactly as the bar it stands for.
    # ------------------------------------------------------------------

    @staticmethod
    def _bar_stroke(p: _PlacedDuration, config: "CalendarConfig") -> dict[str, Any]:
        """A duration bar's stroke: style-rule overrides over the theme's."""
        rule = p.style or StyleResult()
        theme = config.get_line_style("ec-duration-bar")
        return {
            "stroke": rule.stroke_color if rule.stroke_color is not None else p.color,
            "stroke_width": (
                rule.stroke_width
                if rule.stroke_width is not None
                else float(config.compactplan_duration_line_width)
            ),
            "stroke_dasharray": (
                rule.stroke_dasharray
                if rule.stroke_dasharray is not None
                else (theme.dasharray or None)
            ),
            "stroke_opacity": (
                rule.stroke_opacity
                if rule.stroke_opacity is not None
                else theme.opacity
            ),
        }

    @staticmethod
    def _duration_icon_height(config: "CalendarConfig") -> float:
        """Size of a bar's start icon.

        Theme-declared `icon:duration size:` overrides the per-visualizer
        default; falls back to compactplan_duration_icon_height when absent.
        """
        style = config.get_icon_style("ec-duration-icon")
        return float(
            style.size
            if style.size is not None
            else config.compactplan_duration_icon_height
        )

    def _draw_start_icon(
        self,
        p: _PlacedDuration,
        x: float,
        center_y: float,
        size: float,
        config: "CalendarConfig",
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
            x, self._icon_baseline(center_y, size), size,
            anchor="start", color=color,
            css_class="ec-duration-icon",
            box_token="box:duration",
            box_ctx=self._event_ctx(p.event),
        )

    @staticmethod
    def _continuation_icon_style(config: "CalendarConfig") -> tuple[str, float, str]:
        """``(icon, size, configured color)`` of the continuation icon.

        Theme `icon:continuation` (bound to ec-continuation-icon) takes
        precedence; each field falls back to the global continuation_*
        config keys when the theme is silent.  Compactplan only clips its
        "after" end, so it reads continuation_icon_after.
        """
        style = config.get_icon_style("ec-continuation-icon")
        name = str(
            style.icon
            or resolve_continuation_icon(
                config.continuation_icon_after, "horizontal", "arrow-right"
            )
        )
        size = float(
            style.size
            if style.size is not None
            else (config.continuation_icon_height or 8.0)
        )
        color = (style.color or config.continuation_icon_color or "").strip()
        return name, size, color

    def _draw_continuation_icon(
        self,
        config: "CalendarConfig",
        right_x: float,
        center_y: float,
        bar_color: str | None,
        max_size: float | None = None,
    ) -> None:
        """Draw the continuation icon ending at *right_x*, centred on *center_y*.

        On a bar it contrast-swaps against *bar_color* like the start
        icons do; standing alone (``bar_color`` None) it takes the
        configured color, else the legend text's.
        """
        name, size, configured = self._continuation_icon_style(config)
        if max_size is not None:
            size = min(size, max_size)
        if bar_color is None:
            color = configured or str(
                config.get_text_style("ec-legend-text").color or "#595959"
            )
        else:
            color = _resolve_icon_on_bar(
                style_override=None, configured=configured, bar_color=bar_color
            )
        self._draw_icon_svg(
            name, right_x, self._icon_baseline(center_y, size), size,
            anchor="end", color=color,
            css_class="ec-continuation-icon",
        )

    def _milestone_style(
        self, evt: Event, config: "CalendarConfig"
    ) -> tuple[str, StyleResult]:
        """A milestone's marker color, and the style rules it matched."""
        engine = getattr(self, "_style_engine", None)
        rule = engine.evaluate_event(evt) if engine is not None else StyleResult()
        color = (
            rule.fill_color
            or evt.color
            or config.get_element_color("ec-milestone-marker", "black")
        )
        return color, rule

    def _milestone_icon_name(
        self, evt: Event, rule: StyleResult, config: "CalendarConfig"
    ) -> str | None:
        """The icon a milestone is marked with instead of a pennant, if any.

        A style rule's icon, then the event's own, then the theme's
        ``compact_plan.milestone_icon``.  ``None`` -- a flag -- when none is
        named or the name is not in the icons table.  The chart and its key
        both ask here, so the key never shows a mark the chart did not.
        """
        name = rule.icon if rule.icon is not None else (
            evt.icon or getattr(config, "compactplan_milestone_icon", None)
        )
        return name if self._resolve_icon_svg(name) else None

    @classmethod
    def _milestone_icon_size(cls, config: "CalendarConfig") -> float:
        """Size of a milestone icon: the flag's height, but never taller than
        a label lane, so icons in neighbouring lanes cannot touch."""
        return min(
            float(config.compactplan_milestone_flag_height),
            cls._milestone_label_step(config),
        )

    def _milestone_mark_width(self, evt: Event, config: "CalendarConfig") -> float:
        """How far right of the stem a milestone's pennant or icon reaches."""
        _, rule = self._milestone_style(evt, config)
        if self._milestone_icon_name(evt, rule, config):
            return _MILESTONE_ICON_GAP + self._milestone_icon_size(config)
        return float(config.compactplan_milestone_flag_width)

    def _chart_bottom(
        self,
        config: "CalendarConfig",
        placed: list[_PlacedDuration],
        content_bottom: float,
        axis_y: float,
        dur_icon_h: float,
    ) -> float:
        """Lowest ink the chart drew: its bars, their icons, the axis.

        Start and continuation icons are taller than the bar they ride
        and centred on it, so the bottom row's icons reach past the
        bar's own edge; a viewBox ending at the bar would clip them.
        """
        bottom = content_bottom
        if placed:
            half = float(config.compactplan_duration_line_width) / 2.0
            if config.compactplan_show_duration_icons and any(
                p.icon_name for p in placed
            ):
                half = max(half, dur_icon_h / 2.0)
            if config.show_continuation_icon and any(p.continues for p in placed):
                half = max(half, self._continuation_icon_style(config)[1] / 2.0)
            bottom = max(bottom, max(p.row_y for p in placed) + half)
        if config.compactplan_show_axis:
            bottom = max(bottom, axis_y + float(config.compactplan_axis_width) / 2.0)
        return bottom

    # ------------------------------------------------------------------
    # Key page (second SVG)
    # ------------------------------------------------------------------

    def _render_key_svg(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        db: "CalendarDB | None",
    ) -> int:
        """Write the chart's key beside it; returns how many pages it took.

        The key is the shared details listing -- the events the chart
        drew, chronologically, then the holidays and special days on its
        axis -- with a leading column of marks: each activity's bar in
        miniature (its color, start icon and any continuation arrow),
        each milestone's flag, each holiday's icon.  That column is what
        keeps the listing a key: every row is tied to what it explains
        on the chart.  A closing section explains the chart's symbols.

        Built through the shared
        :class:`~renderers.details_page.DetailsPageWriter`, so it is the
        same page the other companions are; it paginates onto
        ``_key_p2.svg`` rather than dropping rows.  The chart's drawing
        is restored afterwards.
        """
        key = self._chart_key
        saved_drawing = self._drawing

        def page_path(number: int) -> str:
            base = details_output_path(
                config.outputfile, config.compactplan_key_output_suffix
            )
            return numbered_page_path(base, number)

        writer = DetailsPageWriter(
            self, config, coordinates, page_path, config.compactplan_key_title_text
        )
        mark_share = min(
            0.5, self._key_column_width(config, key) / max(1.0, writer.width)
        )
        mark_column = DetailsColumn(_KEY_COLUMN_HEADING, mark_share)
        columns = [mark_column] + [
            replace(column, width=column.width * (1.0 - mark_share))
            for column in event_listing.details_columns(config)
        ]
        count = len(columns) - 1
        name_column = 1 + event_listing.NAME_COLUMN

        # Only what the chart drew: an event it had no mark for is not
        # something its key can explain.
        drawn = [
            (event_listing.listing_dict(raw), evt)
            for raw, evt in key.listing
            if id(evt) in key.placed or id(evt) in key.milestones
        ]
        if drawn:
            writer.section(config.mini_details_events_section_text, columns)
            for row, evt in sorted(
                drawn, key=lambda item: event_listing.sort_key(item[0])
            ):
                bar = key.placed.get(id(evt))
                writer.row(
                    [""] + event_listing.event_cells(row, count),
                    columns,
                    sub_line=(name_column, event_listing.event_note(row)),
                    mark=(
                        0,
                        self._bar_mark(bar, config)
                        if bar is not None
                        else self._milestone_mark(evt, config),
                    ),
                )

        holidays: list[dict] = []
        if config.compactplan_show_holiday_list and db is not None:
            holidays = event_listing.holiday_special_rows(
                (d.strftime("%Y%m%d") for d in key.visible_days), config, db
            )
        if holidays:
            writer.section(config.mini_details_holidays_section_text, columns)
            for row in holidays:
                writer.row(
                    [""] + event_listing.holiday_cells(row, count),
                    columns,
                    sub_line=(name_column, row.get("notes") or ""),
                    mark=(
                        (0, self._holiday_mark(row["icon"], config))
                        if row["icon"]
                        else None
                    ),
                )

        # The symbols explain marks on rows above; with no rows there is
        # nothing for them to explain, and no key worth writing.
        symbols = self._key_symbols(config, key)
        if symbols and (drawn or holidays):
            symbol_columns = [mark_column, DetailsColumn("Meaning", 1.0 - mark_share)]
            writer.section(config.compactplan_key_symbols_section_text, symbol_columns)
            for draw, text in symbols:
                writer.row(["", text], symbol_columns, mark=(0, draw))

        pages = writer.finish()
        self._drawing = saved_drawing
        return pages

    def _key_column_width(self, config: "CalendarConfig", key: _ChartKey) -> float:
        """Width of the key page's mark column, in points."""
        swatch = float(config.compactplan_legend_swatch_width)
        if key.continuations:
            # A continuing bar's arrow is drawn past the swatch's end.
            swatch += 1.0 + self._continuation_icon_style(config)[1]
        widths = [
            swatch,
            float(config.compactplan_milestone_flag_width) + 2.0,
            _KEY_COLUMN_MIN_WIDTH,
        ]
        if config.compactplan_show_duration_icons:
            widths.append(self._duration_icon_height(config))
        return max(widths) + _KEY_COLUMN_PADDING

    def _draw_swatch(
        self, x: float, y: float, length: float, stroke: dict[str, Any]
    ) -> None:
        """A key swatch: a short run of *stroke* from *x*, centred on *y*.

        Emitted as a raw <line> with inline style="..." so the color
        survives any .ec-legend-swatch CSS rule in the SVG <style> block
        (themes that bind ec-legend-swatch -> line:axis would otherwise
        override the presentation attribute with the axis color via CSS
        class specificity, hiding the per-bar color entirely).
        """
        parts = [
            f"stroke:{stroke['stroke']}",
            f"stroke-width:{stroke['stroke_width']}",
        ]
        if stroke.get("stroke_opacity") is not None:
            parts.append(f"stroke-opacity:{stroke['stroke_opacity']}")
        if stroke.get("stroke_dasharray"):
            parts.append(f"stroke-dasharray:{stroke['stroke_dasharray']}")
        self._drawing.append(drawsvg.Raw(
            f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{(x + length):.2f}" y2="{y:.2f}" '
            f'style="{";".join(parts)}" class="ec-legend-swatch" />'
        ))

    def _key_arrow_end(
        self, config: "CalendarConfig", x: float, width: float, size: float
    ) -> float:
        """Right edge of a continuation arrow on the key: just past the
        swatch's end, so the arrow never covers the color it continues."""
        swatch = min(width, float(config.compactplan_legend_swatch_width))
        arrow = min(self._continuation_icon_style(config)[1], size * 1.25)
        return min(x + width, x + swatch + 1.0 + arrow)

    def _bar_mark(self, p: _PlacedDuration, config: "CalendarConfig") -> RowMark:
        """An activity's bar in miniature: its stroke, start icon and any
        continuation arrow, painted as the chart painted them."""

        def draw(x: float, baseline: float, width: float, size: float) -> None:
            length = min(width, float(config.compactplan_legend_swatch_width))
            center_y = baseline - size * 0.3
            stroke = self._bar_stroke(p, config)
            # A bar never outgrows the row it keys.
            stroke["stroke_width"] = min(float(stroke["stroke_width"]), size)
            self._draw_swatch(x, center_y, length, stroke)
            icon_h = min(self._duration_icon_height(config), size * 1.25)
            if config.compactplan_show_duration_icons and icon_h > 0:
                self._draw_start_icon(p, x, center_y, icon_h, config)
            if p.continues and config.show_continuation_icon:
                self._draw_continuation_icon(
                    config, self._key_arrow_end(config, x, width, size),
                    center_y, p.color, max_size=size * 1.25,
                )

        return draw

    def _milestone_mark(self, evt: Event, config: "CalendarConfig") -> RowMark:
        """A milestone's flag in its color, or the icon the chart drew for it."""

        def draw(x: float, baseline: float, width: float, size: float) -> None:
            color, rule = self._milestone_style(evt, config)
            icon_name = self._milestone_icon_name(evt, rule, config)
            if icon_name:
                self._draw_icon_svg(
                    icon_name, x, baseline, min(size, width),
                    anchor="start", color=rule.icon_color or color,
                    css_class="ec-milestone-marker",
                    box_token="box:milestone",
                    box_ctx=self._event_ctx(evt),
                )
                return
            flag_w = min(float(config.compactplan_milestone_flag_width), width - 1.0)
            # The stem stands from just below the baseline to cap height,
            # one point in so its foot tick stays inside the cell.
            self._draw_flag_marker(
                x + 1.0, baseline + size * 0.15, size, max(1.0, flag_w),
                color, size * 0.6,
            )

        return draw

    def _holiday_mark(self, icon: str, config: "CalendarConfig") -> RowMark:
        """A holiday or special day's own icon."""
        color = str(config.get_text_style("ec-event-name").color or "#595959")

        def draw(x: float, baseline: float, width: float, size: float) -> None:
            self._draw_icon_svg(
                icon, x, self._icon_baseline(baseline - size * 0.3, size),
                min(size, width), anchor="start", color=color,
                css_class="ec-legend-icon",
            )

        return draw

    def _key_symbols(
        self, config: "CalendarConfig", key: _ChartKey
    ) -> list[tuple[RowMark, str]]:
        """The chart's symbols the key explains, as ``(mark, meaning)``."""
        swatch_w = float(config.compactplan_legend_swatch_width)
        symbols: list[tuple[RowMark, str]] = []

        if key.continuations:
            def continuation(x: float, baseline: float, width: float, size: float) -> None:
                # Where the arrow sits beside an activity's swatch above.
                self._draw_continuation_icon(
                    config, self._key_arrow_end(config, x, width, size),
                    baseline - size * 0.3, None, max_size=size * 1.25,
                )

            symbols.append((
                continuation,
                str(config.compactplan_continuation_legend_text or "activity continues"),
            ))

        if config.compactplan_show_axis_legend and config.compactplan_show_axis:
            def axis(x: float, baseline: float, width: float, size: float) -> None:
                style = config.get_line_style("ec-axis-line")
                self._draw_swatch(
                    x, baseline - size * 0.3, min(width, swatch_w),
                    {
                        "stroke": style.color,
                        "stroke_width": min(float(config.compactplan_axis_width), size),
                        "stroke_dasharray": style.dasharray or None,
                        "stroke_opacity": style.opacity,
                    },
                )

            symbols.append((axis, str(config.compactplan_legend_axis_text or "timeline")))

        return symbols

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
        for ox1, ox2 in occupied:
            if x1 < ox2 and x2 > ox1:
                return True
        return False

    @staticmethod
    def _row_y(
        row_idx: int, axis_y: float, axis_padding: float, lane_spacing: float
    ) -> float:
        """Y coordinate for row index: even=above axis, odd=below."""
        half = row_idx // 2
        if row_idx % 2 == 0:
            return axis_y - axis_padding - half * lane_spacing
        else:
            return axis_y + axis_padding + half * lane_spacing

    @staticmethod
    def _resolve_font(
        font_setting: str | None, config: "CalendarConfig", italic: bool = False
    ) -> str:
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
