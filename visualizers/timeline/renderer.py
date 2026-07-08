"""
Timeline SVG renderer.

Renders a horizontal, date-scaled timeline with distinct point-event callouts
and duration bars aligned to start/end dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import arrow
import drawsvg

from config.config import get_font_path, resolve_continuation_icon
from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import shrinktext, string_width
from shared.data_models import Event
from shared.date_utils import format_arrow_date
from shared.rule_engine import StyleEngine, StyleResult
from shared.day_classifier import classify_day
from shared.icon_band import compute_icon_band_days
from shared.timeband import build_segments as _build_band_segments
from visualizers.timeline.labella_adapter import (
    CalloutPlacement,
    layout_callouts as _labella_layout_callouts,
)
from shared.orientation import Orientation, Side

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


def _timeline_style_rules(config: "CalendarConfig") -> list:
    """Source the raw style_rules list for StyleEngine.

    Prefers the parsed UnifiedTheme (``config.theme``) so the renderer no
    longer depends on the legacy ``theme_style_rules`` decompiler bridge.
    Mirrors compactplan / weekly / blockplan / mini-day_styles.
    """
    theme = getattr(config, "theme", None)
    if theme is not None:
        rules = theme.sections.get("style_rules")
        if isinstance(rules, list):
            return rules
    return list(getattr(config, "theme_style_rules", None) or [])


@dataclass(frozen=True)
class TimelineCallout:
    """Point-in-time event callout placement.

    Coordinates are absolute SVG (Y-down). `x_dot` / `y_dot` mark the
    location of the dot on the axis line where the leader originates;
    `box_*` give the label rectangle. `leader_path_d` is labella's bezier
    `d` attribute in *axis-local* coordinates — it pairs with `axis_origin`
    via a `<g transform="translate(ox,oy)">` wrapper when emitted.
    """

    event: Event
    color: str
    # Dot on the axis line (leader origin).
    x_dot: float
    y_dot: float
    # Label box.
    lane: int
    box_x: float
    box_y: float
    box_width: float
    box_height: float
    date_row: int = 0
    # Labella leader. Empty string is permitted for fallback paths.
    leader_path_d: str = ""
    axis_origin: tuple[float, float] = (0.0, 0.0)
    orientation: Orientation = Orientation.HORIZONTAL
    style: StyleResult | None = None

    @property
    def x(self) -> float:
        """Backwards-compat alias for the dot x position (used by older
        renderer code paths that pre-date the orientation refactor)."""
        return self.x_dot


@dataclass(frozen=True)
class TimelineDuration:
    """Duration bar placement alongside the timeline axis.

    For HORIZONTAL orientation: `start_x`/`end_x` are the bar endpoints
    along the axis, and `lane` stacks downward below the axis.

    For VERTICAL orientation: `start_y`/`end_y` are the bar endpoints
    along the axis, `start_x`/`end_x` both equal the axis x position,
    and `lane` stacks to the LEFT of the axis (secondary side).
    `continues_left` / `continues_right` map to "continues past the top"
    / "continues past the bottom" respectively.
    """

    event: Event
    color: str
    start_x: float
    end_x: float
    lane: int
    min_width: float
    continues_left: bool = False
    continues_right: bool = False
    style: StyleResult | None = None
    orientation: Orientation = Orientation.HORIZONTAL
    start_y: float = 0.0
    end_y: float = 0.0
    # Which side of the axis this bar sits on (vertical orientation only;
    # ignored for horizontal). PRIMARY = right, SECONDARY = left.
    lane_side: Side = Side.SECONDARY


class TimelineRenderer(BaseSVGRenderer):
    """Renderer for timeline visualization."""

    _CALL_OUT_DATE_ROWS = 3

    # Tokens pre-resolved once per render; see BaseSVGRenderer._populate_tokens.
    TOKEN_VISUALIZER = "timeline"
    TOKENS = (
        "text:event_name", "text:event_notes", "text:event_date",
        "text:duration_date", "text:label", "text:today_label",
        "line:axis", "line:today", "line:tick",
        "icon:event", "icon:milestone",
    )

    # NOTE: ``_callout_metrics`` is defined near the bottom of the file.
    # An earlier duplicate definition existed at this point pre-migration
    # (Python silently used the last one); removed during this migration
    # so the token-aware version is the single source of truth.

    @staticmethod
    def _fit_box_text_sizes(
        text: str,
        notes: str,
        text_width: float,
        box_height: float,
        title_font_path: str | None,
        notes_font_path: str | None,
        title_size: float,
        notes_size: float,
    ) -> tuple[float, float]:
        """Shrink title/notes fonts to fit a constrained box width and height."""
        width = max(8.0, text_width)
        tsize = shrinktext(text, width, title_font_path, title_size)
        nsize = (
            shrinktext(notes, width, notes_font_path, notes_size)
            if notes
            else notes_size
        )

        def required_h(ts: float, ns: float, has_notes: bool) -> float:
            # Use ~1.2 line height per row plus a small inner padding. The
            # earlier 1.9/1.7 multipliers were generous and caused declared
            # font sizes to be shrunk well below the box's actual capacity.
            line_h = ts * 1.2 + ((ns * 1.2) if has_notes else 0.0)
            return line_h + 2.0

        has_notes = bool(notes)
        need = required_h(tsize, nsize, has_notes)
        if box_height > 0 and need > box_height:
            # Scale down first, then tighten iteratively if still too tall.
            factor = max(0.35, box_height / need)
            tsize = max(6.0, tsize * factor)
            if has_notes:
                nsize = max(5.0, nsize * factor)
            tsize = shrinktext(text, width, title_font_path, tsize)
            if has_notes:
                nsize = shrinktext(notes, width, notes_font_path, nsize)
            guard = 0
            while required_h(tsize, nsize, has_notes) > box_height and guard < 30:
                tsize = max(6.0, tsize - 0.2)
                if has_notes:
                    nsize = max(5.0, nsize - 0.2)
                guard += 1

        return tsize, nsize

    def _create_drawing(self, config: "CalendarConfig") -> drawsvg.Drawing:
        drawing = super()._create_drawing(config)
        bg_style = config.get_box_style("ec-background")
        bg = str(bg_style.fill or "").strip().lower()
        if bg not in {"", "none", "transparent"}:
            drawing.append(
                drawsvg.Rectangle(
                    0,
                    0,
                    round(config.pageX, 2),
                    round(config.pageY, 2),
                    fill=bg_style.fill,
                )
            )
        return drawing

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        area_x, area_y, area_w, area_h = coordinates.get(
            "TimelineArea", (0.0, 0.0, config.pageX, config.pageY)
        )

        # Timeline is a continuous time axis — use the user-typed range so the
        # axis edges match the requested dates exactly. Fall back to the
        # weekend-style-adjusted range only when no user range was captured.
        user_start_str = getattr(config, "userstart", None) or config.adjustedstart
        user_end_str = getattr(config, "userend", None) or config.adjustedend
        start = arrow.get(user_start_str, "YYYYMMDD")
        end = arrow.get(user_end_str, "YYYYMMDD")
        if end < start:
            start, end = end, start

        orient = Orientation(config.timeline_orientation)
        label_side = Side(config.timeline_label_side)

        # Reserve room for top/bottom timebands only on horizontal axes —
        # timebands above/below a vertical axis are not supported in this
        # release and would land on top of the axis. The config fields
        # still parse, but they no-op for vertical.
        if orient is Orientation.HORIZONTAL:
            top_bands = list(getattr(config, "timeline_top_time_bands", None) or [])
            bottom_bands = list(getattr(config, "timeline_bottom_time_bands", None) or [])
        else:
            top_bands = []
            bottom_bands = []
        top_bands_h = sum(float(b.get("row_height", 14.0)) for b in top_bands)
        bottom_bands_h = sum(float(b.get("row_height", 14.0)) for b in bottom_bands)

        event_objs = [Event.from_dict(e) for e in events]
        self._load_icon_svg_cache(db)
        self._populate_tokens(config)
        point_events, duration_events = self._split_events(config, event_objs)
        style_engine = StyleEngine(_timeline_style_rules(config))

        # Compute the axis geometry for the chosen orientation. axis_origin
        # is the (x, y) where the 1-D idealPos=0 maps in absolute SVG. For
        # horizontal this is the left end of the axis; for vertical, the
        # top end. axis_length is the extent along the axis.
        if orient is Orientation.HORIZONTAL:
            axis_left = area_x + (area_w * 0.04)
            axis_right = area_x + (area_w * 0.96)
            inner_y = area_y + top_bands_h
            inner_h = max(1.0, area_h - top_bands_h - bottom_bands_h)
            if getattr(config, "includeevents", True):
                axis_y = inner_y + (inner_h * 0.44)
            else:
                tick_clearance = self._tick_label_top_clearance(
                    config, getattr(config, "timeline_ticks", None)
                )
                axis_y = inner_y + tick_clearance + 4.0
            axis_origin = (axis_left, axis_y)
            axis_length = axis_right - axis_left
            # End-of-axis coordinates for the line draw and downstream uses.
            axis_end = (axis_right, axis_y)
        else:
            axis_top = area_y + (area_h * 0.04)
            axis_bottom = area_y + (area_h * 0.96)
            # Pick the axis x so each populated side has room. With events
            # visible, callouts dominate the layout: keep the 44% bias that
            # leaves a wider right-hand label column. With --noevents the
            # only horizontal content is duration lanes, so center the axis
            # when bars go on both sides (label_side=both), push it right
            # when bars only go left (secondary), and keep it near the left
            # margin otherwise.
            if getattr(config, "includeevents", True):
                axis_x = area_x + (area_w * 0.44)
            elif label_side is Side.BOTH:
                axis_x = area_x + (area_w * 0.50)
            elif label_side is Side.SECONDARY:
                axis_x = area_x + (area_w * 0.90)
            else:
                axis_x = area_x + (area_w * 0.10)
            axis_origin = (axis_x, axis_top)
            axis_length = axis_bottom - axis_top
            axis_end = (axis_x, axis_bottom)
            # Legacy locals so the horizontal-only feature blocks below can
            # safely no-op when checked.
            axis_left = axis_x
            axis_right = axis_x
            axis_y = axis_top

        callouts = self._layout_callouts(
            config,
            point_events,
            start,
            end,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orient,
            side=label_side,
            style_engine=style_engine,
        )
        if orient is Orientation.HORIZONTAL:
            durations = self._layout_durations(
                config,
                duration_events,
                start,
                end,
                axis_left,
                axis_right,
                axis_y,
                style_engine,
            )
        else:
            durations = self._layout_durations_vertical(
                config,
                duration_events,
                start,
                end,
                axis_x=axis_origin[0],
                axis_top=axis_origin[1],
                axis_bottom=axis_end[1],
                side=label_side,
                style_engine=style_engine,
            )

        # Pass 1: emit labella's curved bezier leader paths under everything
        # else. Each path is in axis-local coordinates; we wrap it in a
        # translate() transform that places idealPos=0 at axis_origin.
        leader_style = config.get_line_style("ec-callout-leader")
        leader_stroke_width = leader_style.width or 1.25
        leader_opacity = leader_style.opacity or 0.75
        leader_dasharray = (
            leader_style.dasharray
            or config.timeline_connector_stroke_dasharray
            or None
        )
        ox, oy = axis_origin
        for callout in callouts:
            if not callout.leader_path_d:
                continue
            dash_attr = (
                f' stroke-dasharray="{leader_dasharray}"'
                if leader_dasharray else ""
            )
            self._drawing.append(drawsvg.Raw(
                f'<g transform="translate({ox:.2f},{oy:.2f})" '
                f'class="ec-callout-leader">'
                f'<path d="{callout.leader_path_d}" '
                f'stroke="{callout.color}" stroke-width="{leader_stroke_width}" '
                f'stroke-opacity="{leader_opacity}" fill="none"{dash_attr}/>'
                f'</g>'
            ))
        if orient is Orientation.HORIZONTAL:
            for duration in durations:
                self._draw_duration_connectors(config, duration, axis_y)
        else:
            for duration in durations:
                self._draw_duration_connectors_vertical(
                    config, duration, axis_origin[0]
                )

        # Main axis line. Vertical orientation: line runs (axis_x, axis_top)
        # → (axis_x, axis_bottom).
        _axis_style = config.get_line_style("ec-axis-line")
        self._draw_line(
            axis_origin[0],
            axis_origin[1],
            axis_end[0],
            axis_end[1],
            stroke=_axis_style.color,
            stroke_width=_axis_style.width,
            stroke_opacity=_axis_style.opacity,
            stroke_dasharray=_axis_style.dasharray or None,
            css_class="ec-axis-line",
        )

        # Tick/today/fiscal/holiday/timeband features below remain
        # horizontal-only in this release. They are skipped on vertical
        # axes (otherwise the date-format text would write atop the
        # vertical axis line). Vertical falls through to the shared
        # callout-drawing pass below.
        _horizontal = orient is Orientation.HORIZONTAL

        if _horizontal:
            tick_bands_cfg = getattr(config, "timeline_ticks", None)
            if tick_bands_cfg:
                tick_bands = (
                    [tick_bands_cfg] if isinstance(tick_bands_cfg, dict) else list(tick_bands_cfg)
                )
                # Precompute ticks per band so labels can be deduplicated when
                # bands collide on the same day. The band whose unit covers the
                # largest number of days (e.g. month > week > day) wins the label.
                band_ticks: list[list[tuple]] = []
                band_priorities: list[int] = []
                for tb in tick_bands:
                    if not isinstance(tb, dict):
                        band_ticks.append([])
                        band_priorities.append(-1)
                        continue
                    band_ticks.append(
                        self._compute_band_ticks(config, tb, start, end, db)
                    )
                    band_priorities.append(self._tick_unit_priority(tb))
                # Per-date max priority across bands. Equal-priority bands ticking
                # on the same date all draw their labels (each sits on its own
                # label row via label_gap/label_offset_y); only strictly lower
                # priority bands are suppressed.
                max_prio: dict = {}
                for idx, ticks in enumerate(band_ticks):
                    prio = band_priorities[idx]
                    for tick_date, _label in ticks:
                        if tick_date not in max_prio or max_prio[tick_date] < prio:
                            max_prio[tick_date] = prio
                for idx, tb in enumerate(tick_bands):
                    if not isinstance(tb, dict):
                        continue
                    prio = band_priorities[idx]
                    allowed = {
                        d for d, _l in band_ticks[idx] if max_prio.get(d) == prio
                    }
                    self._draw_axis_ticks_from_band(
                        config, tb, start, end, axis_left, axis_right, axis_y, db,
                        ticks=band_ticks[idx],
                        allowed_label_dates=allowed,
                    )
            else:
                self._draw_month_ticks(config, start, end, axis_left, axis_right, axis_y)
            if config.fiscal_lookup and (
                config.timeline_show_fiscal_periods or config.timeline_show_fiscal_quarters
            ):
                self._draw_fiscal_bands(config, start, end, axis_left, axis_right, axis_y)
            self._draw_today_marker(
                config,
                start,
                end,
                axis_left,
                axis_right,
                axis_y,
                area_y,
                area_h,
            )

            # Government holiday icons sit between the axis line and the duration
            # bars (the duration offset already reserves enough vertical space).
            if getattr(config, "timeline_show_holiday_icons", True):
                self._draw_holiday_icons(
                    config, start, end, axis_left, axis_right, axis_y, db
                )

        # Pass 2: draw all boxes, markers, and text on top.
        for callout in callouts:
            self._draw_callout(config, callout, axis_y)
        for duration in durations:
            if duration.orientation is Orientation.VERTICAL:
                self._draw_duration_vertical(config, duration, axis_origin[0])
            else:
                self._draw_duration(config, duration, axis_y)

        # Timebands: top bands stack above the timeline area; bottom bands
        # stack below it. Only drawn when declared in the theme.
        if top_bands:
            self._draw_timeline_bands(
                config, top_bands, area_y, axis_left, axis_right, start, end, db,
                events=event_objs,
            )
        if bottom_bands:
            self._draw_timeline_bands(
                config,
                bottom_bands,
                area_y + area_h - bottom_bands_h,
                axis_left,
                axis_right,
                start,
                end,
                db,
                events=event_objs,
            )

        # After all content is laid out, tighten the SVG viewBox to the actual
        # rendered extent. _shrink_drawing_to_content() runs before
        # _render_content() and uses only the coordinate dict, so it cannot see
        # the dynamic callout / duration row positions computed here. Override
        # the viewBox directly now that all bounds are known.
        if config.shrink_to_content:
            tight = self._actual_content_bounds(
                config,
                callouts,
                durations,
                axis_left,
                axis_right,
                axis_y,
                area_x,
                area_y,
                area_w,
                area_h,
            )
            coordinates["TimelineArea"] = tight
            tx, ty, tw, th = tight
            self._drawing.view_box = (tx, ty, tw, th)
            self._drawing.width = tw
            self._drawing.height = th
            self._content_bbox_svg = (tx, ty, tx + tw, ty + th)

        # Timeline view does not use overflow pages.
        return 0, []

    def _actual_content_bounds(
        self,
        config: "CalendarConfig",
        callouts: list[TimelineCallout],
        durations: list[TimelineDuration],
        axis_left: float,
        axis_right: float,
        axis_y: float,
        area_x: float,
        area_y: float,
        area_w: float,
        area_h: float = 0.0,
    ) -> tuple[float, float, float, float]:
        """
        Compute the tight bounding box (SVG space) of all rendered timeline content.

        Returns (x, y, w, h) suitable for replacing coordinates["TimelineArea"].
        """
        # Seed bounds with the axis line itself (plus tick clearance).
        tick_h = max(6.0, config.timeline_axis_width * 2.5)
        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        date_size = max(8.0, config.weekly_name_text_font_size * 0.95)

        # Axis + tick labels extend above axis_y (smaller SVG y = visually higher)
        axis_tick_top = axis_y - (tick_h + label_size * 1.5)
        # Date labels below axis sit slightly below axis_y (larger SVG y = visually lower)
        axis_date_bottom = axis_y + (date_size * 0.1)

        min_y = axis_tick_top
        max_y = axis_date_bottom

        # Callouts extend above axis_y (box_y is the SVG top of the box)
        for callout in callouts:
            min_y = min(min_y, callout.box_y)

        # Durations extend below axis_y (horizontal) or to the left of
        # axis_x (vertical).
        min_x = axis_left
        max_x = axis_right
        if durations:
            title_size, notes_size, d_date_size, bar_h = self._duration_metrics(config)
            min_duration_offset = self._min_duration_offset(d_date_size)
            duration_offset = max(
                config.timeline_duration_offset_y, min_duration_offset
            )
            lane_gap = max(config.timeline_duration_lane_gap_y, d_date_size * 0.9)
            lane_stride_h = bar_h + (d_date_size * 1.8) + lane_gap
            lane_stride_v = bar_h + lane_gap

            for dur in durations:
                if dur.orientation is Orientation.VERTICAL:
                    if dur.lane_side is Side.PRIMARY:
                        bar_x_left = axis_left + duration_offset + (dur.lane * lane_stride_v)
                        max_x = max(max_x, bar_x_left + bar_h)
                    else:
                        bar_x_right = axis_left - duration_offset - (dur.lane * lane_stride_v)
                        min_x = min(min_x, bar_x_right - bar_h)
                    label_y_top = dur.start_y - (d_date_size * 1.3)
                    label_y_bot = dur.end_y + (d_date_size * 1.3)
                    min_y = min(min_y, label_y_top)
                    max_y = max(max_y, label_y_bot)
                else:
                    bar_bottom = axis_y + duration_offset
                    bar_y = bar_bottom + (dur.lane * lane_stride_h)
                    label_y = bar_y + bar_h + (d_date_size * 1.1)
                    max_y = max(max_y, label_y + d_date_size)

        # Extend bounds for declared timebands (only when present).
        top_bands = list(getattr(config, "timeline_top_time_bands", None) or [])
        bottom_bands = list(getattr(config, "timeline_bottom_time_bands", None) or [])
        top_bands_h = sum(float(b.get("row_height", 14.0)) for b in top_bands)
        bottom_bands_h = sum(float(b.get("row_height", 14.0)) for b in bottom_bands)
        if top_bands_h > 0:
            min_y = min(min_y, area_y)
        if bottom_bands_h > 0:
            max_y = max(max_y, area_y + area_h)

        # X: axis extent (with 4% margins already baked in as area_x offsets),
        # extended to include any vertical-orientation duration lanes that
        # spill to the left of the axis.
        x = min(axis_left, min_x)
        w = max(axis_right, max_x) - x

        # Y: min_y is SVG top, max_y is SVG bottom
        y = min_y
        h = max(1.0, max_y - min_y)

        return (round(x, 2), round(y, 2), round(w, 2), round(h, 2))

    @staticmethod
    def _split_events(
        config: "CalendarConfig",
        events: list[Event],
    ) -> tuple[list[Event], list[Event]]:
        point_events: list[Event] = []
        duration_events: list[Event] = []

        for event in events:
            if event.is_duration:
                if config.includedurations:
                    duration_events.append(event)
            else:
                if config.includeevents:
                    point_events.append(event)

        return point_events, duration_events

    def _layout_callouts(
        self,
        config: "CalendarConfig",
        events: list[Event],
        start: arrow.Arrow,
        end: arrow.Arrow,
        *,
        axis_origin: tuple[float, float],
        axis_length: float,
        orientation: Orientation,
        side: Side,
        style_engine: StyleEngine | None = None,
    ) -> list[TimelineCallout]:
        """Place point-event callouts using the labella VPSC algorithm.

        Delegates label-position optimization to the vendored labella
        primitives (`vendor/labella/`). For each event, returns a
        `TimelineCallout` carrying both the axis dot position and the
        post-VPSC label box position, plus the bezier leader path in
        axis-local coordinates.

        Events whose start date falls outside the user-requested range
        (or that fail to parse) are dropped.
        """
        if not events:
            return []

        # User-range filtering — matches the legacy behavior so events
        # outside the requested window don't get drawn even though the
        # axis itself spans the rendered range.
        user_start = (
            self._safe_day(config.userstart, fallback=start)
            if config.userstart else start
        )
        user_end = (
            self._safe_day(config.userend, fallback=end)
            if config.userend else end
        )

        # Filter events to the user-requested window and assign palette
        # colors in chronological order BEFORE labella runs, so colour
        # assignment is independent of the layout algorithm.
        in_range: list[Event] = []
        for ev in events:
            day = self._safe_day(ev.start, fallback=start)
            if (
                day.floor("day") < user_start.floor("day")
                or day.floor("day") > user_end.floor("day")
            ):
                continue
            in_range.append(ev)
        if not in_range:
            return []

        ordered = sorted(
            in_range,
            key=lambda e: (
                e.start,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )

        palette_primary = config.timeline_top_colors or [
            config.get_text_style("ec-event-name").color
            or config.timeline_name_text_font_color
        ]
        palette_secondary = config.timeline_bottom_colors or palette_primary
        date_rows = max(1, self._CALL_OUT_DATE_ROWS)

        # Pre-resolve color + rule-engine style per event, keyed by identity
        # so the post-labella lookup is robust to reordering (Side.BOTH
        # partitions events into two groups).
        per_event: dict[int, tuple[str, "StyleResult | None", int]] = {}
        for idx, event in enumerate(ordered):
            base_palette = (
                palette_secondary if side is Side.SECONDARY else palette_primary
            )
            color = base_palette[idx % len(base_palette)]
            sr = style_engine.evaluate_event(event) if style_engine else None
            if sr is not None and sr.fill_color:
                color = sr.fill_color
            per_event[id(event)] = (color, sr, idx)

        # Build the date → axis-local position closure. axis_length spans
        # the entire date window; the labella adapter handles minPos/maxPos
        # clamping based on config.
        def pos_for_day(day: arrow.Arrow) -> float:
            span_days = max(1, (end.floor("day") - start.floor("day")).days)
            offset = (day.floor("day") - start.floor("day")).days
            clamped = max(0, min(offset, span_days))
            return axis_length * (clamped / span_days)

        placements = _labella_layout_callouts(
            ordered,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orientation,
            side=side,
            config=config,
            pos_for_day=pos_for_day,
        )

        # For Side.BOTH the secondary-side events get the secondary palette.
        # Walk placements and reassign color for the secondary side.
        out: list[TimelineCallout] = []
        for p in placements:
            color, sr, source_idx = per_event[id(p.event)]
            if p.side is Side.SECONDARY and config.timeline_bottom_colors:
                color = config.timeline_bottom_colors[
                    source_idx % len(config.timeline_bottom_colors)
                ]
                if sr is not None and sr.fill_color:
                    color = sr.fill_color
            out.append(
                TimelineCallout(
                    event=p.event,
                    color=color,
                    x_dot=p.x_dot,
                    y_dot=p.y_dot,
                    lane=p.layer,
                    box_x=p.x_label,
                    box_y=p.y_label,
                    box_width=p.label_w,
                    box_height=p.label_h,
                    date_row=source_idx % date_rows,
                    leader_path_d=p.leader_path_d,
                    axis_origin=p.axis_origin,
                    orientation=p.orientation,
                    style=sr,
                )
            )

        return out

    def _layout_durations(
        self,
        config: "CalendarConfig",
        events: list[Event],
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        style_engine: StyleEngine | None = None,
    ) -> list[TimelineDuration]:
        if not events:
            return []

        ordered = sorted(
            events,
            key=lambda e: (
                e.start,
                e.end,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )

        lane_last_end: list[float] = []
        min_gap = max(10.0, self._page_width * 0.01)
        _layout_notes_style = config.get_text_style("ec-event-notes")
        palette = config.timeline_bottom_colors or [_layout_notes_style.color or config.timeline_notes_text_font_color]
        title_size, notes_size, _, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(_layout_notes_style.font or config.timeline_notes_text_font_name)
        notes_font_path = self._safe_font_path(_layout_notes_style.font or config.timeline_notes_text_font_name)

        out: list[TimelineDuration] = []

        # Compare to the user-typed range (not the weekend-adjusted range)
        # so events ending on an excluded weekend day are not flagged as
        # continuing past the visible diagram.
        user_start = self._safe_day(config.userstart, fallback=start) if config.userstart else start
        user_end = self._safe_day(config.userend, fallback=end) if config.userend else end

        for idx, event in enumerate(ordered):
            start_day = self._safe_day(event.start, fallback=start)
            end_day = self._safe_day(event.end, fallback=start_day)
            if end_day < start_day:
                start_day, end_day = end_day, start_day

            # Skip events entirely outside the visible date range.
            if end_day.floor("day") < user_start.floor("day"):
                continue
            if start_day.floor("day") > user_end.floor("day"):
                continue

            continues_left = start_day.floor("day") < user_start.floor("day")
            continues_right = end_day.floor("day") > user_end.floor("day")

            sx = self._x_for_day(start_day, start, end, axis_left, axis_right)
            ex = self._x_for_day(end_day, start, end, axis_left, axis_right)

            configured_w = (
                float(config.timeline_duration_box_width)
                if config.timeline_duration_box_width is not None
                else 0.0
            )
            if configured_w > 0:
                min_width = configured_w
            else:
                # Increase short duration bars when larger font sizes are used so
                # the name/notes lines can fit within the bar.
                name_w = string_width(
                    event.task_name or "", title_font_path, title_size
                )
                notes_w = string_width(
                    (event.notes or "").strip(), notes_font_path, notes_size
                )
                min_width = max(
                    max(16.0, self._page_width * 0.02),
                    name_w + 12.0,
                    notes_w + 12.0,
                )
            if ex - sx < min_width:
                ex = min(axis_right, sx + min_width)

            lane = self._place_span_in_lane(lane_last_end, sx, ex, min_gap)
            color = palette[idx % len(palette)]
            _sr = style_engine.evaluate_event(event) if style_engine is not None else None
            if _sr is not None and _sr.fill_color:
                color = _sr.fill_color
            out.append(
                TimelineDuration(
                    event=event,
                    color=color,
                    start_x=sx,
                    end_x=ex,
                    lane=lane,
                    min_width=min_width,
                    continues_left=continues_left,
                    continues_right=continues_right,
                    style=_sr,
                )
            )

        return out

    def _layout_durations_vertical(
        self,
        config: "CalendarConfig",
        events: list[Event],
        start: arrow.Arrow,
        end: arrow.Arrow,
        *,
        axis_x: float,
        axis_top: float,
        axis_bottom: float,
        side: Side = Side.SECONDARY,
        style_engine: StyleEngine | None = None,
    ) -> list[TimelineDuration]:
        """Place vertical-orientation duration bars alongside the axis.

        Bars run along the axis from start_y to end_y. Lanes stack
        perpendicularly away from the axis (each new overlapping bar sits
        further out). The per-bar `min_width` field carries the minimum
        *along-axis* length for vertical bars so short events still have
        room for their labels.

        ``side`` selects which side(s) of the axis bars go on:
        - PRIMARY  → right side
        - SECONDARY → left side
        - BOTH     → alternate by start date, each side gets independent
          lane tracking
        """
        if not events:
            return []

        ordered = sorted(
            events,
            key=lambda e: (
                e.start,
                e.end,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )

        if side is Side.BOTH:
            # Chronological alternation mirrors how callouts split for
            # Side.BOTH; gives a balanced layout regardless of input order.
            primary_events = [e for i, e in enumerate(ordered) if i % 2 == 0]
            secondary_events = [e for i, e in enumerate(ordered) if i % 2 == 1]
            return (
                self._layout_durations_vertical(
                    config, primary_events, start, end,
                    axis_x=axis_x, axis_top=axis_top, axis_bottom=axis_bottom,
                    side=Side.PRIMARY, style_engine=style_engine,
                )
                + self._layout_durations_vertical(
                    config, secondary_events, start, end,
                    axis_x=axis_x, axis_top=axis_top, axis_bottom=axis_bottom,
                    side=Side.SECONDARY, style_engine=style_engine,
                )
            )

        lane_last_end: list[float] = []
        min_gap = max(10.0, self._page_height * 0.01)
        _layout_notes_style = config.get_text_style("ec-event-notes")
        palette = config.timeline_bottom_colors or [
            _layout_notes_style.color or config.timeline_notes_text_font_color
        ]
        title_size, notes_size, _, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(
            _layout_notes_style.font or config.timeline_notes_text_font_name
        )
        notes_font_path = self._safe_font_path(
            _layout_notes_style.font or config.timeline_notes_text_font_name
        )

        out: list[TimelineDuration] = []

        user_start = self._safe_day(config.userstart, fallback=start) if config.userstart else start
        user_end = self._safe_day(config.userend, fallback=end) if config.userend else end

        for idx, event in enumerate(ordered):
            start_day = self._safe_day(event.start, fallback=start)
            end_day = self._safe_day(event.end, fallback=start_day)
            if end_day < start_day:
                start_day, end_day = end_day, start_day

            if end_day.floor("day") < user_start.floor("day"):
                continue
            if start_day.floor("day") > user_end.floor("day"):
                continue

            continues_top = start_day.floor("day") < user_start.floor("day")
            continues_bottom = end_day.floor("day") > user_end.floor("day")

            sy = self._y_for_day(start_day, start, end, axis_top, axis_bottom)
            ey = self._y_for_day(end_day, start, end, axis_top, axis_bottom)

            configured_len = (
                float(config.timeline_duration_box_width)
                if config.timeline_duration_box_width is not None
                else 0.0
            )
            if configured_len > 0:
                min_length = configured_len
            else:
                # Text reads bottom→top once rotated, so the bar's
                # along-axis length is the available width for the label.
                name_w = string_width(
                    event.task_name or "", title_font_path, title_size
                )
                notes_w = string_width(
                    (event.notes or "").strip(), notes_font_path, notes_size
                )
                min_length = max(
                    max(16.0, self._page_height * 0.02),
                    name_w + 12.0,
                    notes_w + 12.0,
                )
            if ey - sy < min_length:
                ey = min(axis_bottom, sy + min_length)

            lane = self._place_span_in_lane(lane_last_end, sy, ey, min_gap)
            color = palette[idx % len(palette)]
            _sr = style_engine.evaluate_event(event) if style_engine is not None else None
            if _sr is not None and _sr.fill_color:
                color = _sr.fill_color
            out.append(
                TimelineDuration(
                    event=event,
                    color=color,
                    start_x=axis_x,
                    end_x=axis_x,
                    lane=lane,
                    min_width=min_length,
                    continues_left=continues_top,
                    continues_right=continues_bottom,
                    style=_sr,
                    orientation=Orientation.VERTICAL,
                    start_y=sy,
                    end_y=ey,
                    lane_side=side,
                )
            )

        return out

    @staticmethod
    def _place_span_in_lane(
        lane_last_end: list[float],
        start_x: float,
        end_x: float,
        min_gap: float,
    ) -> int:
        for lane, last_end in enumerate(lane_last_end):
            if start_x >= (last_end + min_gap):
                lane_last_end[lane] = end_x
                return lane

        lane_last_end.append(end_x)
        return len(lane_last_end) - 1

    @staticmethod
    def _boxes_overlap(
        box_a: tuple[float, float, float, float],
        box_b: tuple[float, float, float, float],
        pad: float = 0.0,
    ) -> bool:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        return not (
            ax2 + pad <= bx1 or bx2 + pad <= ax1 or ay2 + pad <= by1 or by2 + pad <= ay1
        )


    def _draw_callout(
        self,
        config: "CalendarConfig",
        item: TimelineCallout,
        axis_y: float,
    ) -> None:
        title = item.event.task_name or "(untitled)"
        notes = (item.event.notes or "").strip()

        title_font_size, notes_font_size, date_font_size = self._callout_metrics(config)

        # Always draw a plain circle on the axis — icons go in the label box.
        # `item.x_dot` / `item.y_dot` already account for orientation; the
        # `axis_y` arg is retained for backwards-compatibility but only
        # consulted by the legacy horizontal-only date-label rendering path
        # further down in this method.
        self._draw_timeline_marker(
            config,
            x=item.x_dot,
            y=item.y_dot,
            color=item.color,
            icon_name=None,
        )

        # Label box.
        _callout_style = config.get_box_style("ec-callout-box")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=_callout_style.fill_opacity,
            stroke=item.color,
            stroke_width=_callout_style.stroke_width,
            stroke_opacity=0.95,
            stroke_dasharray=_callout_style.stroke_dasharray or None,
        )
        self._draw_rect(
            item.box_x,
            item.box_y,
            item.box_width,
            item.box_height,
            css_class="ec-callout-box",
            **rect_kwargs,
        )

        has_icon = bool(item.event.icon and self._resolve_icon_svg(item.event.icon))
        icon_gap = 2.0
        icon_reserved = (title_font_size + icon_gap) if has_icon else 0.0

        _name_style = config.get_text_style("ec-event-name")
        _notes_style = config.get_text_style("ec-event-notes")
        tk_name = self._tk("text:event_name")
        tk_notes = self._tk("text:event_notes")
        name_font_default = (
            tk_name.get("font")
            or config.timeline_name_text_font_name
            or _name_style.font
        )
        notes_font_default = (
            tk_notes.get("font")
            or config.timeline_notes_text_font_name
            or _notes_style.font
        )
        title_font_path = self._safe_font_path(name_font_default)
        notes_font_path = self._safe_font_path(notes_font_default)
        fitted_title, fitted_notes = self._fit_box_text_sizes(
            title,
            notes,
            item.box_width - 12.0 - icon_reserved,
            item.box_height,
            title_font_path,
            notes_font_path,
            title_font_size,
            notes_font_size,
        )

        text_x = item.box_x + 6.0
        title_y = item.box_y + fitted_title * 1.15
        notes_y = title_y + (fitted_notes * 1.55)

        event_text_color = (
            tk_name.get("color")
            or config.timeline_name_text_font_color
            or _name_style.color
            or item.color
        )
        name_font, _, name_color, name_opacity = _sr.text_override(
            "event_name",
            font=name_font_default,
            color=event_text_color,
            opacity=_name_style.opacity,
        )
        notes_color_base = (
            tk_notes.get("color")
            or config.timeline_notes_text_font_color
            or _notes_style.color
            or event_text_color
        )
        notes_font, _, notes_color, notes_opacity = _sr.text_override(
            "event_notes",
            font=notes_font_default,
            color=notes_color_base,
            opacity=_notes_style.opacity,
        )
        icon_to_draw = _sr.icon if _sr.icon is not None else item.event.icon
        icon_color = _sr.icon_color or event_text_color

        if has_icon:
            self._draw_icon_svg(
                icon_to_draw,
                text_x,
                title_y,
                fitted_title,
                anchor="start",
                color=icon_color,
                css_class="ec-event-icon",
                box_token=(
                    "box:milestone"
                    if getattr(item.event, "milestone", False)
                    else "box:event"
                ),
                box_ctx=self._event_ctx(item.event),
            )
            title_text_x = text_x + fitted_title + icon_gap
            title_max_w = item.box_width - 12.0 - fitted_title - icon_gap
        else:
            title_text_x = text_x
            title_max_w = item.box_width - 12.0

        self._draw_text(
            title_text_x,
            title_y,
            title,
            name_font,
            fitted_title,
            fill=name_color,
            fill_opacity=name_opacity,
            max_width=title_max_w,
            css_class="ec-event-name",
        )

        if notes:
            self._draw_text(
                text_x,
                notes_y,
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                max_width=item.box_width - 12.0,
                css_class="ec-event-notes",
            )

        # Date label below the dot — horizontal-only. On vertical timelines
        # the date is implicit (events are ordered along the axis); the
        # label box itself shows the task name.
        if item.orientation is Orientation.HORIZONTAL:
            _event_date_style = config.get_text_style("ec-event-date")
            tk_event_date = self._tk("text:event_date")
            date_label = format_arrow_date(
                self._safe_day(item.event.start, fallback=arrow.now()),
                config.timeline_date_format,
            )
            date_row_gap_factor = 1.35
            date_y = axis_y - (
                date_font_size * (0.9 + (item.date_row * date_row_gap_factor))
            )
            date_font, _, date_color, _ = _sr.text_override(
                "event_date",
                font=(
                    _event_date_style.font
                    or tk_event_date.get("font")
                    or config.timeline_date_font
                ),
                color=(
                    _event_date_style.color
                    or tk_event_date.get("color")
                    or event_text_color
                ),
            )
            self._draw_text(
                item.x_dot,
                date_y,
                date_label,
                date_font,
                date_font_size,
                fill=date_color,
                anchor="middle",
                css_class="ec-event-date",
            )

    def _draw_duration_connectors(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_y: float,
    ) -> None:
        """Draw only the vertical aligner lines from the axis to the duration bar."""
        title_size, notes_size, date_size, bar_h = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_h + (date_size * 1.8) + lane_gap
        bar_bottom = axis_y + duration_offset
        bar_y = bar_bottom + (item.lane * lane_stride)
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        self._draw_line(
            item.start_x,
            axis_y,
            item.start_x,
            bar_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )
        self._draw_line(
            item.end_x,
            axis_y,
            item.end_x,
            bar_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )

    def _draw_duration(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_y: float,
    ) -> None:
        title = item.event.task_name or "(untitled duration)"
        notes = (item.event.notes or "").strip()
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)

        title_size, notes_size, date_size, bar_h = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_h + (date_size * 1.8) + lane_gap

        bar_bottom = axis_y + duration_offset
        bar_y = bar_bottom + (item.lane * lane_stride)

        # Duration bar.
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=_dur_bar_style.opacity,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.9,
            stroke_dasharray=_dur_bar_style.dasharray or None,
        )
        self._draw_rect(
            item.start_x,
            bar_y,
            max(1.0, item.end_x - item.start_x),
            bar_h,
            css_class="ec-duration-bar",
            **rect_kwargs,
        )

        # Start/end markers on the main axis.
        _marker_style = config.get_box_style("ec-milestone-marker")
        marker_fill = _sr.fill_color if _sr.fill_color is not None else item.color
        marker_stroke = _sr.stroke_color if _sr.stroke_color is not None else _marker_style.stroke
        self._draw_circle(
            item.start_x,
            axis_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )
        self._draw_circle(
            item.end_x,
            axis_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )

        # Continuation icons for duration bars clipped by the visible range.
        # continues_left == event starts before the visualization start
        # ("before"); continues_right == event ends after the visualization
        # end ("after"). Driven by the global `continuation` theme section.
        if (item.continues_left or item.continues_right) and bool(
            getattr(config, "show_continuation_icon", True)
        ):
            cont_h = float(getattr(config, "continuation_icon_height", 8.0))
            cont_color_cfg = getattr(config, "continuation_icon_color", None)
            cont_color = cont_color_cfg if cont_color_cfg else item.color
            cont_baseline = bar_y + bar_h * 0.5 + cont_h * 0.3
            if item.continues_left:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_before", None),
                        "horizontal",
                        "arrow-left",
                    ),
                    item.start_x,
                    cont_baseline,
                    cont_h,
                    anchor="start",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )
            if item.continues_right:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_after", None),
                        "horizontal",
                        "arrow-right",
                    ),
                    item.end_x,
                    cont_baseline,
                    cont_h,
                    anchor="end",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )

        _dur_name_style = config.get_text_style("ec-event-name")
        _dur_notes_style = config.get_text_style("ec-event-notes")
        tk_dur_name = self._tk("text:event_name")
        tk_dur_notes = self._tk("text:event_notes")
        dur_name_font_default = (
            tk_dur_name.get("font")
            or config.timeline_name_text_font_name
            or _dur_name_style.font
        )
        dur_notes_font_default = (
            tk_dur_notes.get("font")
            or config.timeline_notes_text_font_name
            or _dur_notes_style.font
        )
        title_font_path = self._safe_font_path(dur_name_font_default)
        notes_font_path = self._safe_font_path(dur_notes_font_default)
        text_w = max(10.0, item.end_x - item.start_x - 6.0)
        fitted_title, fitted_notes = self._fit_box_text_sizes(
            title,
            notes,
            text_w,
            bar_h,
            title_font_path,
            notes_font_path,
            title_size,
            notes_size,
        )
        duration_text_color = (
            tk_dur_name.get("color")
            or config.timeline_name_text_font_color
            or _dur_name_style.color
            or item.color
        )
        title_font_base = dur_name_font_default
        title_font, _, name_color, name_opacity = _sr.text_override(
            "duration_name",
            font=title_font_base,
            color=duration_text_color,
            opacity=_dur_name_style.opacity,
        )
        # Vertically center the title (and notes, when present) within the bar
        # so the text sits in the lower portion of the rectangle rather than
        # being pinned to its top edge.
        has_notes = bool(notes and config.include_notes)
        line1_h = fitted_title * 1.2
        line2_h = (fitted_notes * 1.2) if has_notes else 0.0
        text_block_h = line1_h + line2_h
        text_top_y = bar_y + max(0.0, (bar_h - text_block_h) / 2.0)
        title_y = text_top_y + fitted_title * 0.85
        show_icon = bool(config.timeline_duration_icon_visible) and bool(item.event.icon)
        if show_icon:
            icon_size = fitted_title
            try:
                title_w = string_width(title, title_font_path, fitted_title)
            except Exception:
                title_w = len(title) * fitted_title * 0.55
            gap = 2.0
            total_w = icon_size + gap + title_w
            available_w = max(8.0, text_w)
            icon_scale_x = min(1.0, available_w / total_w) if total_w > available_w else 1.0
            effective_icon_w = icon_size * icon_scale_x
            effective_text_w = min(title_w * icon_scale_x, available_w - effective_icon_w - gap)
            group_x0 = (item.start_x + item.end_x) / 2 - (effective_icon_w + gap + effective_text_w) / 2.0
            draw_x = max(item.start_x, group_x0)
            icon_transform = None
            if icon_scale_x < 1.0:
                icon_transform = (
                    f"translate({draw_x:.4f} {title_y:.4f}) "
                    f"scale({icon_scale_x:.6f} 1) "
                    f"translate({-draw_x:.4f} {-title_y:.4f})"
                )
            dur_icon = _sr.icon if _sr.icon is not None else item.event.icon
            dur_icon_color = _sr.icon_color or duration_text_color
            icon_drawn = self._draw_icon_svg(
                dur_icon,
                draw_x,
                title_y,
                icon_size,
                anchor="start",
                color=dur_icon_color,
                fallback_name=config.default_missing_icon,
                fallback_color=dur_icon_color,
                transform=icon_transform,
                css_class="ec-duration-icon",
                box_token="box:duration",
                box_ctx=self._event_ctx(item.event),
            )
            text_x = draw_x + effective_icon_w + gap if icon_drawn else (item.start_x + item.end_x) / 2
            self._draw_text(
                text_x,
                title_y,
                title,
                title_font,
                fitted_title,
                fill=name_color,
                fill_opacity=name_opacity,
                anchor="start" if icon_drawn else "middle",
                max_width=max(8.0, item.end_x - text_x - 2),
                css_class="ec-event-name",
            )
        else:
            self._draw_text(
                (item.start_x + item.end_x) / 2,
                title_y,
                title,
                title_font,
                fitted_title,
                fill=name_color,
                fill_opacity=name_opacity,
                anchor="middle",
                max_width=text_w,
                css_class="ec-event-name",
            )

        if has_notes:
            notes_color_base = (
                tk_dur_notes.get("color")
                or config.timeline_notes_text_font_color
                or _dur_notes_style.color
                or duration_text_color
            )
            notes_font, _, notes_color, notes_opacity = _sr.text_override(
                "duration_notes",
                font=dur_notes_font_default,
                color=notes_color_base,
                opacity=_dur_notes_style.opacity,
            )
            notes_y = text_top_y + line1_h + fitted_notes * 0.85
            self._draw_text(
                (item.start_x + item.end_x) / 2,
                notes_y,
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                anchor="middle",
                max_width=text_w,
                css_class="ec-event-notes",
            )

        # Keep start/end labels on the same Y baseline.
        _dur_date_style = config.get_text_style("ec-duration-date")
        tk_dur_date = self._tk("text:duration_date")
        date_font_base = (
            _dur_date_style.font
            or config.timeline_duration_date_font
            or tk_dur_date.get("font")
            or config.timeline_date_font
        )
        date_color_base = (
            _dur_date_style.color
            or config.timeline_duration_date_color
            or tk_dur_date.get("color")
            or duration_text_color
        )
        start_date_font, _, start_date_color, _ = _sr.text_override(
            "duration_start_date",
            font=date_font_base,
            color=date_color_base,
        )
        end_date_font, _, end_date_color, _ = _sr.text_override(
            "duration_end_date",
            font=date_font_base,
            color=date_color_base,
        )
        date_y = bar_y + bar_h + (date_size * 1.1)
        self._draw_text(
            item.start_x,
            date_y,
            format_arrow_date(start_day, config.timeline_date_format),
            start_date_font,
            date_size,
            fill=start_date_color,
            anchor="start",
            css_class="ec-duration-date",
        )
        self._draw_text(
            item.end_x,
            date_y,
            format_arrow_date(end_day, config.timeline_date_format),
            end_date_font,
            date_size,
            fill=end_date_color,
            anchor="end",
            css_class="ec-duration-date",
        )

    def _draw_duration_connectors_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_x: float,
    ) -> None:
        """Horizontal aligner lines from the vertical axis to the duration bar."""
        title_size, notes_size, date_size, bar_thickness = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_thickness + lane_gap
        # PRIMARY = right of axis (+X), SECONDARY = left (-X).
        sign = 1.0 if item.lane_side is Side.PRIMARY else -1.0
        bar_near_axis_x = axis_x + sign * (duration_offset + (item.lane * lane_stride))
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        self._draw_line(
            axis_x,
            item.start_y,
            bar_near_axis_x,
            item.start_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )
        self._draw_line(
            axis_x,
            item.end_y,
            bar_near_axis_x,
            item.end_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )

    def _draw_duration_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_x: float,
    ) -> None:
        """Draw a vertical-orientation duration bar (left of axis)."""
        title = item.event.task_name or "(untitled duration)"
        notes = (item.event.notes or "").strip()
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)

        title_size, notes_size, date_size, bar_thickness = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_thickness + lane_gap

        if item.lane_side is Side.PRIMARY:
            # Right of axis: bars grow rightward, bar_x is the left edge.
            bar_x = axis_x + duration_offset + (item.lane * lane_stride)
        else:
            # Left of axis: bars grow leftward, bar_x is still the left
            # edge of the rectangle (axis_x - offset - lane*stride - thickness).
            bar_right = axis_x - duration_offset - (item.lane * lane_stride)
            bar_x = bar_right - bar_thickness
        bar_y = item.start_y
        bar_h = max(1.0, item.end_y - item.start_y)

        _dur_bar_style = config.get_line_style("ec-duration-bar")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=_dur_bar_style.opacity,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.9,
            stroke_dasharray=_dur_bar_style.dasharray or None,
        )
        self._draw_rect(
            bar_x,
            bar_y,
            bar_thickness,
            bar_h,
            css_class="ec-duration-bar",
            **rect_kwargs,
        )

        # Start/end markers on the main axis at the bar's start/end y.
        _marker_style = config.get_box_style("ec-milestone-marker")
        marker_fill = _sr.fill_color if _sr.fill_color is not None else item.color
        marker_stroke = _sr.stroke_color if _sr.stroke_color is not None else _marker_style.stroke
        self._draw_circle(
            axis_x,
            item.start_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )
        self._draw_circle(
            axis_x,
            item.end_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )

        # Continuation icons for bars clipped above/below the visible range.
        # continues_left == event starts before visualization start ("before");
        # continues_right == event ends after visualization end ("after").
        # On a vertical axis the second element of a [horizontal, vertical]
        # icon-list pair selects the orientation-appropriate glyph.
        if (item.continues_left or item.continues_right) and bool(
            getattr(config, "show_continuation_icon", True)
        ):
            cont_h = float(getattr(config, "continuation_icon_height", 8.0))
            cont_color_cfg = getattr(config, "continuation_icon_color", None)
            cont_color = cont_color_cfg if cont_color_cfg else item.color
            cont_x = bar_x + bar_thickness * 0.5
            if item.continues_left:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_before", None),
                        "vertical",
                        "arrow-up",
                    ),
                    cont_x,
                    item.start_y + cont_h * 0.5,
                    cont_h,
                    anchor="middle",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )
            if item.continues_right:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_after", None),
                        "vertical",
                        "arrow-down",
                    ),
                    cont_x,
                    item.end_y - cont_h * 0.5,
                    cont_h,
                    anchor="middle",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )

        # Title + notes rotated -90° so they read bottom→top inside the bar.
        _dur_name_style = config.get_text_style("ec-event-name")
        _dur_notes_style = config.get_text_style("ec-event-notes")
        tk_dur_name = self._tk("text:event_name")
        tk_dur_notes = self._tk("text:event_notes")
        dur_name_font_default = (
            tk_dur_name.get("font")
            or config.timeline_name_text_font_name
            or _dur_name_style.font
        )
        dur_notes_font_default = (
            tk_dur_notes.get("font")
            or config.timeline_notes_text_font_name
            or _dur_notes_style.font
        )
        title_font_path = self._safe_font_path(dur_name_font_default)
        notes_font_path = self._safe_font_path(dur_notes_font_default)
        # Available "width" for the rotated text is the bar's along-axis length.
        text_w = max(10.0, bar_h - 6.0)
        fitted_title, fitted_notes = self._fit_box_text_sizes(
            title,
            notes,
            text_w,
            bar_thickness,
            title_font_path,
            notes_font_path,
            title_size,
            notes_size,
        )
        duration_text_color = (
            tk_dur_name.get("color")
            or config.timeline_name_text_font_color
            or _dur_name_style.color
            or item.color
        )
        title_font, _, name_color, name_opacity = _sr.text_override(
            "duration_name",
            font=dur_name_font_default,
            color=duration_text_color,
            opacity=_dur_name_style.opacity,
        )

        has_notes = bool(notes and config.include_notes)
        line1_h = fitted_title * 1.2
        line2_h = (fitted_notes * 1.2) if has_notes else 0.0
        text_block_h = line1_h + line2_h
        # Anchor the rotation around the bar's center; pre-rotation the text
        # is laid out horizontally centered at (cx, cy) and rotate(-90)
        # turns it into a vertical run reading bottom→top.
        cx = bar_x + bar_thickness / 2.0
        cy = bar_y + bar_h / 2.0
        # Title baseline (pre-rotation) sits above center by half text_block;
        # adjust so the title line ends up on the +y side after rotation
        # (i.e. closer to the bar's start_y / top edge).
        title_pre_y = cy + (bar_thickness / 2.0) - max(0.0, (bar_thickness - text_block_h) / 2.0) - line2_h - (fitted_title * 0.15)
        rot = f"rotate(-90 {cx:.4f} {cy:.4f})"
        self._draw_text(
            cx,
            title_pre_y,
            title,
            title_font,
            fitted_title,
            fill=name_color,
            fill_opacity=name_opacity,
            anchor="middle",
            max_width=text_w,
            transform=rot,
            css_class="ec-event-name",
        )
        if has_notes:
            notes_color_base = (
                tk_dur_notes.get("color")
                or config.timeline_notes_text_font_color
                or _dur_notes_style.color
                or duration_text_color
            )
            notes_font, _, notes_color, notes_opacity = _sr.text_override(
                "duration_notes",
                font=dur_notes_font_default,
                color=notes_color_base,
                opacity=_dur_notes_style.opacity,
            )
            notes_pre_y = title_pre_y + line1_h
            self._draw_text(
                cx,
                notes_pre_y,
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                anchor="middle",
                max_width=text_w,
                transform=rot,
                css_class="ec-event-notes",
            )

        # Date labels above the bar's start edge and below its end edge,
        # placed at the bar's horizontal center.
        _dur_date_style = config.get_text_style("ec-duration-date")
        tk_dur_date = self._tk("text:duration_date")
        date_font_base = (
            _dur_date_style.font
            or config.timeline_duration_date_font
            or tk_dur_date.get("font")
            or config.timeline_date_font
        )
        date_color_base = (
            _dur_date_style.color
            or config.timeline_duration_date_color
            or tk_dur_date.get("color")
            or duration_text_color
        )
        start_date_font, _, start_date_color, _ = _sr.text_override(
            "duration_start_date",
            font=date_font_base,
            color=date_color_base,
        )
        end_date_font, _, end_date_color, _ = _sr.text_override(
            "duration_end_date",
            font=date_font_base,
            color=date_color_base,
        )
        self._draw_text(
            cx,
            bar_y - (date_size * 0.3),
            format_arrow_date(start_day, config.timeline_date_format),
            start_date_font,
            date_size,
            fill=start_date_color,
            anchor="middle",
            css_class="ec-duration-date",
        )
        self._draw_text(
            cx,
            bar_y + bar_h + (date_size * 1.1),
            format_arrow_date(end_day, config.timeline_date_format),
            end_date_font,
            date_size,
            fill=end_date_color,
            anchor="middle",
            css_class="ec-duration-date",
        )

    def _draw_timeline_marker(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        color: str,
        icon_name: str | None,
    ) -> None:
        """Draw default filled circle marker or icon-in-circle marker."""
        radius = max(2.5, config.timeline_marker_radius)

        # Resolve effective icon: fall back to "position-align" (red) when the
        # requested icon name exists but is not found in the icon table.
        effective_icon = icon_name
        effective_color = color
        if icon_name and self._resolve_icon_svg(icon_name) is None:
            effective_icon = "position-align"
            effective_color = "red"

        icon_found = self._resolve_icon_svg(effective_icon) is not None

        _marker_style = config.get_box_style("ec-milestone-marker")
        if icon_found:
            self._draw_circle(
                x,
                y,
                radius=radius,
                fill="none",
                stroke=effective_color,
                stroke_width=_marker_style.stroke_width,
            )
            # DB-provided SVG icon centered in the circle.
            self._draw_icon_svg(
                effective_icon,
                x,
                y,
                max(7.0, config.timeline_icon_size),
                anchor="middle",
                color=effective_color,
                css_class="ec-event-icon",
            )
            return

        self._draw_circle(
            x,
            y,
            radius=radius,
            fill=color,
            stroke=_marker_style.stroke,
            stroke_width=_marker_style.stroke_width,
        )

    def _duration_metrics(
        self,
        config: "CalendarConfig",
    ) -> tuple[float, float, float, float]:
        """Return (title_size, notes_size, date_size, bar_height).

        Consults ``text:event_name`` / ``text:event_notes`` / ``text:duration_date``
        tokens first; falls back to legacy ``timeline_*_font_size`` (with the
        same 0.85 / 0.82 scale-down factors that pre-migration code applied)
        and finally to the page-scaled ``weekly_name_text_font_size``.
        Token sizes are taken at face value — if a theme defines an explicit
        size for the duration bar text, it's expected to be that size.
        """
        title_size = (
            self._tk("text:event_name").get("size")
            or (
                float(config.timeline_name_text_font_size * 0.85)
                if config.timeline_name_text_font_size is not None
                else max(8.0, config.weekly_name_text_font_size * 0.86)
            )
        )
        notes_size = (
            self._tk("text:event_notes").get("size")
            or (
                float(config.timeline_notes_text_font_size * 0.82)
                if config.timeline_notes_text_font_size is not None
                else max(7.0, config.weekly_name_text_font_size * 0.74)
            )
        )
        date_size = (
            self._tk("text:duration_date").get("size")
            or (
                float(config.timeline_duration_date_font_size)
                if config.timeline_duration_date_font_size is not None
                else max(7.0, config.weekly_name_text_font_size * 0.78)
            )
        )
        if config.timeline_duration_box_height is not None:
            bar_h = max(8.0, float(config.timeline_duration_box_height))
            return title_size, notes_size, date_size, bar_h

        top_pad = max(2.0, notes_size * 0.30)
        line_gap = max(1.0, notes_size * 0.25)
        bottom_pad = max(2.0, notes_size * 0.30)
        bar_h = top_pad + title_size + line_gap + notes_size + bottom_pad
        return title_size, notes_size, date_size, bar_h

    @staticmethod
    def _min_duration_offset(date_size: float) -> float:
        """Minimum axis-to-bar clearance so timeline date labels remain unobstructed."""
        return max(22.0, date_size * 3.2)

    def _draw_timeline_bands(
        self,
        config: "CalendarConfig",
        bands: list[dict],
        block_top_y: float,
        axis_left: float,
        axis_right: float,
        start: arrow.Arrow,
        end: arrow.Arrow,
        db: "CalendarDB",
        events: "list[Event] | None" = None,
    ) -> None:
        """Draw a stack of timebands using shared.timeband.build_segments().

        Each band gets a row of the configured ``row_height``. Bands are stacked
        downward starting at ``block_top_y``. Segment x positions are mapped via
        the same date→x function used by the timeline axis.

        Bands with ``unit: "icon"`` are rendered per visible day via
        :func:`shared.icon_band.compute_icon_band_days` rather than as labeled
        segments.
        """
        if not bands:
            return

        start_d = start.floor("day").date()
        end_d = end.floor("day").date()
        # visible_days for date/dow units (continuous calendar — timeline does
        # not skip weekends).
        from datetime import timedelta
        visible_days: list = []
        d = start_d
        while d <= end_d:
            visible_days.append(d)
            d = d + timedelta(days=1)

        _events: list[Event] = events or []
        _day_classes: dict = (
            {d: classify_day(d, db, config) for d in visible_days} if db is not None else {}
        )

        def _classify(day_) -> frozenset:
            return _day_classes.get(day_, frozenset())

        _band_text_style = config.get_text_style("ec-label")
        tk_band_label = self._tk("text:label")
        text_color = str(tk_band_label.get("color") or _band_text_style.color or "black")
        text_opacity = float(
            tk_band_label.get("opacity")
            if tk_band_label.get("opacity") is not None
            else _band_text_style.opacity
        )

        row_y = block_top_y
        for band in bands:
            row_h = float(band.get("row_height", 14.0))
            unit = str(band.get("unit", "week")).strip().lower()

            # ── Icon band — one cell per visible day, icons driven by rules ──
            if unit == "icon":
                icon_rules = list(band.get("icon_rules") or [])
                day_icon_map = compute_icon_band_days(
                    _events, icon_rules, visible_days, classify_fn=_classify
                )
                icon_h = float(band.get("icon_height") or row_h * 0.65)
                fill = str(band.get("fill_color") or "none")
                day_cells: list[tuple[float, float, list[tuple[str, str]]]] = []
                for day_d in visible_days:
                    day_arrow = arrow.Arrow(day_d.year, day_d.month, day_d.day)
                    next_arrow = arrow.Arrow(day_d.year, day_d.month, day_d.day).shift(days=1)
                    cell_x = self._x_for_day(day_arrow, start, end, axis_left, axis_right)
                    cell_x2 = self._x_for_day(next_arrow, start, end, axis_left, axis_right)
                    cell_w = max(0.0, cell_x2 - cell_x)
                    day_cells.append((cell_x, cell_w, day_icon_map.get(day_d, [])))
                self._draw_icon_band_row(day_cells, row_y, row_h, icon_h, fill)
                sep_y = row_y + row_h
                self._draw_line(
                    axis_left, sep_y, axis_right, sep_y,
                    stroke="#cccccc", stroke_width=0.5,
                    css_class="ec-separator",
                )
                row_y += row_h
                continue

            fill_color = str(band.get("fill_color") or "none")
            alt_fill_color = str(band.get("alt_fill_color") or "none")
            text_align = str(band.get("text_align", "center")).strip().lower()
            if text_align not in {"left", "center", "right"}:
                text_align = "center"
            band_font = str(
                band.get("font")
                or tk_band_label.get("font")
                or _band_text_style.font
                or config.timeline_text_font_name
            )
            band_font_color = str(band.get("font_color") or text_color)
            band_label_color = str(band.get("label_color") or band_font_color)
            font_size = float(
                band.get("font_size")
                or tk_band_label.get("size")
                or max(7.0, row_h * 0.55)
            )

            segments = _build_band_segments(
                band, start_d, end_d, config,
                visible_days=visible_days,
                db=db,
                week_start_default=0,
                fiscal_year_start_month_default=int(
                    getattr(config, "blockplan_fiscal_year_start_month", 2) or 2
                ),
            )

            for seg_idx, seg in enumerate(segments):
                seg_start_arrow = arrow.Arrow(seg.start.year, seg.start.month, seg.start.day)
                seg_end_arrow = arrow.Arrow(
                    seg.end_exclusive.year, seg.end_exclusive.month, seg.end_exclusive.day
                )
                x1 = self._x_for_day(seg_start_arrow, start, end, axis_left, axis_right)
                x2 = self._x_for_day(seg_end_arrow, start, end, axis_left, axis_right)
                seg_w = max(0.0, x2 - x1)
                if seg_w <= 0:
                    continue

                fill = alt_fill_color if seg_idx % 2 else fill_color
                if fill and fill.strip().lower() not in {"none", "transparent", ""}:
                    self._draw_rect(
                        x1, row_y, seg_w, row_h,
                        fill=fill,
                        fill_opacity=1.0,
                        css_class="ec-band-cell",
                    )

                label = seg.label
                if label:
                    pad = 2.0
                    if text_align == "center":
                        text_x = x1 + seg_w / 2.0
                        anchor = "middle"
                        max_w = seg_w - pad * 2
                    elif text_align == "right":
                        text_x = x2 - pad
                        anchor = "end"
                        max_w = seg_w - pad * 2
                    else:
                        text_x = x1 + pad
                        anchor = "start"
                        max_w = seg_w - pad * 2
                    self._draw_text(
                        text_x, row_y + row_h * 0.72, label,
                        band_font, font_size,
                        fill=band_label_color,
                        fill_opacity=text_opacity,
                        anchor=anchor,
                        max_width=max_w,
                        css_class="ec-label",
                    )

            sep_y = row_y + row_h
            self._draw_line(
                axis_left, sep_y, axis_right, sep_y,
                stroke="#cccccc", stroke_width=0.5,
                css_class="ec-separator",
            )
            row_y += row_h

    @staticmethod
    def _tick_label_top_clearance(
        config: "CalendarConfig", tick_bands_cfg: object
    ) -> float:
        """Maximum vertical extent (pts) of any tick band's label above the axis.

        Used to size the area above axis_y when there are no callouts/events to
        accommodate, so the axis can be raised toward the top edge while still
        leaving room for the tick labels themselves.
        """
        if not tick_bands_cfg:
            return 0.0
        bands = (
            [tick_bands_cfg]
            if isinstance(tick_bands_cfg, dict)
            else list(tick_bands_cfg)
        )
        default_label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        default_tick_h = max(6.0, config.timeline_axis_width * 2.5)
        max_above = 0.0
        for tb in bands:
            if not isinstance(tb, dict):
                continue
            tick_h = float(tb.get("tick_length") or default_tick_h)
            lsize = float(
                tb.get("label_font_size")
                or tb.get("font_size")
                or default_label_size
            )
            offset = tb.get("label_offset_y")
            gap = tb.get("label_gap")
            if offset is not None:
                lo = float(offset)
            elif gap is not None:
                lo = tick_h + float(gap)
            else:
                lo = tick_h + lsize * 1.5
            max_above = max(max_above, lo + lsize)
        return max_above

    @staticmethod
    def _tick_unit_priority(band: dict) -> int:
        """Approximate days-per-segment for a tick band's unit.

        Larger units (month) win the shared-day label over smaller ones (week,
        day). Used to deduplicate labels when two bands tick on the same date.
        """
        unit = str(band.get("unit", "date")).strip().lower()
        if unit == "interval":
            try:
                return max(1, int(band.get("interval_days", 14) or 14))
            except (TypeError, ValueError):
                return 14
        return {
            "year": 365,
            "fiscal_quarter": 91,
            "month": 30,
            "fiscal_period": 28,
            "week": 7,
            "dow": 7,
            "date": 1,
            "countdown": 1,
            "countup": 1,
        }.get(unit, 1)

    def _compute_band_ticks(
        self,
        config: "CalendarConfig",
        band: dict,
        start: arrow.Arrow,
        end: arrow.Arrow,
        db: "CalendarDB",
    ) -> list[tuple[date, str]]:
        """Return the (date, label) ticks a band would draw."""
        from datetime import timedelta

        start_d = start.floor("day").date()
        end_d = end.floor("day").date()
        visible_days: list = []
        d = start_d
        while d <= end_d:
            visible_days.append(d)
            d = d + timedelta(days=1)

        segments = _build_band_segments(
            band, start_d, end_d, config,
            visible_days=visible_days,
            db=db,
            week_start_default=0,
            fiscal_year_start_month_default=int(
                getattr(config, "blockplan_fiscal_year_start_month", 2) or 2
            ),
        )
        if not segments:
            return []

        fmt = band.get("label_format") or band.get("date_format")
        fmt_str = str(fmt) if fmt else None
        include_endpoints = bool(band.get("include_endpoints", True))

        def _format_label(d: date, fallback: str = "") -> str:
            if fmt_str:
                return format_arrow_date(arrow.get(d), fmt_str)
            return fallback

        ticks: list[tuple[date, str]] = []
        seen: set[date] = set()
        if include_endpoints:
            ticks.append((start_d, _format_label(start_d)))
            seen.add(start_d)
        for seg in segments:
            if seg.start in seen:
                continue
            ticks.append((seg.start, _format_label(seg.start, fallback=seg.label)))
            seen.add(seg.start)
        if include_endpoints and end_d not in seen:
            ticks.append((end_d, _format_label(end_d)))
        return ticks

    def _draw_axis_ticks_from_band(
        self,
        config: "CalendarConfig",
        band: dict,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        db: "CalendarDB",
        ticks: list[tuple[date, str]] | None = None,
        allowed_label_dates: set[date] | None = None,
    ) -> None:
        """Draw axis ticks at the start of each segment produced by a band dict.

        Accepts any unit supported by shared.timeband.build_segments
        (fiscal_quarter, fiscal_period, month, week, interval, date, dow,
        countdown, countup). Each segment.start gets a tick line; segment.label
        is rendered above the axis.

        Tick label_format is always an Arrow date format applied to each
        tick's own date — independent of the band's unit. This lets any
        supported unit produce date-style tick labels like "MMM D" or
        "MMMM DD". When no label_format/date_format is given, fall back to the
        segment's generated label.

        When ``allowed_label_dates`` is provided, only ticks whose date is in
        that set draw a label; the tick line is still drawn. The caller uses
        this to suppress duplicate labels when multiple bands tick on the
        same day.
        """
        if ticks is None:
            ticks = self._compute_band_ticks(config, band, start, end, db)
        if not ticks:
            return

        # Tick decoration: per-band overrides.
        _tick_style = config.get_line_style("ec-axis-tick")
        default_tick_h = max(6.0, config.timeline_axis_width * 2.5)
        tick_h = float(band.get("tick_length") or default_tick_h)
        tick_width = float(band.get("tick_width") or 1.0)
        tick_opacity = float(band.get("tick_opacity") if band.get("tick_opacity") is not None else 0.35)
        tick_color = str(band.get("tick_color") or _tick_style.color)
        tick_dash = band.get("tick_dasharray") or _tick_style.dasharray or None

        # Label styling.
        default_label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        label_size = float(
            band.get("label_font_size")
            or band.get("font_size")
            or default_label_size
        )
        draw_labels = bool(band.get("show_labels", True)) and len(ticks) <= int(
            band.get("max_label_count", 60)
        )
        tk_event_date = self._tk("text:event_date")
        label_color = str(
            band.get("label_color")
            or band.get("font_color")
            or tk_event_date.get("color")
            or _tick_style.color
        )
        label_opacity = float(
            band.get("label_opacity") if band.get("label_opacity") is not None else 0.8
        )
        font_name = str(
            band.get("font")
            or tk_event_date.get("font")
            or config.timeline_date_font
        )
        label_offset = band.get("label_offset_y")
        label_gap = band.get("label_gap")
        if label_offset is not None:
            label_offset_y = float(label_offset)
        elif label_gap is not None:
            label_offset_y = tick_h + float(label_gap)
        else:
            label_offset_y = tick_h + label_size * 1.5

        last_idx = len(ticks) - 1
        for idx, (tick_date, tick_label) in enumerate(ticks):
            tick_arrow = arrow.Arrow(tick_date.year, tick_date.month, tick_date.day)
            x = self._x_for_day(tick_arrow, start, end, axis_left, axis_right)
            self._draw_line(
                x,
                axis_y - tick_h,
                x,
                axis_y + tick_h,
                stroke=tick_color,
                stroke_width=tick_width,
                stroke_opacity=tick_opacity,
                stroke_dasharray=tick_dash,
                css_class="ec-axis-tick",
            )
            if (
                draw_labels
                and tick_label
                and (allowed_label_dates is None or tick_date in allowed_label_dates)
            ):
                if idx == 0:
                    label_anchor = "start"
                elif idx == last_idx:
                    label_anchor = "end"
                else:
                    label_anchor = "middle"
                self._draw_text(
                    x,
                    axis_y - label_offset_y,
                    tick_label,
                    font_name,
                    label_size,
                    fill=label_color,
                    fill_opacity=label_opacity,
                    anchor=label_anchor,
                    css_class="ec-label",
                )

    def _draw_holiday_icons(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        db: "CalendarDB",
    ) -> None:
        """Render one icon per government-holiday date below the axis line."""
        size = float(getattr(config, "timeline_holiday_icon_size", 10.0))
        y_offset = float(getattr(config, "timeline_holiday_icon_y_offset", 4.0))
        if size <= 0:
            return
        color = getattr(config, "timeline_holiday_icon_color", None)
        baseline_y = axis_y + y_offset + (size * 0.80)

        seen: set[str] = set()
        for day in arrow.Arrow.range("day", start.floor("day"), end.floor("day")):
            daykey = day.format("YYYYMMDD")
            if daykey in seen:
                continue
            seen.add(daykey)
            try:
                hols = db.get_holidays_for_date(daykey, config.country)
            except Exception:
                continue
            icon_name = next(
                (h.get("icon") for h in hols
                 if h.get("nonworkday") and h.get("icon")),
                None,
            )
            if not icon_name:
                continue
            x = self._x_for_day(day, start, end, axis_left, axis_right)
            self._draw_icon_svg(
                str(icon_name),
                x,
                baseline_y,
                size,
                anchor="middle",
                color=color,
                css_class="ec-holiday-icon",
            )

    def _draw_month_ticks(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
    ) -> None:
        # Default ticks to the first day of each month inside the visible range.
        month_start = start.floor("month")
        if month_start < start.floor("day"):
            month_start = month_start.shift(months=1)
        month_end = end.floor("month")
        ticks = (
            list(arrow.Arrow.range("month", month_start, month_end))
            if month_start <= month_end
            else []
        )
        if not ticks:
            return

        draw_labels = len(ticks) <= 18
        tick_h = max(6.0, config.timeline_axis_width * 2.5)
        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)

        _tick_style = config.get_line_style("ec-axis-tick")
        for m in ticks:
            x = self._x_for_day(m, start, end, axis_left, axis_right)
            self._draw_line(
                x,
                axis_y - tick_h,
                x,
                axis_y + tick_h,
                stroke=_tick_style.color,
                stroke_width=1.0,
                stroke_opacity=0.35,
                stroke_dasharray=_tick_style.dasharray or None,
                css_class="ec-axis-tick",
            )
            if draw_labels:
                self._draw_text(
                    x,
                    axis_y - (tick_h + label_size * 1.5),
                    format_arrow_date(m, config.timeline_tick_label_format),
                    self._tk("text:event_date").get("font") or config.timeline_date_font,
                    label_size,
                    fill=self._tk("text:event_date").get("color") or _tick_style.color,
                    fill_opacity=0.8,
                    anchor="middle",
                    css_class="ec-label",
                )

    def _draw_fiscal_bands(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
    ) -> None:
        """Draw fiscal period and/or quarter band rows above the timeline axis.

        Each band row is a sequence of colored rectangles with centered labels,
        positioned just above the month tick labels.
        """
        from shared.fiscal_renderer import (
            build_fiscal_period_segments,
            build_fiscal_quarter_segments,
        )

        tick_h = max(6.0, config.timeline_axis_width * 2.5)
        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        band_h = label_size * 1.8
        band_gap = 2.0

        # y position: start just above the month tick label area
        # month tick labels are at axis_y - (tick_h + label_size * 1.5)
        top_of_month_labels = axis_y - (tick_h + label_size * 1.5 + label_size)
        band_bottom = top_of_month_labels - band_gap

        start_date = start.date()
        end_date = end.date()

        rows: list[list] = []
        if config.timeline_show_fiscal_quarters:
            rows.append(build_fiscal_quarter_segments(start_date, end_date, config))
        if config.timeline_show_fiscal_periods:
            rows.append(build_fiscal_period_segments(start_date, end_date, config))

        alt_colors = ["#e8eaf0", "#d4d8e8"]
        label_color = config.get_line_style("ec-axis-tick").color

        for row_idx, segments in enumerate(rows):
            row_top = band_bottom - (row_idx + 1) * (band_h + band_gap)
            row_bottom = row_top + band_h
            for seg_idx, seg in enumerate(segments):
                seg_start_arrow = arrow.get(seg.start)
                seg_end_arrow = arrow.get(seg.end_exclusive)
                x1 = self._x_for_day(seg_start_arrow, start, end, axis_left, axis_right)
                x2 = self._x_for_day(seg_end_arrow, start, end, axis_left, axis_right)
                x1 = max(x1, axis_left)
                x2 = min(x2, axis_right)
                if x2 <= x1:
                    continue
                fill = alt_colors[seg_idx % 2]
                self._draw_rect(
                    x1, row_top, x2 - x1, band_h,
                    fill=fill, fill_opacity=0.6,
                    stroke="#aaaaaa", stroke_width=0.5,
                    css_class="ec-callout-box",
                )
                cx = (x1 + x2) / 2.0
                cy = row_top + band_h / 2.0 + label_size * 0.35
                self._draw_text(
                    cx, cy, seg.label,
                    self._tk("text:event_date").get("font") or config.timeline_date_font,
                    label_size,
                    fill=label_color,
                    fill_opacity=0.9,
                    anchor="middle",
                    max_width=x2 - x1 - 4.0,
                    css_class="ec-label",
                )

    def _draw_today_marker(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        area_y: float,
        area_h: float,
    ) -> None:
        today = self._resolve_today(config)
        if today < start.floor("day") or today > end.floor("day"):
            return

        x = self._x_for_day(today, start, end, axis_left, axis_right)

        # Bounds within which the line may be drawn (SVG: top = small y, bottom = large y).
        area_top = area_y  # visually topmost edge (smallest SVG y)
        area_bottom = area_y + area_h  # visually bottommost edge (largest SVG y)

        direction = (config.timeline_today_line_direction or "both").strip().lower()
        length = max(0.0, config.timeline_today_line_length)

        if length == 0.0:
            # Full available span in the requested direction.
            if direction == "above":
                line_top = area_top
                line_bottom = axis_y
            elif direction == "below":
                line_top = axis_y
                line_bottom = area_bottom
            else:  # "both"
                line_top = area_top
                line_bottom = area_bottom
        else:
            if direction == "above":
                line_top = axis_y - length
                line_bottom = axis_y
            elif direction == "below":
                line_top = axis_y
                line_bottom = axis_y + length
            else:  # "both"
                half = length / 2.0
                line_top = axis_y - half
                line_bottom = axis_y + half

        # Clamp to page content area so the line never overruns the margins.
        line_top = max(line_top, area_top)
        line_bottom = min(line_bottom, area_bottom)

        _today_line_style = config.get_line_style("ec-today-line")
        _today_label_style = config.get_text_style("ec-today-label")
        self._draw_line(
            x,
            line_top,
            x,
            line_bottom,
            stroke=_today_line_style.color,
            stroke_width=1.0,
            stroke_opacity=0.55,
            stroke_dasharray=_today_line_style.dasharray or None,
            css_class="ec-today-line",
        )
        tk_today_label = self._tk("text:today_label")
        label_size = (
            tk_today_label.get("size")
            or max(7.0, config.weekly_name_text_font_size * 0.8)
        )
        preferred_y = line_top - max(0.0, config.timeline_today_label_offset_y)
        # Keep label baseline inside SVG bounds.
        min_y = label_size * 1.1
        max_y = self._page_height - (label_size * 0.6)
        if preferred_y < min_y:
            preferred_y = line_top + (label_size * 1.25)
        label_y = max(min_y, min(preferred_y, max_y))
        self._draw_text(
            x,
            label_y,
            config.timeline_today_label_text or "Today",
            tk_today_label.get("font") or _today_label_style.font or config.timeline_date_font,
            label_size,
            fill=tk_today_label.get("color") or _today_label_style.color,
            fill_opacity=0.85,
            anchor="middle",
            css_class="ec-today-label",
        )

    # _draw_circle() is inherited from BaseSVGRenderer.

    @staticmethod
    def _safe_day(date_str: str, fallback: arrow.Arrow) -> arrow.Arrow:
        try:
            return arrow.get(str(date_str)[:8], "YYYYMMDD")
        except Exception:
            return fallback

    @staticmethod
    def _resolve_today(config: "CalendarConfig") -> arrow.Arrow:
        """Resolve 'today' from config override (if set), otherwise use current date."""
        raw = (config.timeline_today_date or "").strip()
        if not raw:
            return arrow.now().floor("day")

        for fmt in ("YYYYMMDD", "YYYY-MM-DD"):
            try:
                return arrow.get(raw, fmt).floor("day")
            except Exception:
                continue
        try:
            return arrow.get(raw).floor("day")
        except Exception:
            return arrow.now().floor("day")

    @staticmethod
    def _x_for_day(
        day: arrow.Arrow,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
    ) -> float:
        span_days = max(1, (end.floor("day") - start.floor("day")).days)
        day_offset = (day.floor("day") - start.floor("day")).days
        clamped = max(0, min(day_offset, span_days))
        return axis_left + ((axis_right - axis_left) * (clamped / span_days))

    @staticmethod
    def _y_for_day(
        day: arrow.Arrow,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
    ) -> float:
        """Vertical analogue of :meth:`_x_for_day`. Y increases downward
        with later dates (start at top, end at bottom)."""
        span_days = max(1, (end.floor("day") - start.floor("day")).days)
        day_offset = (day.floor("day") - start.floor("day")).days
        clamped = max(0, min(day_offset, span_days))
        return axis_top + ((axis_bottom - axis_top) * (clamped / span_days))

    @staticmethod
    def _safe_font_path(font_name: str) -> str:
        try:
            return get_font_path(font_name)
        except KeyError:
            return get_font_path("RobotoCondensed-Bold")

    def _callout_metrics(self, config: "CalendarConfig") -> tuple[float, float, float]:
        """Return (title_size, notes_size, date_size) for point-event callouts.

        Consults ``text:event_name`` / ``text:event_notes`` / ``text:event_date``
        tokens first; falls back to the legacy ``timeline_*_font_size`` fields
        and finally to the page-scaled ``weekly_name_text_font_size``.
        """
        title_size = (
            self._tk("text:event_name").get("size")
            or (
                float(config.timeline_name_text_font_size)
                if config.timeline_name_text_font_size is not None
                else max(10.0, config.weekly_name_text_font_size + 2.0)
            )
        )
        notes_size = (
            self._tk("text:event_notes").get("size")
            or (
                float(config.timeline_notes_text_font_size)
                if config.timeline_notes_text_font_size is not None
                else max(8.0, config.weekly_name_text_font_size * 0.9)
            )
        )
        date_size = (
            self._tk("text:event_date").get("size")
            or max(8.0, config.weekly_name_text_font_size * 0.95)
        )
        return title_size, notes_size, date_size
