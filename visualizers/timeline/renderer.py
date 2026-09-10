"""
Timeline SVG renderer.

Renders a horizontal, date-scaled timeline with distinct point-event callouts
and duration bars aligned to start/end dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

from datetime import date

import arrow
import drawsvg

from config.config import get_font_path, resolve_continuation_icon
from renderers.glyph_cache import get_ink_extents
from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.date_utils import format_arrow_date
from shared.rule_engine import StyleEngine, StyleResult
from shared.wbs_filter import wbs_group, wbs_sort_key
from shared.day_classifier import classify_day
from shared.icon_band import compute_icon_band_days
from shared.timeband import build_segments as _build_band_segments
from visualizers.timeline.labella_adapter import (
    CalloutPlacement,
    layout_callouts as _labella_layout_callouts,
)
from visualizers.timeline.packing import pack_callouts as _pack_callouts
from shared.orientation import Orientation, Side

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict

#: Breathing room between the top of the axis tick labels and the innermost
#: row of callout boxes.
_AXIS_LABEL_MARGIN = 2.0


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
    # Labella leader. Empty string is permitted for fallback paths.
    leader_path_d: str = ""
    axis_origin: tuple[float, float] = (0.0, 0.0)
    orientation: Orientation = Orientation.HORIZONTAL
    style: StyleResult | None = None
    #: False when packing found no room for the box. The leader is still
    #: drawn, capped with the theme's missing-box icon; nothing else is.
    placed: bool = True

    @property
    def x(self) -> float:
        """Backwards-compat alias for the dot x position (used by older
        renderer code paths that pre-date the orientation refactor)."""
        return self.x_dot


@dataclass(frozen=True)
class TimelineDuration:
    """Duration bar placement alongside the timeline axis.

    For HORIZONTAL orientation: `start_x`/`end_x` are the bar endpoints
    along the axis — exactly the x of the event's start and end dates, so
    bars sharing a date share an edge — and `lane` stacks downward below
    the axis.

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
    # True when the bar is narrower than `min_width`, i.e. than its own text
    # needs.  Horizontal bars are never widened past their dates to make room
    # — both edges belong to the calendar — so the drawer answers this by
    # breaking the name across the middle column's two rows, dropping the
    # notes that row would otherwise carry, and condensing every cell of the
    # bar by one shared factor.
    text_overflow: bool = False


#: Inset from a duration bar's edge to its in-bar start / end date.
_DURATION_DATE_PAD_X: float = 3.0

#: Clear space kept between an in-bar date and the bar's title.
_DURATION_DATE_GAP_X: float = 4.0

#: Smallest drawn size for an icon in a duration bar's side column; a cell
#: with less room than this is left empty rather than smudged.
_DURATION_ICON_MIN_SIZE: float = 3.0


class TimelineRenderer(BaseSVGRenderer):
    """Renderer for timeline visualization."""

    # Tokens pre-resolved once per render; see BaseSVGRenderer._populate_tokens.
    TOKEN_VISUALIZER = "timeline"
    TOKENS = (
        "text:event_name", "text:event_notes", "text:event_date",
        "text:duration_date", "text:label", "text:today_label",
        "line:axis", "line:today", "line:tick", "line:duration_bar",
        "icon:event", "icon:milestone",
    )

    #: Outermost ink drawn beside a vertical axis — tick dates, holiday
    #: marks, fiscal columns, timeband columns — tracked during the draw
    #: pass so ``--shrink`` does not crop what the layout never placed.
    #: ``None`` until something is drawn; reset per page.
    _side_ink_min_x: float | None = None
    _side_ink_max_x: float | None = None

    # NOTE: ``_callout_metrics`` is defined near the bottom of the file.
    # An earlier duplicate definition existed at this point pre-migration
    # (Python silently used the last one); removed during this migration
    # so the token-aware version is the single source of truth.

    @staticmethod
    def _ink_extents_pt(font_path: str | None, size: float) -> tuple[float, float]:
        """Ink height above and below the baseline, in points."""
        if not font_path or size <= 0:
            return size * 0.75, size * 0.22
        ascent, descent = get_ink_extents(font_path)
        return ascent * size, descent * size

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        """Assemble the timeline page for either axis orientation.

        Sequence: compute axis geometry (horizontal or vertical) →
        labella callout layout for point events (`_layout_callouts`) and
        lane layout for durations → draw in layers: leader paths first
        (under everything), then durations, callout boxes, the axis with
        ticks/timebands, and finally the today marker.  Returns
        ``(0, [])`` — the timeline emits no overflow *page*; density is
        labella's problem, not pagination's.  (A duration bar too narrow
        for its name breaks the name over two rows instead — see
        :py:meth:`_duration_cells`.)
        """
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
        # A vertical axis has two sides to spend, and the horizontal layout
        # spends its two on callouts above and bars below.  Mirror that by
        # default rather than stacking both on one side, where the bars end
        # up under the callout boxes.
        duration_side = self._duration_side(config, label_side)
        # Tick dates go where the bars are not: a bar's first lane starts a
        # few points off the axis, exactly where a date would land.
        tick_label_side = self._tick_label_side(duration_side)

        # Room for the timeband stacks, taken off the ends of the content
        # area: above and below a horizontal chart, left and right of a
        # vertical one, where "above" and "below" turn into.  A band's
        # `row_height` is its thickness across the axis either way.
        top_bands = list(getattr(config, "timeline_top_time_bands", None) or [])
        bottom_bands = list(getattr(config, "timeline_bottom_time_bands", None) or [])
        top_bands_h = sum(float(b.get("row_height", 14.0)) for b in top_bands)
        bottom_bands_h = sum(float(b.get("row_height", 14.0)) for b in bottom_bands)

        event_objs = [Event.from_dict(e) for e in events]
        self._load_icon_svg_cache(db)
        self._populate_tokens(config)
        self._side_ink_min_x = None
        self._side_ink_max_x = None
        point_events, duration_events = self._split_events(config, event_objs)
        style_engine = StyleEngine(_timeline_style_rules(config))
        # One color per WBS group for the whole chart, so a phase's events,
        # milestones and bars match instead of each layout cycling its own
        # palette independently.
        group_colors = self._wbs_group_colors(
            config, list(point_events) + list(duration_events)
        )

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
                # Nothing above the axis but its own tick dates, so it can
                # rise to just past them.
                axis_y = inner_y + self._tick_side_clearance(config, start, end) + 4.0
            axis_origin = (axis_left, axis_y)
            axis_length = axis_right - axis_left
            # End-of-axis coordinates for the line draw and downstream uses.
            axis_end = (axis_right, axis_y)
        else:
            axis_top = area_y + (area_h * 0.04)
            axis_bottom = area_y + (area_h * 0.96)
            # The band stacks claim the outer edges; the axis is placed in
            # what is left, exactly as the horizontal branch does with the
            # top and bottom of its area.
            inner_x = area_x + top_bands_h
            inner_w = max(1.0, area_w - top_bands_h - bottom_bands_h)
            # Pick the axis x so each populated side has room. With events
            # visible, callouts dominate the layout: keep the 44% bias that
            # leaves a wider label column. With --noevents the only
            # across-axis content is the duration lanes, so the axis goes by
            # where the bars went: centred when they split across both
            # sides, hard right when they stack to the left, hard left when
            # they stack to the right.
            if getattr(config, "includeevents", True):
                axis_x = inner_x + (inner_w * 0.44)
            elif duration_side is Side.BOTH:
                axis_x = inner_x + (inner_w * 0.50)
            elif duration_side is Side.SECONDARY:
                axis_x = inner_x + (inner_w * 0.90)
            else:
                axis_x = inner_x + (inner_w * 0.10)
            if not getattr(config, "includeevents", True):
                # The tick dates take the side the bars left free; keep the
                # axis far enough in for them, as the horizontal branch does
                # for the dates above its own axis.
                clear = self._tick_side_clearance(config, start, end) + 4.0
                if tick_label_side is Side.SECONDARY:
                    axis_x = max(axis_x, inner_x + clear)
                else:
                    axis_x = min(axis_x, inner_x + inner_w - clear)
            axis_origin = (axis_x, axis_top)
            axis_length = axis_bottom - axis_top
            axis_end = (axis_x, axis_bottom)
            # Legacy locals so the horizontal-only feature blocks below can
            # safely no-op when checked.
            axis_left = axis_x
            axis_right = axis_x
            axis_y = axis_top

        # Room one side of the axis has for its stack of callout rows. The
        # axis sits at 44% of the content area, so the near side is the
        # smaller of the two — using it bounds both sides safely.
        # A box stroked exactly on the page edge loses half its border to
        # the clip, so the bounds are inset by half the stroke.
        _edge_inset = config.get_box_style("ec-callout-box").stroke_width / 2.0
        if orient is Orientation.HORIZONTAL:
            room_low = max(0.0, axis_y - (area_y + top_bands_h))
            room_high = max(0.0, (area_y + area_h - bottom_bands_h) - axis_y)
            label_bounds = (area_x + _edge_inset, area_x + area_w - _edge_inset)
        else:
            room_low = max(0.0, axis_origin[0] - (area_x + top_bands_h))
            room_high = max(
                0.0, (area_x + area_w - bottom_bands_h) - axis_origin[0]
            )
            label_bounds = (area_y + _edge_inset, area_y + area_h - _edge_inset)
        callout_room = self._callout_room(orient, label_side, room_low, room_high)

        callouts = self._layout_callouts(
            config,
            point_events,
            start,
            end,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orient,
            side=label_side,
            # Rows past the edge of the drawable area carry labels nobody
            # can read, so the layout stops buying them there. Under
            # --shrink there is no such edge — the viewBox is grown to
            # whatever the layout needs — so the stack goes as deep as it
            # likes, the same licence the duration lanes get below.
            max_extent=None if config.shrink_to_content else callout_room,
            # A box that runs off the paper is a box the reader loses the
            # end of, so placement is bounded by the page, not the axis.
            label_bounds=label_bounds,
            group_colors=group_colors,
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
                group_colors=group_colors,
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
                side=duration_side,
                style_engine=style_engine,
                group_colors=group_colors,
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
        # How far the duration band may reach before it leaves the paper.
        # None under --shrink: the viewBox is grown to whatever the bars
        # need, so every lane is drawn however deep the stack goes.
        if config.shrink_to_content:
            duration_limit = None
            room_primary = room_secondary = None
        elif orient is Orientation.HORIZONTAL:
            duration_limit = area_y + area_h - bottom_bands_h
            room_primary = room_secondary = None
        else:
            # Vertical bars fan out on both sides of the axis, and the axis
            # is not centred, so each side is measured against its own room.
            duration_limit = None
            room_primary = max(0.0, area_x + area_w - axis_origin[0])
            room_secondary = max(0.0, axis_origin[0] - area_x)

        def _vertical_room(item: TimelineDuration) -> float | None:
            if config.shrink_to_content:
                return None
            return (
                room_primary
                if item.lane_side is Side.PRIMARY
                else room_secondary
            )

        if orient is Orientation.HORIZONTAL:
            for duration in durations:
                self._draw_duration_connectors(
                    config, duration, axis_y, duration_limit
                )
        else:
            for duration in durations:
                self._draw_duration_connectors_vertical(
                    config, duration, axis_origin[0], _vertical_room(duration)
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

        # The today marker, fiscal bands, holiday icons and timebands below
        # remain horizontal-only in this release. Axis ticks are not: a
        # vertical axis draws the same theme's bands turned on their side
        # (see _draw_axis_ticks_from_band_vertical).
        _horizontal = orient is Orientation.HORIZONTAL

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
                if _horizontal:
                    self._draw_axis_ticks_from_band(
                        config, tb, start, end, axis_left, axis_right, axis_y, db,
                        ticks=band_ticks[idx],
                        allowed_label_dates=allowed,
                    )
                else:
                    self._draw_axis_ticks_from_band_vertical(
                        config, tb, start, end, axis_origin[1], axis_end[1],
                        axis_origin[0], db,
                        ticks=band_ticks[idx],
                        allowed_label_dates=allowed,
                        label_side=tick_label_side,
                    )
        elif _horizontal:
            self._draw_month_ticks(config, start, end, axis_left, axis_right, axis_y)
        else:
            self._draw_month_ticks_vertical(
                config, start, end, axis_origin[1], axis_end[1], axis_origin[0],
                label_side=tick_label_side,
            )

        if config.fiscal_lookup and (
            config.timeline_show_fiscal_periods or config.timeline_show_fiscal_quarters
        ):
            if _horizontal:
                self._draw_fiscal_bands(config, start, end, axis_left, axis_right, axis_y)
            else:
                self._draw_fiscal_bands_vertical(
                    config, start, end, axis_origin[1], axis_end[1], axis_origin[0],
                    side=tick_label_side,
                )

        if _horizontal:
            self._draw_today_marker(
                config, start, end, axis_left, axis_right, axis_y, area_y, area_h,
            )
        else:
            self._draw_today_marker_vertical(
                config, start, end, axis_origin[1], axis_end[1], axis_origin[0],
                area_x, area_w,
                label_bounds=(
                    area_x + top_bands_h,
                    area_x + area_w - bottom_bands_h,
                ),
            )

        # Government holiday icons sit between the axis line and the duration
        # bars (the duration offset already reserves enough space for them).
        if getattr(config, "timeline_show_holiday_icons", True):
            if _horizontal:
                self._draw_holiday_icons(
                    config, start, end, axis_left, axis_right, axis_y, db
                )
            else:
                self._draw_holiday_icons_vertical(
                    config, start, end, axis_origin[1], axis_end[1], axis_origin[0],
                    db, side=duration_side,
                )

        # Pass 2: draw all boxes, markers, and text on top.
        for callout in callouts:
            self._draw_callout(config, callout, axis_y)
        for duration in durations:
            if duration.orientation is Orientation.VERTICAL:
                self._draw_duration_vertical(
                    config, duration, axis_origin[0], _vertical_room(duration)
                )
            else:
                self._draw_duration(config, duration, axis_y, duration_limit)

        # Timebands: top bands stack above the timeline area; bottom bands
        # stack below it. Only drawn when declared in the theme.
        if top_bands:
            if _horizontal:
                self._draw_timeline_bands(
                    config, top_bands, area_y, axis_left, axis_right, start, end, db,
                    events=event_objs,
                )
            else:
                self._draw_timeline_bands_vertical(
                    config, top_bands, area_x + top_bands_h,
                    axis_origin[1], axis_end[1], start, end, db,
                    events=event_objs, sign=-1.0,
                )
        if bottom_bands:
            if _horizontal:
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
            else:
                self._draw_timeline_bands_vertical(
                    config, bottom_bands, area_x + area_w - bottom_bands_h,
                    axis_origin[1], axis_end[1], start, end, db,
                    events=event_objs, sign=1.0,
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

        # Holiday icons and their date labels hang below the axis. Durations
        # usually reach further down and would cover this, but a timeline with
        # no duration bars would otherwise crop the band away under --shrink.
        if getattr(config, "timeline_show_holiday_icons", True):
            max_y = max(max_y, axis_y + self._holiday_band_extent(config))

        # Durations extend below axis_y (horizontal) or to the left of
        # axis_x (vertical).
        min_x = axis_left
        max_x = axis_right

        # Callouts extend above axis_y (box_y is the SVG top of the box), and
        # along the axis as well: a packed box starts on its own date and runs
        # a full box-width from there, so the last one reaches the axis end.
        # Half the box's stroke sits outside its rect, so count that too or
        # the final border is shaved off by the viewBox.
        half_stroke = config.get_box_style("ec-callout-box").stroke_width / 2.0
        for callout in callouts:
            min_y = min(min_y, callout.box_y - half_stroke)
            max_y = max(max_y, callout.box_y + callout.box_height + half_stroke)
            min_x = min(min_x, callout.box_x - half_stroke)
            max_x = max(
                max_x, callout.box_x + callout.box_width + half_stroke
            )

        if durations:
            title_size, notes_size, d_date_size, bar_h = self._duration_metrics(config)
            min_duration_offset = self._min_duration_offset(config, d_date_size)
            duration_offset = max(
                config.timeline_duration_offset_y, min_duration_offset
            )
            lane_gap = max(config.timeline_duration_lane_gap_y, d_date_size * 0.9)
            lane_stride_h = bar_h + lane_gap
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
                    max_y = max(max_y, bar_y + bar_h)

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
        # spill to the left of the axis — and the tick labels, which are
        # written beside a vertical axis during the draw pass.
        if self._side_ink_min_x is not None:
            min_x = min(min_x, self._side_ink_min_x)
        if self._side_ink_max_x is not None:
            max_x = max(max_x, self._side_ink_max_x)
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
        """Split into (point_events, duration_events), honoring the
        --noevents / --nodurations content filters."""
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
        max_extent: float | None = None,
        label_bounds: tuple[float, float] | None = None,
        group_colors: dict[str, str] | None = None,
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

        group_colors = group_colors or {}
        group_depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)

        palette_primary = config.timeline_top_colors or [
            config.get_text_style("ec-event-name").color
            or config.timeline_name_text_font_color
        ]
        palette_secondary = config.timeline_bottom_colors or palette_primary

        # Pre-resolve color + rule-engine style per event, keyed by identity
        # so the post-labella lookup is robust to reordering (Side.BOTH
        # partitions events into two groups).
        per_event: dict[int, tuple[str, "StyleResult | None", int]] = {}
        for idx, event in enumerate(ordered):
            base_palette = (
                palette_secondary if side is Side.SECONDARY else palette_primary
            )
            group = wbs_group(event.wbs, group_depth) if group_colors else None
            color = (
                group_colors[group]
                if group is not None and group in group_colors
                else base_palette[idx % len(base_palette)]
            )
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

        place = (
            _pack_callouts
            if config.timeline_event_placement == "packed"
            else _labella_layout_callouts
        )
        placements = place(
            ordered,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orientation,
            side=side,
            config=config,
            pos_for_day=pos_for_day,
            # The tick dates are written between the axis and the first
            # row of callouts, whichever way the axis runs, so the row has
            # to start past them.  Zero when no labels will be drawn.
            min_layer_gap=self._axis_label_clearance(
                config, start, end, orientation=orientation
            ),
            max_extent=max_extent,
            label_bounds=label_bounds,
        )

        # For Side.BOTH the secondary-side events get the secondary palette
        # — unless a WBS group already decided the color, which has to hold
        # on both sides of the axis or the group stops being one color.
        out: list[TimelineCallout] = []
        for p in placements:
            color, sr, source_idx = per_event[id(p.event)]
            if (
                not group_colors
                and p.side is Side.SECONDARY
                and config.timeline_bottom_colors
            ):
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
                    leader_path_d=p.leader_path_d,
                    axis_origin=p.axis_origin,
                    orientation=p.orientation,
                    style=sr,
                    placed=getattr(p, "placed", True),
                )
            )

        return out

    @staticmethod
    def _wbs_group_colors(
        config: "CalendarConfig", events: "Sequence[Event]"
    ) -> dict[str, str]:
        """One color per WBS group, shared by every item drawn on the chart.

        Events, milestones and duration bars are laid out separately but
        belong to one schedule, so a phase reads as a phase only if its
        colour is the same above and below the axis.  The map is therefore
        built once over all of them, in date order, so a group takes the
        palette entry its earliest item would have taken.

        ``timeline_top_colors`` is the palette: with one colour per group
        there is only one palette to draw from, so a theme's
        ``bottom_colors`` no longer separates durations from callouts while
        grouping is on.

        Returns ``{}`` when grouping is off, which leaves each layout to its
        own per-item palette cycling.
        """
        depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)
        if depth <= 0:
            return {}

        _notes_style = config.get_text_style("ec-event-notes")
        palette = (
            config.timeline_top_colors
            or config.timeline_bottom_colors
            or [_notes_style.color or config.timeline_notes_text_font_color]
        )

        ordered = sorted(
            events,
            key=lambda e: (
                e.start,
                e.end,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )
        colors: dict[str, str] = {}
        for event in ordered:
            group = wbs_group(event.wbs, depth)
            if group not in colors:
                colors[group] = palette[len(colors) % len(palette)]
        return colors

    @staticmethod
    def _order_durations(
        config: "CalendarConfig",
        events: list[Event],
        group_colors: dict[str, str] | None = None,
    ) -> tuple[list[Event], dict[int, str]]:
        """Order duration events and decide what color each one gets.

        Bars are grouped by the first ``timeline_wbs_group_depth``
        segments of their WBS, so ``NP.3.S1.4`` and ``NP.3.S2.1`` both land
        in ``NP.3``.  A group's bars sort together and take one color from
        the palette, which is what lets a phase read as a band without a
        legend.  Unnumbered bars form their own block after the numbered
        ones — interleaving them by date would scatter them through the
        hierarchy, the same reasoning the gantt's row ordering uses.

        Depth 0 turns grouping off: bars run in date order and the palette
        cycles per bar, as it did before grouping existed.

        ``group_colors`` is the chart-wide map from
        :py:meth:`_wbs_group_colors`, so a bar takes the same colour as the
        milestones and events in its phase.

        Returns ``(ordered_events, {id(event): color})``.
        """
        # A caller that lays bars out on their own — a test, or any future
        # path that skips _render_content — still gets grouped colors; the
        # map is only passed in so events and bars agree chart-wide.
        if not group_colors:
            group_colors = TimelineRenderer._wbs_group_colors(config, events)

        def date_key(event: Event) -> tuple:
            return (
                event.start,
                event.end,
                event.priority,
                event.task_name.lower() if event.task_name else "",
            )

        depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)

        if depth > 0:
            groups = {id(e): wbs_group(e.wbs, depth) for e in events}
            ordered = sorted(
                events,
                key=lambda e: (
                    0 if groups[id(e)] else 1,
                    wbs_sort_key(groups[id(e)]),
                    # A group's rollups lead it, so the lane they take is
                    # known before the parts they summarise are placed and
                    # floored beneath it (_rollup_lane_floor). A rollup
                    # whose own code is a prefix of its parts' already led
                    # them; this also covers one whose code is not.
                    0 if e.rollup else 1,
                    wbs_sort_key(e.wbs),
                    date_key(e),
                ),
            )
        else:
            groups = {id(e): "" for e in events}
            ordered = sorted(events, key=date_key)

        colors: dict[int, str] = {}
        if depth > 0:
            for event in ordered:
                colors[id(event)] = group_colors.get(groups[id(event)], "")
        else:
            _notes_style = config.get_text_style("ec-event-notes")
            palette = config.timeline_bottom_colors or [
                _notes_style.color or config.timeline_notes_text_font_color
            ]
            for index, event in enumerate(ordered):
                colors[id(event)] = palette[index % len(palette)]

        return ordered, colors

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
        group_colors: dict[str, str] | None = None,
    ) -> list[TimelineDuration]:
        """Lay out duration bars in lanes below a horizontal axis.

        Both edges of a bar are the x of its dates and nothing else, so
        every bar starting on a given day shares a left edge with the
        others and every bar ending on one shares a right edge — the
        alignment that lets a reader compare bars against the axis and
        against each other.  A bar too narrow for its own text is flagged
        ``text_overflow`` rather than widened; `_draw_duration` answers
        that by breaking the name over two rows and condensing the bar.

        Chronologically sorted bars pack greedily into the first lane
        whose previous bar ends at least ``min_gap`` px earlier.  Bars
        are clamped to the user-typed range with ``continues_left/right``
        flagged so the drawer can add continuation arrows; events wholly
        outside the range are dropped.  Returns placement records only —
        drawing happens in `_draw_duration`.
        """
        if not events:
            return []

        ordered, duration_colors = self._order_durations(
            config, events, group_colors
        )

        lane_last_end: list[float] = []
        # Lane each group's rollups reached, so the bars they summarise can
        # be kept further from the axis than their header is.
        rollup_floors: dict[str, int] = {}
        min_gap = max(10.0, self._page_width * 0.01)
        _layout_notes_style = config.get_text_style("ec-event-notes")
        title_size, notes_size, date_size, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(_layout_notes_style.font or config.timeline_notes_text_font_name)
        notes_font_path = self._safe_font_path(_layout_notes_style.font or config.timeline_notes_text_font_name)
        date_font_path = self._safe_font_path(
            config.get_text_style("ec-duration-date").font
            or config.timeline_duration_date_font
            or self._tk("text:duration_date").get("font")
            or config.timeline_date_font
        )

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

            # What the bar's three-column grid wants; nothing is widened to
            # reach it, so it only decides which bars carry the overflow mark.
            min_width = self._duration_full_extent(config, event, start)

            group = self._rollup_group(config, event)
            lane = self._place_span_in_lane(
                lane_last_end, sx, ex, min_gap,
                self._rollup_lane_floor(rollup_floors, group, event),
            )
            if group is not None and event.rollup:
                rollup_floors[group] = max(rollup_floors.get(group, -1), lane)
            color = duration_colors[id(event)]
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
                    text_overflow=(ex - sx) < min_width,
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
        group_colors: dict[str, str] | None = None,
    ) -> list[TimelineDuration]:
        """Place vertical-orientation duration bars alongside the axis.

        Bars run along the axis from start_y to end_y — exactly the y of
        their two dates, so bars sharing a date share an edge, as in the
        horizontal layout.  The per-bar `min_width` field carries the
        *along-axis* length the label would need; a bar shorter than that
        is flagged ``text_overflow`` rather than stretched, and
        `_draw_duration_vertical` answers by breaking the name over two
        rows and condensing the bar.

        Lanes stack perpendicularly away from the axis (each new
        overlapping bar sits further out).

        ``side`` selects which side(s) of the axis bars go on:
        - PRIMARY  → right side
        - SECONDARY → left side
        - BOTH     → alternate by start date, each side gets independent
          lane tracking
        """
        if not events:
            return []

        ordered, duration_colors = self._order_durations(
            config, events, group_colors
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
                    group_colors=group_colors,
                )
                + self._layout_durations_vertical(
                    config, secondary_events, start, end,
                    axis_x=axis_x, axis_top=axis_top, axis_bottom=axis_bottom,
                    side=Side.SECONDARY, style_engine=style_engine,
                    group_colors=group_colors,
                )
            )

        lane_last_end: list[float] = []
        rollup_floors: dict[str, int] = {}
        min_gap = max(10.0, self._page_height * 0.01)
        _layout_notes_style = config.get_text_style("ec-event-notes")
        title_size, notes_size, date_size, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(
            _layout_notes_style.font or config.timeline_notes_text_font_name
        )
        notes_font_path = self._safe_font_path(
            _layout_notes_style.font or config.timeline_notes_text_font_name
        )
        date_font_path = self._safe_font_path(
            config.get_text_style("ec-duration-date").font
            or config.timeline_duration_date_font
            or self._tk("text:duration_date").get("font")
            or config.timeline_date_font
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

            # Same grid as a horizontal bar, so the same demand — measured
            # along this axis, where the bar's length is its text's width.
            min_length = self._duration_full_extent(config, event, start_day)
            group = self._rollup_group(config, event)
            lane = self._place_span_in_lane(
                lane_last_end, sy, ey, min_gap,
                self._rollup_lane_floor(rollup_floors, group, event),
            )
            if group is not None and event.rollup:
                rollup_floors[group] = max(rollup_floors.get(group, -1), lane)
            color = duration_colors[id(event)]
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
                    text_overflow=(ey - sy) < min_length,
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
        min_lane: int = 0,
    ) -> int:
        """First lane at or beyond ``min_lane`` with room for this span.

        ``min_lane`` is how a group's parts are kept outside the lanes its
        rollup claimed — see :py:meth:`_rollup_lane_floor`.  Lanes skipped
        because of it stay open for bars from other groups, so the floor
        costs depth only where it actually applies.
        """
        for lane in range(min_lane, len(lane_last_end)):
            if start_x >= (lane_last_end[lane] + min_gap):
                lane_last_end[lane] = end_x
                return lane

        # A floor past the end of the stack opens the lanes it skipped as
        # empty, not as used: another group's bar may still take them.
        while len(lane_last_end) < min_lane:
            lane_last_end.append(float("-inf"))
        lane_last_end.append(end_x)
        return len(lane_last_end) - 1

    @staticmethod
    def _rollup_group(config: "CalendarConfig", event: Event) -> str | None:
        """The WBS group whose rollup outranks this bar, or ``None``.

        ``None`` when WBS grouping is off (``timeline_wbs_group_depth`` 0):
        bars then run in date order with no hierarchy to express, so there
        is no "same root WBS" for a rollup to lead.
        """
        depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)
        if depth <= 0:
            return None
        return wbs_group(event.wbs, depth)

    @staticmethod
    def _rollup_lane_floor(
        floors: dict[str, int], group: str | None, event: Event
    ) -> int:
        """Lowest lane a bar may take, given its group's rollup.

        A rollup summarises the bars under it, so it has to read as their
        header: it sits nearer the axis than every other bar sharing its
        root WBS.  Greedy first-fit alone will not do that — a child that
        starts after the rollup's neighbours have ended happily reuses a
        lane the rollup could not reach — so the group's parts are floored
        one lane past whatever its rollups claimed.

        Rollups themselves are unfloored, and are ordered ahead of their
        group in :py:meth:`_order_durations`, so the floor is always known
        by the time the parts are placed.
        """
        if group is None or event.rollup:
            return 0
        return floors.get(group, -1) + 1

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


    @classmethod
    def _cell_baseline(
        cls,
        cell_top: float,
        cell_h: float,
        font_path: str | None,
        size: float,
    ) -> float:
        """Baseline that centres one line's ink in a cell.

        The 2x2 grid gives each line a band of its own, so a line is
        centred in its band rather than the four of them being centred
        together as one block.
        """
        ascent, descent = cls._ink_extents_pt(font_path, size)
        return cell_top + ((cell_h - (ascent + descent)) / 2.0) + ascent

    @classmethod
    def _cell_font_size(
        cls, cell_h: float, font_path: str | None, size: float
    ) -> float:
        """``size``, capped so its ink fits the cell's height.

        Width is not consulted: a callout box is never stretched to its
        text, and over-wide text is compressed horizontally at draw time
        (``_draw_text(max_width=...)``) rather than shrunk, which keeps
        every box's four lines at a consistent size.
        """
        ascent, descent = cls._ink_extents_pt(font_path, 1.0)
        per_point = max(1e-6, ascent + descent)
        return max(4.0, min(size, cell_h / per_point))

    def _draw_callout(
        self,
        config: "CalendarConfig",
        item: TimelineCallout,
        axis_y: float,
    ) -> None:
        """Draw one placed callout: the axis dot, the label box, and the
        box's contents.

        A callout whose box found no room (packed placement, page full)
        draws its dot and the theme's missing-box icon at the end of its
        leader, and nothing else — the same treatment a duration bar past
        its limit gets in :py:meth:`_draw_duration_connectors`.

        The leader path itself was drawn in ``_render_content``'s underlay
        pass, so it runs beneath every box rather than over the ones it
        crosses.  ``axis_y`` is retained for backwards compatibility;
        ``item.x_dot`` / ``item.y_dot`` already account for orientation.
        """
        # Always draw a plain circle on the axis — icons go in the label box.
        self._draw_timeline_marker(
            config,
            x=item.x_dot,
            y=item.y_dot,
            color=item.color,
            icon_name=None,
        )

        if not item.placed:
            self._draw_missing_box_marker(
                config,
                item.box_x,
                item.box_y,
                max(8.0, float(config.timeline_icon_size)),
                item.color,
            )
            return

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
        self._draw_callout_contents(config, item, _sr)

    def _draw_callout_contents(
        self,
        config: "CalendarConfig",
        item: TimelineCallout,
        _sr: StyleResult,
    ) -> None:
        """Fill a callout box's two columns of two rows.

        The box is divided once, into a narrow leading column carrying the
        icon over the start date and a wide one carrying the name over the
        notes.  ``timeline_events.icon_column_ratio`` sets the split (15%
        by default) and ``inner_pad`` keeps a border clear on all four
        sides, so nothing is drawn on or outside the box's own stroke.

        Every line is measured against its own cell and compressed to it.
        Nothing here resizes the box: the theme's width and height are the
        box, and the text yields.
        """
        pad = max(0.0, float(config.timeline_event_box_pad or 0.0))
        inner_x = item.box_x + pad
        inner_y = item.box_y + pad
        inner_w = max(1.0, item.box_width - 2.0 * pad)
        inner_h = max(1.0, item.box_height - 2.0 * pad)

        ratio = min(0.9, max(0.02, float(config.timeline_event_icon_column_ratio)))
        col1_w = inner_w * ratio
        col2_w = inner_w - col1_w
        row_h = inner_h / 2.0
        col2_x = inner_x + col1_w
        row2_y = inner_y + row_h

        title_size, notes_size, date_size = self._callout_metrics(config)

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
        notes_font, _, notes_color, notes_opacity = _sr.text_override(
            "event_notes",
            font=notes_font_default,
            color=(
                tk_notes.get("color")
                or config.timeline_notes_text_font_color
                or _notes_style.color
                or event_text_color
            ),
            opacity=_notes_style.opacity,
        )
        name_path = self._safe_font_path(name_font)
        notes_path = self._safe_font_path(notes_font)

        # Column 1, row 1: the icon, centred in its cell and sized to
        # whichever of the cell's two dimensions is tighter.
        icon_to_draw = _sr.icon if _sr.icon is not None else item.event.icon
        if icon_to_draw and self._resolve_icon_svg(icon_to_draw):
            icon_size = max(1.0, min(col1_w, row_h))
            self._draw_icon_svg(
                icon_to_draw,
                inner_x + (col1_w / 2.0),
                self._icon_baseline(inner_y + (row_h / 2.0), icon_size),
                icon_size,
                anchor="middle",
                color=_sr.icon_color or event_text_color,
                css_class="ec-event-icon",
                box_token=(
                    "box:milestone"
                    if getattr(item.event, "milestone", False)
                    else "box:event"
                ),
                box_ctx=self._event_ctx(item.event),
            )

        # Column 2, row 1: the name.
        fitted_name = self._cell_font_size(row_h, name_path, title_size)
        self._draw_text(
            col2_x,
            self._cell_baseline(inner_y, row_h, name_path, fitted_name),
            item.event.task_name or "(untitled)",
            name_font,
            fitted_name,
            fill=name_color,
            fill_opacity=name_opacity,
            max_width=col2_w,
            css_class="ec-event-name",
        )

        # Column 2, row 2: the notes.
        notes = (item.event.notes or "").strip()
        if notes:
            fitted_notes = self._cell_font_size(row_h, notes_path, notes_size)
            self._draw_text(
                col2_x,
                self._cell_baseline(row2_y, row_h, notes_path, fitted_notes),
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                max_width=col2_w,
                css_class="ec-event-notes",
            )

        # Column 1, row 2: the start date, under the icon.
        date_label = self._callout_date_label(config, item)
        if not date_label:
            return
        _event_date_style = config.get_text_style("ec-event-date")
        tk_event_date = self._tk("text:event_date")
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
        date_path = self._safe_font_path(date_font)
        fitted_date = self._cell_font_size(row_h, date_path, date_size)
        self._draw_text(
            inner_x,
            self._cell_baseline(row2_y, row_h, date_path, fitted_date),
            date_label,
            date_font,
            fitted_date,
            fill=date_color,
            anchor="start",
            max_width=col1_w,
            css_class="ec-event-date",
        )

    def _duration_bar_y(
        self, config: "CalendarConfig", item: TimelineDuration, axis_y: float
    ) -> tuple[float, float]:
        """``(bar_y, bar_h)`` for one horizontal duration bar.

        The connector and the bar itself both need this and used to compute
        it separately; sharing it is what lets the connector know whether the
        bar it points at was actually drawn.
        """
        _title, _notes, date_size, bar_h = self._duration_metrics(config)
        duration_offset = max(
            config.timeline_duration_offset_y,
            self._min_duration_offset(config, date_size),
        )
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        # The start/end dates ride inside the bar, so a row is the bar plus
        # the gap to the next one — no label band underneath.
        lane_stride = bar_h + lane_gap
        return axis_y + duration_offset + (item.lane * lane_stride), bar_h

    def _duration_row_extent(self, config: "CalendarConfig") -> float:
        """Vertical room one duration row needs, its date labels included.

        The dates sit inside the bar, so the row is just the rect.  Kept as
        its own method because `_actual_content_bounds` reserves the same
        figure and the two must not drift.
        """
        _title, _notes, _date_size, bar_h = self._duration_metrics(config)
        return bar_h

    def _duration_bar_x(
        self, config: "CalendarConfig", item: TimelineDuration, axis_x: float
    ) -> tuple[float, float, float]:
        """``(near_edge_x, thickness, sign)`` for one vertical duration bar.

        ``sign`` is +1 on the primary side (right of the axis), -1 on the
        secondary.
        """
        _title, _notes, date_size, bar_thickness = self._duration_metrics(config)
        duration_offset = max(
            config.timeline_duration_offset_y,
            self._min_duration_offset(config, date_size),
        )
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_thickness + lane_gap
        sign = 1.0 if item.lane_side is Side.PRIMARY else -1.0
        near_x = axis_x + sign * (duration_offset + (item.lane * lane_stride))
        return near_x, bar_thickness, sign

    @staticmethod
    def _duration_fits(bar_far_edge: float, limit: float | None) -> bool:
        """True when a bar's far edge is inside the drawable area.

        ``limit`` is None whenever nothing constrains the band — no page
        bound was supplied, or --shrink is growing the page to fit the
        content, in which case every bar is drawn however deep the stack
        goes.
        """
        return limit is None or bar_far_edge <= limit

    def _draw_missing_box_marker(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        size: float,
        color: str,
    ) -> None:
        """Mark a leader whose box ran out of room with the missing icon.

        Without it the leader still gets drawn and simply runs off the page,
        which reads as a line pointing at a bar that is not there.  The glyph
        is the theme's ``base.default_missing_icon``; a theme that leaves it
        unset gets a leader that stops at the edge and nothing else, which is
        still better than one that leaves the paper.
        """
        icon = getattr(config, "default_missing_icon", None)
        if not icon:
            return
        configured = getattr(config, "default_missing_icon_size", None)
        if configured and configured > 0:
            size = float(configured)
        self._draw_icon_svg(
            str(icon),
            x,
            self._icon_baseline(y, size),
            size,
            anchor="middle",
            color=color,
            css_class="ec-overflow-icon",
        )

    def _draw_duration_connectors(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_y: float,
        limit: float | None = None,
    ) -> None:
        """Draw the vertical aligner line from the axis to the duration bar.

        Start edge only, as in :py:meth:`_draw_duration_connectors_vertical`.
        Both edges stand on real dates now (see ``_layout_durations``), but
        one leader is enough to tie a lane deep below the axis back up to it,
        and a second would cross every bar stacked between the two edges.

        When the bar itself did not fit below ``limit`` the leader stops at
        the edge of the drawable area and ends in the theme's missing-box
        icon, instead of running off the page toward a bar nobody drew.
        """
        bar_y, bar_h = self._duration_bar_y(config, item, axis_y)
        row_extent = self._duration_row_extent(config)
        fits = self._duration_fits(bar_y + row_extent, limit)
        end_y = bar_y if fits else float(limit) - row_extent
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        self._draw_line(
            item.start_x,
            axis_y,
            item.start_x,
            end_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )
        if not fits:
            self._draw_missing_box_marker(
                config, item.start_x, end_y + bar_h / 2.0, bar_h, item.color
            )

    def _draw_duration(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_y: float,
        limit: float | None = None,
    ) -> None:
        """Draw one placed duration below a horizontal axis: the bar
        rect (fill opacity token-first from ``line:duration_bar``),
        start/end axis markers, continuation arrows when the event
        extends past the visible range, and the name / notes / date
        text block sized to the bar's lane.

        A bar whose lane falls past ``limit`` is not drawn at all — its
        leader carries the missing-box icon instead (see
        :py:meth:`_draw_duration_connectors`), which says more than a bar
        printed off the edge of the paper.
        """
        _probe_y, _probe_h = self._duration_bar_y(config, item, axis_y)
        if not self._duration_fits(
            _probe_y + self._duration_row_extent(config), limit
        ):
            return

        title = item.event.task_name or "(untitled duration)"
        notes = (item.event.notes or "").strip()
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)

        title_size, notes_size, date_size, bar_h = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(config, date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_h + lane_gap

        bar_bottom = axis_y + duration_offset
        bar_y = bar_bottom + (item.lane * lane_stride)

        # Duration bar.
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        # Bar-rect fill opacity is token-first: themes set it per-visualizer
        # via a line:duration_bar rule with select: {visualizer: timeline}.
        _tk_bar_opacity = self._tk("line:duration_bar").get("opacity")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=(
                _tk_bar_opacity if _tk_bar_opacity is not None
                else _dur_bar_style.opacity
            ),
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

        # Start marker on the main axis.  The end date gets none: the bar's
        # own right edge already stands on it, and a dot out on the axis
        # with no leader running down to the bar belongs to no bar in
        # particular once several lanes share the day.
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

        self._draw_duration_contents(
            config,
            item,
            item.start_x,
            bar_y,
            max(1.0, item.end_x - item.start_x),
            bar_h,
            _sr,
        )


    def _duration_full_extent(
        self,
        config: "CalendarConfig",
        event: Event,
        fallback: arrow.Arrow,
    ) -> float:
        """Along-axis extent at which a bar's grid needs no compressing.

        Each side column has to hold its date and the middle one the wider
        of the name and the notes, so the bar wants whichever of those
        demands is larger once divided by its column's share.  A theme that
        sets ``timeline_durations.box_width`` names this outright.  Bars are
        never grown to it — their edges are their dates — so it only decides
        which of them break their name over two rows and condense.
        """
        configured = (
            float(config.timeline_duration_box_width)
            if config.timeline_duration_box_width is not None
            else 0.0
        )
        if configured > 0:
            return configured

        title_size, notes_size, date_size, _bar_h = self._duration_metrics(config)
        fonts = self._duration_text_fonts(config, StyleResult())
        name_w = string_width(
            event.task_name or "", self._safe_font_path(fonts["name_font"]), title_size
        )
        notes_w = (
            string_width(
                (event.notes or "").strip(),
                self._safe_font_path(fonts["notes_font"]),
                notes_size,
            )
            if config.include_notes
            else 0.0
        )
        start_w = string_width(
            format_arrow_date(
                self._safe_day(event.start, fallback=fallback),
                config.timeline_date_format,
            ),
            self._safe_font_path(fonts["start_font"]),
            date_size,
        )
        end_w = string_width(
            format_arrow_date(
                self._safe_day(event.end, fallback=fallback),
                config.timeline_date_format,
            ),
            self._safe_font_path(fonts["end_font"]),
            date_size,
        )
        ratio = min(0.45, max(0.02, self._duration_column_ratio(config)))
        # The middle column loses a gap on each side; solving
        # inner*(1-2r) - 2*gap >= text for inner puts the gaps back here.
        inner = max(
            max(start_w, end_w) / ratio,
            (max(name_w, notes_w) + 2.0 * _DURATION_DATE_GAP_X)
            / max(0.05, 1.0 - 2.0 * ratio),
        )
        return inner + 2.0 * _DURATION_DATE_PAD_X

    def _duration_cell_layout(
        self, config: "CalendarConfig", inner_w: float
    ) -> list[tuple[float, float]]:
        """The three columns of a duration bar, as (offset, width) pairs.

        The two side columns are the same width — the callout box's icon
        column, mirrored — so the start date at one end and the end date at
        the other are laid out identically and the name in the middle sits
        where the eye expects it whatever the dates say.  A gap either side
        of the middle column keeps a compressed name off the dates it runs
        between; without it the three read as one run of text.
        """
        ratio = min(0.45, max(0.02, self._duration_column_ratio(config)))
        side = inner_w * ratio
        gap = _DURATION_DATE_GAP_X if inner_w > 4.0 * _DURATION_DATE_GAP_X else 0.0
        mid = max(1.0, inner_w - 2.0 * side - 2.0 * gap)
        return [(0.0, side), (side + gap, mid), (inner_w - side, side)]

    @staticmethod
    def _duration_column_ratio(config: "CalendarConfig") -> float:
        """Share of a duration bar given to each of its two side columns.

        ``timeline_durations.icon_column_ratio`` when a theme sets one,
        otherwise whatever the callout boxes use, so the two kinds of box
        line up without a theme having to say so twice.
        """
        configured = getattr(config, "timeline_duration_icon_column_ratio", None)
        if configured:
            return float(configured)
        return float(config.timeline_event_icon_column_ratio)

    def _duration_text_fonts(
        self, config: "CalendarConfig", _sr: StyleResult
    ) -> dict:
        """Fonts, colors and opacities for everything inside a duration bar.

        One resolution shared by the horizontal and vertical layouts, which
        drew from the same tokens through two copies of this until the
        layouts themselves were made one.
        """
        _name_style = config.get_text_style("ec-event-name")
        _notes_style = config.get_text_style("ec-event-notes")
        _date_style = config.get_text_style("ec-duration-date")
        tk_name = self._tk("text:event_name")
        tk_notes = self._tk("text:event_notes")
        tk_date = self._tk("text:duration_date")

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
        text_color = (
            tk_name.get("color")
            or config.timeline_name_text_font_color
            or _name_style.color
        )
        name_font, _, name_color, name_opacity = _sr.text_override(
            "duration_name",
            font=name_font_default,
            color=text_color,
            opacity=_name_style.opacity,
        )
        notes_font, _, notes_color, notes_opacity = _sr.text_override(
            "duration_notes",
            font=notes_font_default,
            color=(
                tk_notes.get("color")
                or config.timeline_notes_text_font_color
                or _notes_style.color
                or text_color
            ),
            opacity=_notes_style.opacity,
        )
        date_font_base = (
            _date_style.font
            or config.timeline_duration_date_font
            or tk_date.get("font")
            or config.timeline_date_font
        )
        date_color_base = (
            _date_style.color
            or config.timeline_duration_date_color
            or tk_date.get("color")
            or text_color
        )
        start_font, _, start_color, _ = _sr.text_override(
            "duration_start_date", font=date_font_base, color=date_color_base
        )
        end_font, _, end_color, _ = _sr.text_override(
            "duration_end_date", font=date_font_base, color=date_color_base
        )
        return {
            "name_font": name_font,
            "name_color": name_color,
            "name_opacity": name_opacity,
            "notes_font": notes_font,
            "notes_color": notes_color,
            "notes_opacity": notes_opacity,
            "start_font": start_font,
            "start_color": start_color,
            "end_font": end_font,
            "end_color": end_color,
            "text_color": text_color,
        }

    @staticmethod
    def _split_name_two_lines(
        name: str, font_path: str | None, size: float
    ) -> tuple[str, str]:
        """Break a name at the word boundary that balances the two lines.

        "Balanced" means the narrower of the two widest lines, since that
        is what the bar has to condense to fit — splitting at the middle
        *word* leaves one line long whenever the words are uneven.  A name
        with no boundary to break at comes back as one line; half a word on
        each row reads as neither.
        """
        words = name.split()
        if len(words) < 2:
            return name, ""
        best_widest, best_at = None, 1
        for at in range(1, len(words)):
            widest = max(
                string_width(" ".join(words[:at]), font_path, size),
                string_width(" ".join(words[at:]), font_path, size),
            )
            if best_widest is None or widest < best_widest:
                best_widest, best_at = widest, at
        return " ".join(words[:best_at]), " ".join(words[best_at:])

    def _duration_cells(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        fonts: dict,
        title_size: float,
    ) -> list[tuple[int, int, str, str]]:
        """What goes in each cell of a duration bar, as (col, row, kind, text).

        Three columns of two rows, the callout box's grid with one column
        more: the event's icon over its start date, the name over the
        notes, and the end date under a cell left empty.  ``kind`` is
        "icon", "name", "notes" or "date"; the caller places them.

        A bar too narrow for all of that at full size (``text_overflow``)
        spends the middle column's second row on the *rest of the name*
        rather than the notes: two condensed lines saying what the activity
        is beat one line of it above a description neither has room for.
        """
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)
        show_icon = bool(config.timeline_duration_icon_visible) and bool(
            item.event.icon
        )
        cells: list[tuple[int, int, str, str]] = []
        if show_icon:
            cells.append((0, 0, "icon", str(item.event.icon)))
        cells.append(
            (0, 1, "date", format_arrow_date(start_day, config.timeline_date_format))
        )
        name = item.event.task_name or "(untitled duration)"
        if item.text_overflow:
            first, second = self._split_name_two_lines(
                name, self._safe_font_path(fonts["name_font"]), title_size
            )
            cells.append((1, 0, "name", first))
            if second:
                cells.append((1, 1, "name", second))
        else:
            cells.append((1, 0, "name", name))
            notes = (item.event.notes or "").strip()
            if notes and config.include_notes:
                cells.append((1, 1, "notes", notes))
        cells.append(
            (2, 1, "date", format_arrow_date(end_day, config.timeline_date_format))
        )
        return cells

    @staticmethod
    def _duration_cell_style(
        kind: str, fonts: dict, col: int
    ) -> tuple[str, str, float, str]:
        """Font, color, opacity and CSS class for one duration text cell.

        Both lines of a broken name are drawn in the name's own style even
        though the second sits in the notes' row — they are one piece of
        text, and switching font halfway down reads as two.
        """
        return {
            "name": (fonts["name_font"], fonts["name_color"],
                     fonts["name_opacity"], "ec-event-name"),
            "notes": (fonts["notes_font"], fonts["notes_color"],
                      fonts["notes_opacity"], "ec-event-notes"),
        }.get(
            kind,
            (
                fonts["start_font"] if col == 0 else fonts["end_font"],
                fonts["start_color"] if col == 0 else fonts["end_color"],
                1.0,
                "ec-duration-date",
            ),
        )

    def _duration_squeeze(
        self,
        cells: list[tuple[int, int, str, str]],
        col_w: tuple[float, ...],
        row_h: float,
        fonts: dict,
        size_for: dict,
    ) -> float:
        """The one horizontal condense factor every cell of a bar shares.

        A bar is never widened to its text, so text wider than its cell is
        condensed into it.  Doing that per cell squashed each line by its
        own slack, and a name at 40% beside a date at 95% read as two
        unrelated bits of type sharing a rectangle.  The tightest cell sets
        the factor and everything in the bar — the other lines, the dates,
        the icon — is drawn at it.  ``1.0`` when nothing overflows.
        """
        squeeze = 1.0
        for col, _row, kind, text in cells:
            cell_w = col_w[col]
            # Icons are drawn at min(cell_w, row_h) and so never overflow;
            # they take the factor without having a say in it.
            if cell_w <= 0.5 or not text or kind == "icon":
                continue
            font, _color, _opacity, _css = self._duration_cell_style(kind, fonts, col)
            font_path = self._safe_font_path(font)
            fitted = self._cell_font_size(row_h, font_path, size_for[kind])
            measured = string_width(text, font_path, fitted)
            if measured > 0:
                squeeze = min(squeeze, cell_w / measured)
        return min(1.0, squeeze)

    @staticmethod
    def _squeeze_transform(
        squeeze: float, cx: float, cy: float, axis: str = "x"
    ) -> str | None:
        """Condense about ``(cx, cy)`` along ``axis``; None at full width.

        ``axis`` is the direction the bar's text runs in: "x" beside a
        horizontal axis, "y" beside a vertical one, where the rows are
        turned on their side with the bar.
        """
        if squeeze >= 1.0:
            return None
        sx, sy = (squeeze, 1.0) if axis == "x" else (1.0, squeeze)
        return (
            f"translate({cx:.4f} {cy:.4f}) scale({sx:.6f} {sy:.6f}) "
            f"translate({-cx:.4f} {-cy:.4f})"
        )

    def _draw_duration_contents(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        bar_x: float,
        bar_y: float,
        bar_w: float,
        bar_h: float,
        _sr: StyleResult,
    ) -> None:
        """Fill a horizontal duration bar's three columns of two rows.

        The same grid a callout box uses, with a third column: icon over
        start date, name over notes, end date at the far end.  Nothing here
        resizes the bar — its edges are its dates — so a bar too narrow for
        all of that breaks its name over both rows of the middle column
        (:py:meth:`_duration_cells`) and everything in the bar is condensed
        by the one factor the tightest cell needs
        (:py:meth:`_duration_squeeze`).
        """
        pad = _DURATION_DATE_PAD_X
        inner_x = bar_x + pad
        inner_y = bar_y
        inner_w = max(1.0, bar_w - 2.0 * pad)
        inner_h = max(1.0, bar_h)
        columns = self._duration_cell_layout(config, inner_w)
        col_x = tuple(inner_x + off for off, _w in columns)
        col_w = tuple(w for _off, w in columns)
        side_w = col_w[0]
        row_h = inner_h / 2.0

        if side_w < _DURATION_ICON_MIN_SIZE:
            # Too narrow for columns at all: every cell would be narrower
            # than the ink it carries, and a name condensed into one that
            # small is a smear that names nothing.  The bar rect alone.
            return

        title_size, notes_size, date_size, _bar_h = self._duration_metrics(config)
        size_for = {"name": title_size, "notes": notes_size, "date": date_size}
        fonts = self._duration_text_fonts(config, _sr)
        cells = self._duration_cells(config, item, fonts, title_size)
        squeeze = self._duration_squeeze(cells, col_w, row_h, fonts, size_for)

        for col, row, kind, text in cells:
            cell_x, cell_w = col_x[col], col_w[col]
            cell_y = inner_y + row * row_h
            if cell_w <= 0.5 or not text:
                continue
            if kind == "icon":
                cx, cy = cell_x + cell_w / 2.0, cell_y + row_h / 2.0
                self._draw_duration_cell_icon(
                    config, item, text, _sr,
                    cx, cy, min(cell_w, row_h), fonts["text_color"],
                    transform=self._squeeze_transform(squeeze, cx, cy),
                )
                continue
            self._draw_duration_cell_text(
                kind, text, fonts, size_for[kind],
                cell_x, cell_y, cell_w, row_h, col,
                align=("start", "middle", "end")[col],
                squeeze=squeeze,
            )

    def _draw_duration_cell_icon(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        icon_name: str,
        _sr: StyleResult,
        cx: float,
        cy: float,
        size: float,
        text_color: str,
        transform: str | None = None,
    ) -> None:
        """Draw a duration bar's event icon, centred in its cell.

        ``transform`` carries the bar's shared condense factor, so the glyph
        narrows with the text beside it instead of standing at full width in
        a row of squeezed type.
        """
        if size < _DURATION_ICON_MIN_SIZE:
            return
        icon_name = _sr.icon if _sr.icon is not None else icon_name
        color = _sr.icon_color or text_color
        self._draw_icon_svg(
            icon_name,
            cx,
            self._icon_baseline(cy, size),
            size,
            anchor="middle",
            color=color,
            fallback_name=config.default_missing_icon,
            fallback_size=config.default_missing_icon_size,
            fallback_color=color,
            transform=transform,
            css_class="ec-duration-icon",
            box_token="box:duration",
            box_ctx=self._event_ctx(item.event),
        )

    def _draw_duration_cell_text(
        self,
        kind: str,
        text: str,
        fonts: dict,
        size: float,
        cell_x: float,
        cell_y: float,
        cell_w: float,
        cell_h: float,
        col: int,
        align: str,
        transform: str | None = None,
        squeeze: float = 1.0,
    ) -> None:
        """Draw one of a duration bar's text cells, condensed to fit it.

        The side columns hang their dates off the bar's own ends — start
        date flush against the start, end date against the end — and the
        middle column centres the name and notes, so a row of bars reads as
        a column of dates with the names between them.  ``align`` says which
        edge of the cell to hang this one from; the two layouts disagree
        about which that is, because a rotated line runs the other way.

        ``squeeze`` is the bar's shared condense factor
        (:py:meth:`_duration_squeeze`): a line is drawn at that fraction of
        its natural width rather than merely capped at its own cell, so
        every line in the bar narrows by the same amount.
        """
        font, color, opacity, css_class = self._duration_cell_style(kind, fonts, col)
        font_path = self._safe_font_path(font)
        fitted = self._cell_font_size(cell_h, font_path, size)
        max_width = cell_w
        if squeeze < 1.0:
            measured = string_width(text, font_path, fitted)
            if measured > 0:
                max_width = measured * squeeze
        x = {
            "start": cell_x,
            "end": cell_x + cell_w,
        }.get(align, cell_x + cell_w / 2.0)
        anchor = align if align in ("start", "end") else "middle"
        self._draw_text(
            x,
            self._cell_baseline(cell_y, cell_h, font_path, fitted),
            text,
            font,
            fitted,
            fill=color,
            fill_opacity=opacity,
            anchor=anchor,
            max_width=max_width,
            transform=transform,
            css_class=css_class,
        )

    def _draw_duration_contents_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        bar_x: float,
        bar_y: float,
        bar_thickness: float,
        bar_h: float,
        _sr: StyleResult,
    ) -> None:
        """:py:meth:`_draw_duration_contents` turned on its side.

        The same three columns of two rows: the columns run along the axis
        (start date at the top, end date at the bottom, name between) and
        the rows across the bar's thickness.  Text is rotated to read
        bottom→top with the bar; the icons stay upright, since an indicator
        on its side reads as a different glyph.  A bar too short for its
        text breaks the name across both rows and condenses everything by
        the one shared factor, exactly as the horizontal layout does.
        """
        pad = _DURATION_DATE_PAD_X
        inner_len = max(1.0, bar_h - 2.0 * pad)
        columns = self._duration_cell_layout(config, inner_len)
        # Along the axis, measured from the bar's top edge.
        col_start = tuple(pad + off for off, _w in columns)
        col_len = tuple(w for _off, w in columns)
        side_w = col_len[0]
        row_h = max(1.0, bar_thickness) / 2.0

        if side_w < _DURATION_ICON_MIN_SIZE:
            return

        title_size, notes_size, date_size, _bar_h = self._duration_metrics(config)
        size_for = {"name": title_size, "notes": notes_size, "date": date_size}
        fonts = self._duration_text_fonts(config, _sr)
        cells = self._duration_cells(config, item, fonts, title_size)
        squeeze = self._duration_squeeze(cells, col_len, row_h, fonts, size_for)

        cx = bar_x + bar_thickness / 2.0
        cy = bar_y + bar_h / 2.0
        rot = f"rotate(-90 {cx:.4f} {cy:.4f})"

        for col, row, kind, text in cells:
            length, along0 = col_len[col], bar_y + col_start[col]
            if length <= 0.5 or not text:
                continue
            # rotate(-90) maps a pre-rotation +dx onto -dx in y, so a cell
            # that starts `along0` down the bar is laid out that far to the
            # right of the rotation centre, and its row offsets the other way.
            row_center = bar_x + (row + 0.5) * row_h
            if kind == "icon":
                icon_cy = along0 + length / 2.0
                self._draw_duration_cell_icon(
                    config, item, text, _sr,
                    row_center,
                    icon_cy,
                    min(length, row_h),
                    fonts["text_color"],
                    # The rows run down the page here, so the bar condenses
                    # along y — the icon has to follow the text's axis, not
                    # the screen's.
                    transform=self._squeeze_transform(
                        squeeze, row_center, icon_cy, axis="y"
                    ),
                )
                continue
            # Pre-rotation x runs along the axis but backwards: rotate(-90)
            # sends +x upward, so a cell's low-x edge is its *bottom*.  The
            # start date therefore hangs from the high-x edge ("end") to sit
            # flush against the bar's top, and the end date from the low one.
            cell_pre_x = cx + (cy - (along0 + length))
            cell_pre_y = cy - (cx - (row_center - row_h / 2.0))
            self._draw_duration_cell_text(
                kind, text, fonts, size_for[kind],
                cell_pre_x, cell_pre_y, length, row_h, col,
                align=("end", "middle", "start")[col],
                transform=rot,
                squeeze=squeeze,
            )

    def _draw_duration_connectors_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_x: float,
        limit: float | None = None,
    ) -> None:
        """Horizontal aligner line from the vertical axis to the duration bar.

        Start edge only.  Both edges stand on real dates now (see
        :py:meth:`_layout_durations_vertical`), but one leader is enough to
        tie a lane back to the axis, and a second would cross every bar
        stacked between them on the way.

        ``limit`` is how far from the axis this side may reach; a lane past it
        gets a leader that stops at the edge and ends in the missing-box icon
        rather than one that runs off the page.
        """
        bar_near_axis_x, bar_thickness, sign = self._duration_bar_x(
            config, item, axis_x
        )
        far_edge = bar_near_axis_x + sign * bar_thickness
        fits = self._duration_fits(abs(far_edge - axis_x), limit)
        end_x = (
            bar_near_axis_x
            if fits
            else axis_x + sign * (float(limit) - bar_thickness)
        )
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        self._draw_line(
            axis_x,
            item.start_y,
            end_x,
            item.start_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )
        if not fits:
            self._draw_missing_box_marker(
                config,
                end_x + sign * (bar_thickness / 2.0),
                item.start_y,
                bar_thickness,
                item.color,
            )

    def _draw_duration_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_x: float,
        limit: float | None = None,
    ) -> None:
        """Draw a vertical-orientation duration bar (left of axis).

        A lane past ``limit`` is skipped; its leader carries the missing-box
        icon instead.
        """
        _near_x, _thickness, _sign = self._duration_bar_x(config, item, axis_x)
        if not self._duration_fits(
            abs(_near_x + _sign * _thickness - axis_x), limit
        ):
            return

        title = item.event.task_name or "(untitled duration)"
        notes = (item.event.notes or "").strip()
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)

        title_size, notes_size, date_size, bar_thickness = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(config, date_size)
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
        # Bar-rect fill opacity is token-first: themes set it per-visualizer
        # via a line:duration_bar rule with select: {visualizer: timeline}.
        _tk_bar_opacity = self._tk("line:duration_bar").get("opacity")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=(
                _tk_bar_opacity if _tk_bar_opacity is not None
                else _dur_bar_style.opacity
            ),
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

        # Start marker on the main axis, at the bar's start y — the end
        # date has none, for the reason given in :py:meth:`_draw_duration`.
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

        self._draw_duration_contents_vertical(
            config, item, bar_x, bar_y, bar_thickness, bar_h, _sr
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

    def _min_duration_offset(self, config: "CalendarConfig", date_size: float) -> float:
        """Minimum axis-to-bar clearance so what sits under the axis stays legible.

        The clearance has to cover the timeline date labels and, when holiday
        marks are drawn, the icon-plus-date band that shares the same strip.
        """
        clearance = max(22.0, date_size * 3.2)
        if getattr(config, "timeline_show_holiday_icons", True):
            clearance = max(clearance, self._holiday_band_extent(config) + 2.0)
        return clearance

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

    def _tick_side_clearance(
        self, config: "CalendarConfig", start: arrow.Arrow, end: arrow.Arrow
    ) -> float:
        """Room the axis ticks and their dates need on their own side.

        The wider of what a theme's ``timeline.ticks`` bands claim and what
        the built-in month ticks do, so an axis pushed toward the edge of
        the page — which is what ``--noevents`` does — still leaves its
        dates somewhere to be printed.
        """
        return max(
            self._tick_label_top_clearance(
                config, getattr(config, "timeline_ticks", None)
            ),
            self._axis_label_clearance(config, start, end),
        )

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
            # (kept inline: this walks every band to find the deepest)
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

    def _band_tick_style(
        self,
        config: "CalendarConfig",
        band: dict,
        tick_count: int,
    ) -> dict:
        """Resolve one tick band's marks and labels against the theme.

        Per-band keys win, then the ``ec-axis-tick`` line style and the
        ``text:event_date`` token, then the config defaults — the same
        order whichever way the axis runs, which is the point of having
        this in one place.
        """
        _tick_style = config.get_line_style("ec-axis-tick")
        tk_event_date = self._tk("text:event_date")
        tick_h = float(band.get("tick_length") or self._axis_tick_height(config))
        label_size = float(
            band.get("label_font_size")
            or band.get("font_size")
            or max(7.0, config.weekly_name_text_font_size * 0.8)
        )
        return {
            "tick_h": tick_h,
            "tick_width": float(band.get("tick_width") or 1.0),
            "tick_opacity": float(
                band.get("tick_opacity")
                if band.get("tick_opacity") is not None
                else 0.35
            ),
            "tick_color": str(band.get("tick_color") or _tick_style.color),
            "tick_dash": band.get("tick_dasharray") or _tick_style.dasharray or None,
            "label_size": label_size,
            "draw_labels": bool(band.get("show_labels", True))
            and tick_count <= int(band.get("max_label_count", 60)),
            "label_color": str(
                band.get("label_color")
                or band.get("font_color")
                or tk_event_date.get("color")
                or _tick_style.color
            ),
            "label_opacity": float(
                band.get("label_opacity")
                if band.get("label_opacity") is not None
                else 0.8
            ),
            "font_name": str(
                band.get("font")
                or tk_event_date.get("font")
                or config.timeline_date_font
            ),
            "label_offset": self._tick_label_offset(
                tick_h,
                label_size,
                band.get("label_gap"),
                band.get("label_offset_y"),
            ),
        }

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

        style = self._band_tick_style(config, band, len(ticks))
        tick_h = style["tick_h"]
        tick_width = style["tick_width"]
        tick_opacity = style["tick_opacity"]
        tick_color = style["tick_color"]
        tick_dash = style["tick_dash"]
        label_size = style["label_size"]
        draw_labels = style["draw_labels"]
        label_color = style["label_color"]
        label_opacity = style["label_opacity"]
        font_name = style["font_name"]
        label_offset_y = style["label_offset"]

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

    def _draw_axis_ticks_from_band_vertical(
        self,
        config: "CalendarConfig",
        band: dict,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
        axis_x: float,
        db: "CalendarDB",
        ticks: list[tuple[date, str]] | None = None,
        allowed_label_dates: set[date] | None = None,
        label_side: Side = Side.SECONDARY,
    ) -> None:
        """:py:meth:`_draw_axis_ticks_from_band` turned on its side.

        Same bands, same theme resolution (see
        :py:meth:`_band_tick_style`); the tick crosses the axis at the
        day's y and its date is written beside it, on ``label_side`` —
        SECONDARY (left) or PRIMARY (right), chosen by
        :py:meth:`_tick_label_side` so the dates land clear of the bars.
        The labels stay upright: a date is read, not followed.
        """
        if ticks is None:
            ticks = self._compute_band_ticks(config, band, start, end, db)
        if not ticks:
            return

        style = self._band_tick_style(config, band, len(ticks))
        tick_h = style["tick_h"]
        label_size = style["label_size"]

        for tick_date, tick_label in ticks:
            tick_arrow = arrow.Arrow(tick_date.year, tick_date.month, tick_date.day)
            y = self._y_for_day(tick_arrow, start, end, axis_top, axis_bottom)
            self._draw_line(
                axis_x - tick_h,
                y,
                axis_x + tick_h,
                y,
                stroke=style["tick_color"],
                stroke_width=style["tick_width"],
                stroke_opacity=style["tick_opacity"],
                stroke_dasharray=style["tick_dash"],
                css_class="ec-axis-tick",
            )
            if (
                style["draw_labels"]
                and tick_label
                and (allowed_label_dates is None or tick_date in allowed_label_dates)
            ):
                label_x, anchor = self._tick_label_x(
                    axis_x, style["label_offset"], label_side
                )
                self._draw_text(
                    label_x,
                    self._tick_label_baseline(y, label_size, axis_top, axis_bottom),
                    tick_label,
                    style["font_name"],
                    label_size,
                    fill=style["label_color"],
                    fill_opacity=style["label_opacity"],
                    anchor=anchor,
                    css_class="ec-label",
                )
                self._note_label_ink(
                    label_x, tick_label, style["font_name"], label_size, label_side
                )

    @staticmethod
    def _tick_label_x(
        axis_x: float, label_offset: float, label_side: Side
    ) -> tuple[float, str]:
        """Where a vertical tick's date starts, and which end it hangs from.

        Either way the text grows away from the axis, so the offset is all
        that separates them.
        """
        if label_side is Side.PRIMARY:
            return axis_x + label_offset, "start"
        return axis_x - label_offset, "end"

    def _note_side_ink(self, *xs: float) -> None:
        """Remember how far past a vertical axis something was drawn.

        ``--shrink`` tightens the viewBox from the coordinates the layout
        knows about, and everything beside a vertical axis — the tick
        dates, the holiday marks, the fiscal and timeband columns — is
        written during the draw pass, outside every box the layout placed.
        Without this they are what the tightened box cuts off.
        """
        for x in xs:
            if self._side_ink_min_x is None or x < self._side_ink_min_x:
                self._side_ink_min_x = x
            if self._side_ink_max_x is None or x > self._side_ink_max_x:
                self._side_ink_max_x = x

    def _note_label_ink(
        self,
        label_x: float,
        label: str,
        font_name: str,
        label_size: float,
        side: Side,
    ) -> None:
        """:py:meth:`_note_side_ink` for a label, whose width it measures."""
        width = string_width(label, self._safe_font_path(font_name), label_size)
        self._note_side_ink(
            label_x, label_x + width if side is Side.PRIMARY else label_x - width
        )

    @staticmethod
    def _tick_label_baseline(
        y: float, label_size: float, axis_top: float, axis_bottom: float
    ) -> float:
        """Baseline that centres a tick's label on its mark, kept on the page.

        The first and last ticks sit on the ends of the axis, where half the
        label would hang off; they are pulled back inside instead, the way
        the horizontal ticks anchor their end labels start / end.
        """
        baseline = y + label_size * 0.35
        return min(max(baseline, axis_top + label_size * 0.8), axis_bottom)

    def _draw_month_ticks_vertical(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
        axis_x: float,
        label_side: Side = Side.SECONDARY,
    ) -> None:
        """The built-in month ticks on a vertical axis.

        The fallback when a theme declares no ``timeline.ticks`` bands, and
        the twin of :py:meth:`_draw_month_ticks` down to the 18-tick label
        cut-off and the ``text:event_date`` styling.
        """
        ticks = self._month_tick_arrows(start, end)
        if not ticks:
            return

        draw_labels = len(ticks) <= 18
        tick_h = self._axis_tick_height(config)
        label_size = self._axis_tick_label_size(config)
        _tick_style = config.get_line_style("ec-axis-tick")
        tk_event_date = self._tk("text:event_date")
        label_offset = self._tick_label_offset(
            tick_h,
            label_size,
            config.timeline_tick_label_gap,
            config.timeline_tick_label_offset_y,
        )

        for m in ticks:
            y = self._y_for_day(m, start, end, axis_top, axis_bottom)
            self._draw_line(
                axis_x - tick_h,
                y,
                axis_x + tick_h,
                y,
                stroke=_tick_style.color,
                stroke_width=1.0,
                stroke_opacity=0.35,
                stroke_dasharray=_tick_style.dasharray or None,
                css_class="ec-axis-tick",
            )
            if draw_labels:
                label = format_arrow_date(m, config.timeline_tick_label_format)
                font_name = tk_event_date.get("font") or config.timeline_date_font
                label_x, anchor = self._tick_label_x(
                    axis_x, label_offset, label_side
                )
                self._draw_text(
                    label_x,
                    self._tick_label_baseline(y, label_size, axis_top, axis_bottom),
                    label,
                    font_name,
                    label_size,
                    fill=tk_event_date.get("color") or _tick_style.color,
                    fill_opacity=0.8,
                    anchor=anchor,
                    css_class="ec-label",
                )
                self._note_label_ink(
                    label_x, label, font_name, label_size, label_side
                )

    @staticmethod
    def _holiday_icon_size(config: "CalendarConfig") -> float:
        """Drawn height of one holiday icon; <= 0 suppresses the whole band."""
        return float(getattr(config, "timeline_holiday_icon_size", 10.0))

    @staticmethod
    def _holiday_date_font_size(config: "CalendarConfig") -> float:
        """Font size of the date printed under a holiday icon.

        Defaults to a fraction of the icon so the pair reads as one mark
        rather than as a label that happens to sit near an icon.
        """
        configured = getattr(config, "timeline_holiday_date_font_size", None)
        if configured:
            return float(configured)
        return max(6.0, TimelineRenderer._holiday_icon_size(config) * 0.68)

    def _holiday_marks(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        db: "CalendarDB",
        pos_for_day: "Callable[[arrow.Arrow], float] | None" = None,
    ) -> list[tuple[float, str, str]]:
        """Return (pos, icon_name, date_label) for each government holiday.

        ``pos`` is the mark's coordinate along the axis — x on a horizontal
        one, y on a vertical one, which is what ``pos_for_day`` is for.

        One mark per date: a day carrying several holidays is represented by
        the first one that is a nonworkday and has an icon, matching what the
        axis itself can show at that position.
        """
        if pos_for_day is None:
            def pos_for_day(day: arrow.Arrow) -> float:
                return self._x_for_day(day, start, end, axis_left, axis_right)
        date_format = (
            getattr(config, "timeline_holiday_date_format", None)
            or config.timeline_date_format
        )
        marks: list[tuple[float, str, str]] = []
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
            marks.append(
                (
                    pos_for_day(day),
                    str(icon_name),
                    format_arrow_date(day, date_format),
                )
            )
        return marks

    @staticmethod
    def _assign_holiday_date_rows(
        labels: list[tuple[float, float]],
        max_rows: int = 2,
    ) -> list[int]:
        """Place each date label on a row where it clears its neighbours.

        ``labels`` is (center_x, width) in axis order.  Holidays cluster —
        Christmas Eve and Christmas Day, Thanksgiving and the day after — so
        a single row would print those dates on top of each other.  Labels
        that fit nowhere return -1 and are left undrawn: the icon still marks
        the day, and a smeared date would say less than none.
        """
        gap = 3.0
        row_right: list[float] = []
        rows: list[int] = []
        for center_x, width in labels:
            left = center_x - width / 2.0
            for row in range(max_rows):
                if row == len(row_right):
                    row_right.append(left + width + gap)
                    rows.append(row)
                    break
                if left >= row_right[row]:
                    row_right[row] = left + width + gap
                    rows.append(row)
                    break
            else:
                rows.append(-1)
        return rows

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
        """Render each government holiday below the axis as an icon and,
        unless suppressed, the date it falls on."""
        size = self._holiday_icon_size(config)
        y_offset = float(getattr(config, "timeline_holiday_icon_y_offset", 4.0))
        if size <= 0:
            return
        color = getattr(config, "timeline_holiday_icon_color", None)
        baseline_y = axis_y + y_offset + (size * 0.80)

        marks = self._holiday_marks(
            config, start, end, axis_left, axis_right, db
        )
        for x, icon_name, _date_label in marks:
            self._draw_icon_svg(
                icon_name,
                x,
                baseline_y,
                size,
                anchor="middle",
                color=color,
                css_class="ec-holiday-icon",
            )

        if not getattr(config, "timeline_show_holiday_dates", True):
            return

        date_size = self._holiday_date_font_size(config)
        if date_size <= 0:
            return
        # ec-holiday-date is catalog-bound to text:event_date, so a theme that
        # styles event dates styles these too unless the holiday-specific
        # config field overrides it.
        _date_style = config.get_text_style("ec-holiday-date")
        font_name = _date_style.font or config.timeline_date_font
        font_path = self._safe_font_path(font_name)
        date_color = (
            getattr(config, "timeline_holiday_date_color", None)
            or _date_style.color
            or color
            or config.timeline_tick_color
        )
        # First date row clears the icon's descender; further rows stack below.
        first_baseline = axis_y + y_offset + size + (date_size * 0.95)
        row_stride = date_size * 1.15

        labelled = [(x, label) for x, _icon, label in marks if label]
        rows = self._assign_holiday_date_rows(
            [(x, string_width(label, font_path, date_size)) for x, label in labelled]
        )
        for (x, label), row in zip(labelled, rows):
            if row < 0:
                continue
            self._draw_text(
                x,
                first_baseline + (row * row_stride),
                label,
                font_name,
                date_size,
                fill=date_color,
                anchor="middle",
                css_class="ec-holiday-date",
            )

    def _holiday_band_extent(self, config: "CalendarConfig") -> float:
        """Height the holiday icons and their dates claim below the axis."""
        size = self._holiday_icon_size(config)
        if size <= 0 or not getattr(config, "timeline_show_holiday_icons", True):
            return 0.0
        y_offset = float(getattr(config, "timeline_holiday_icon_y_offset", 4.0))
        extent = y_offset + size
        if getattr(config, "timeline_show_holiday_dates", True):
            date_size = self._holiday_date_font_size(config)
            if date_size > 0:
                # Two rows are the most _assign_holiday_date_rows() will use,
                # and the last row's descenders hang below its baseline.
                extent += (date_size * 0.95) + (date_size * 1.15) + (date_size * 0.3)
        return extent

    @staticmethod
    def _callout_room(
        orient: Orientation, label_side: Side, room_low: float, room_high: float
    ) -> float:
        """How deep the callout stack may go before it leaves the paper.

        ``room_low`` / ``room_high`` are the space on the two sides of the
        axis in coordinate order — above / below a horizontal axis, left /
        right of a vertical one — and the answer is whichever the callouts
        actually take.  PRIMARY is above on a horizontal axis but *right* on
        a vertical one, which is why this cannot just read ``room_low``;
        doing that cost a vertical chart the wider half of its page.
        ``Side.BOTH`` is bounded by the smaller, since a stack has to fit
        on each.
        """
        if label_side is Side.BOTH:
            return min(room_low, room_high)
        primary_is_low = orient is Orientation.HORIZONTAL
        if label_side is Side.PRIMARY:
            return room_low if primary_is_low else room_high
        return room_high if primary_is_low else room_low

    @staticmethod
    def _duration_side(config: "CalendarConfig", label_side: Side) -> Side:
        """Which side of a vertical axis the duration bars stack on.

        ``timeline.duration_side: opposite`` — the default — puts them
        across the axis from the event callouts, which is how a horizontal
        timeline reads: callouts above, bars below.  Naming a concrete side
        pins them there instead, wherever the callouts went.
        """
        configured = str(
            getattr(config, "timeline_duration_side", "opposite") or "opposite"
        ).lower()
        if configured != "opposite":
            return Side(configured)
        if label_side is Side.BOTH:
            return Side.BOTH
        return Side.SECONDARY if label_side is Side.PRIMARY else Side.PRIMARY

    @staticmethod
    def _tick_label_side(duration_side: Side) -> Side:
        """Which side of a vertical axis carries the tick dates.

        Opposite the bars, whose first lane starts a few points off the
        axis — right where a date would be written.  With bars on both
        sides there is no clear side; the dates take the left, and a theme
        that wants them elsewhere can move the bars with
        ``timeline.duration_side``.
        """
        if duration_side is Side.PRIMARY:
            return Side.SECONDARY
        return Side.PRIMARY if duration_side is Side.SECONDARY else Side.SECONDARY

    @staticmethod
    def _month_tick_arrows(
        start: arrow.Arrow, end: arrow.Arrow
    ) -> list[arrow.Arrow]:
        """First day of each month inside the visible range."""
        month_start = start.floor("month")
        if month_start < start.floor("day"):
            month_start = month_start.shift(months=1)
        month_end = end.floor("month")
        if month_start > month_end:
            return []
        return list(arrow.Arrow.range("month", month_start, month_end))

    def _draw_month_ticks(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
    ) -> None:
        """Draw month-boundary ticks on a horizontal axis; labels are
        suppressed beyond 18 ticks to avoid overlap."""
        ticks = self._month_tick_arrows(start, end)
        if not ticks:
            return

        draw_labels = len(ticks) <= 18
        tick_h = self._axis_tick_height(config)
        label_size = self._axis_tick_label_size(config)

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
                    axis_y - self._tick_label_offset(
                        tick_h,
                        label_size,
                        config.timeline_tick_label_gap,
                        config.timeline_tick_label_offset_y,
                    ),
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

    def _draw_fiscal_bands_vertical(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
        axis_x: float,
        side: Side = Side.PRIMARY,
    ) -> None:
        """Fiscal period / quarter bands as columns beside a vertical axis.

        The horizontal bands stack above the axis, past the tick labels;
        these stack out to ``side`` — the tick labels' side — past the same
        labels.  A column is as narrow as those rows are short, so each
        band's name is rotated to read bottom-to-top, the way a duration
        bar's is.
        """
        from shared.fiscal_renderer import (
            build_fiscal_period_segments,
            build_fiscal_quarter_segments,
        )

        rows: list[list] = []
        if config.timeline_show_fiscal_quarters:
            rows.append(build_fiscal_quarter_segments(start.date(), end.date(), config))
        if config.timeline_show_fiscal_periods:
            rows.append(build_fiscal_period_segments(start.date(), end.date(), config))
        if not rows:
            return

        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        band_w = label_size * 1.8
        band_gap = 2.0
        sign = 1.0 if side is Side.PRIMARY else -1.0
        # Clear the tick labels, which occupy this side of the axis.
        band_start = axis_x + sign * (
            self._axis_label_clearance(config, start, end)
            or (self._axis_tick_height(config) + label_size * 1.5)
        )

        alt_colors = ["#e8eaf0", "#d4d8e8"]
        label_color = config.get_line_style("ec-axis-tick").color
        font_name = (
            self._tk("text:event_date").get("font") or config.timeline_date_font
        )

        for row_idx, segments in enumerate(rows):
            near = band_start + sign * (row_idx * (band_w + band_gap))
            col_x = min(near, near + sign * band_w)
            for seg_idx, seg in enumerate(segments):
                y1 = self._y_for_day(
                    arrow.get(seg.start), start, end, axis_top, axis_bottom
                )
                y2 = self._y_for_day(
                    arrow.get(seg.end_exclusive), start, end, axis_top, axis_bottom
                )
                y1 = max(y1, axis_top)
                y2 = min(y2, axis_bottom)
                if y2 <= y1:
                    continue
                self._draw_rect(
                    col_x, y1, band_w, y2 - y1,
                    fill=alt_colors[seg_idx % 2], fill_opacity=0.6,
                    stroke="#aaaaaa", stroke_width=0.5,
                    css_class="ec-callout-box",
                )
                self._note_side_ink(col_x, col_x + band_w)
                cx = col_x + band_w / 2.0
                cy = (y1 + y2) / 2.0
                self._draw_text(
                    cx, cy + label_size * 0.35, seg.label,
                    font_name,
                    label_size,
                    fill=label_color,
                    fill_opacity=0.9,
                    anchor="middle",
                    max_width=(y2 - y1) - 4.0,
                    transform=f"rotate(-90 {cx:.4f} {cy:.4f})",
                    css_class="ec-label",
                )

    def _draw_timeline_bands_vertical(
        self,
        config: "CalendarConfig",
        bands: list[dict],
        block_near_x: float,
        axis_top: float,
        axis_bottom: float,
        start: arrow.Arrow,
        end: arrow.Arrow,
        db: "CalendarDB",
        events: "list[Event] | None" = None,
        sign: float = -1.0,
    ) -> None:
        """:py:meth:`_draw_timeline_bands` as columns beside a vertical axis.

        A band's ``row_height`` is its column width here, and the stack
        grows away from the axis in ``sign`` — the top bands to the left of
        the chart, the bottom bands to the right, mirroring where they sit
        above and below a horizontal one.  Segment labels are rotated to
        read bottom-to-top, since a column is far taller than it is wide.
        """
        if not bands:
            return

        start_d = start.floor("day").date()
        end_d = end.floor("day").date()
        from datetime import timedelta
        visible_days: list = []
        d = start_d
        while d <= end_d:
            visible_days.append(d)
            d = d + timedelta(days=1)

        _events: list[Event] = events or []
        _day_classes: dict = (
            {d: classify_day(d, db, config) for d in visible_days}
            if db is not None else {}
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

        col_near = block_near_x
        for band in bands:
            col_w = float(band.get("row_height", 14.0))
            col_x = min(col_near, col_near + sign * col_w)
            unit = str(band.get("unit", "week")).strip().lower()

            if unit == "icon":
                icon_rules = list(band.get("icon_rules") or [])
                day_icon_map = compute_icon_band_days(
                    _events, icon_rules, visible_days, classify_fn=_classify
                )
                icon_h = float(band.get("icon_height") or col_w * 0.65)
                fill = str(band.get("fill_color") or "none")
                for day_d in visible_days:
                    day_arrow = arrow.Arrow(day_d.year, day_d.month, day_d.day)
                    cell_y = self._y_for_day(
                        day_arrow, start, end, axis_top, axis_bottom
                    )
                    cell_y2 = self._y_for_day(
                        day_arrow.shift(days=1), start, end, axis_top, axis_bottom
                    )
                    self._draw_icon_band_row(
                        [(col_x, col_w, day_icon_map.get(day_d, []))],
                        cell_y,
                        max(0.0, cell_y2 - cell_y),
                        icon_h,
                        fill,
                    )
                self._draw_line(
                    col_x, axis_top, col_x, axis_bottom,
                    stroke="#cccccc", stroke_width=0.5,
                    css_class="ec-separator",
                )
                self._note_side_ink(col_x, col_x + col_w)
                col_near += sign * col_w
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
                or max(7.0, col_w * 0.55)
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
                y1 = self._y_for_day(
                    arrow.Arrow(seg.start.year, seg.start.month, seg.start.day),
                    start, end, axis_top, axis_bottom,
                )
                y2 = self._y_for_day(
                    arrow.Arrow(
                        seg.end_exclusive.year,
                        seg.end_exclusive.month,
                        seg.end_exclusive.day,
                    ),
                    start, end, axis_top, axis_bottom,
                )
                seg_h = max(0.0, y2 - y1)
                if seg_h <= 0:
                    continue

                fill = alt_fill_color if seg_idx % 2 else fill_color
                if fill and fill.strip().lower() not in {"none", "transparent", ""}:
                    self._draw_rect(
                        col_x, y1, col_w, seg_h,
                        fill=fill,
                        fill_opacity=1.0,
                        css_class="ec-band-cell",
                    )
                if seg.label:
                    cx = col_x + col_w * 0.72
                    cy = y1 + seg_h / 2.0
                    # The label reads bottom→top, so a band's `text_align`
                    # lands along the segment: "left" pins the text to where
                    # it starts reading (the segment's bottom edge), "right"
                    # to where it ends.  rotate(-90) maps a pre-rotation
                    # offset of +dx onto -dx in y, hence the sign.
                    pad = 2.0
                    if text_align == "left":
                        text_x, anchor = cx + (cy - (y2 - pad)), "start"
                    elif text_align == "right":
                        text_x, anchor = cx + (cy - (y1 + pad)), "end"
                    else:
                        text_x, anchor = cx, "middle"
                    self._draw_text(
                        text_x, cy, seg.label,
                        band_font, font_size,
                        fill=band_label_color,
                        fill_opacity=text_opacity,
                        anchor=anchor,
                        max_width=seg_h - pad * 2,
                        transform=f"rotate(-90 {cx:.4f} {cy:.4f})",
                        css_class="ec-label",
                    )

            sep_x = col_x if sign < 0 else col_x + col_w
            self._draw_line(
                sep_x, axis_top, sep_x, axis_bottom,
                stroke="#cccccc", stroke_width=0.5,
                css_class="ec-separator",
            )
            self._note_side_ink(col_x, col_x + col_w)
            col_near += sign * col_w

    def _draw_holiday_icons_vertical(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
        axis_x: float,
        db: "CalendarDB",
        side: Side = Side.SECONDARY,
    ) -> None:
        """:py:meth:`_draw_holiday_icons` turned on its side.

        The icons sit between the axis and the first lane of duration bars,
        the same slot the horizontal axis gives them, so they take the bars'
        ``side``; ``timeline.holiday_icon_y_offset`` is the gap to the axis
        either way.  A day's date is written past its icon, stepping further
        out when two holidays fall close enough for their dates to touch.
        """
        size = self._holiday_icon_size(config)
        if size <= 0:
            return
        sign = 1.0 if side is Side.PRIMARY else -1.0
        y_offset = float(getattr(config, "timeline_holiday_icon_y_offset", 4.0))
        color = getattr(config, "timeline_holiday_icon_color", None)
        icon_x = axis_x + sign * (y_offset + size * 0.5)

        marks = self._holiday_marks(
            config, start, end, 0.0, 0.0, db,
            pos_for_day=lambda day: self._y_for_day(
                day, start, end, axis_top, axis_bottom
            ),
        )
        if not marks:
            return
        for y, icon_name, _date_label in marks:
            self._draw_icon_svg(
                icon_name,
                icon_x,
                self._icon_baseline(y, size),
                size,
                anchor="middle",
                color=color,
                css_class="ec-holiday-icon",
            )
            self._note_side_ink(icon_x - size / 2.0, icon_x + size / 2.0)

        if not getattr(config, "timeline_show_holiday_dates", True):
            return
        date_size = self._holiday_date_font_size(config)
        if date_size <= 0:
            return

        _date_style = config.get_text_style("ec-holiday-date")
        font_name = _date_style.font or config.timeline_date_font
        date_color = (
            getattr(config, "timeline_holiday_date_color", None)
            or _date_style.color
            or color
            or config.timeline_tick_color
        )
        # Rows step away from the axis, as they step down from a horizontal
        # one; along the axis a date claims its own line height.
        first_x = axis_x + sign * (y_offset + size + 2.0)
        row_stride = sign * (
            max(
                string_width(label, self._safe_font_path(font_name), date_size)
                for _p, _i, label in marks
            )
            + 3.0
        )
        labelled = [(y, label) for y, _icon, label in marks if label]
        rows = self._assign_holiday_date_rows(
            [(y, date_size * 1.2) for y, _label in labelled]
        )
        for (y, label), row in zip(labelled, rows):
            if row < 0:
                continue
            x = first_x + (row * row_stride)
            self._draw_text(
                x,
                y + date_size * 0.35,
                label,
                font_name,
                date_size,
                fill=date_color,
                anchor="start" if side is Side.PRIMARY else "end",
                css_class="ec-holiday-date",
            )
            self._note_label_ink(x, label, font_name, date_size, side)

    def _draw_today_marker_vertical(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
        axis_x: float,
        area_x: float,
        area_w: float,
        label_bounds: tuple[float, float] | None = None,
    ) -> None:
        """The today line and its label across a vertical axis.

        ``timeline.today_line_direction`` keeps its horizontal vocabulary:
        ``above`` is the primary side (right of a vertical axis) and
        ``below`` the secondary (left), the same pairing
        :py:class:`~shared.orientation.Side` uses.  ``_length`` 0 still
        means "the whole width available".
        """
        today = self._resolve_today(config)
        if today < start.floor("day") or today > end.floor("day"):
            return

        y = self._y_for_day(today, start, end, axis_top, axis_bottom)
        area_left = area_x
        area_right = area_x + area_w

        direction = (config.timeline_today_line_direction or "both").strip().lower()
        length = max(0.0, config.timeline_today_line_length)
        if length == 0.0:
            line_left = axis_x if direction == "above" else area_left
            line_right = axis_x if direction == "below" else area_right
        elif direction == "above":
            line_left, line_right = axis_x, axis_x + length
        elif direction == "below":
            line_left, line_right = axis_x - length, axis_x
        else:
            line_left, line_right = axis_x - length / 2.0, axis_x + length / 2.0
        line_left = max(line_left, area_left)
        line_right = min(line_right, area_right)

        _today_line_style = config.get_line_style("ec-today-line")
        _today_label_style = config.get_text_style("ec-today-label")
        self._draw_line(
            line_left,
            y,
            line_right,
            y,
            stroke=_today_line_style.color,
            stroke_width=1.0,
            stroke_opacity=0.55,
            stroke_dasharray=_today_line_style.dasharray or None,
            css_class="ec-today-line",
        )
        self._note_side_ink(line_left, line_right)
        tk_today_label = self._tk("text:today_label")
        label_size = (
            tk_today_label.get("size")
            or max(7.0, config.weekly_name_text_font_size * 0.8)
        )
        label = config.timeline_today_label_text or "Today"
        font_name = (
            tk_today_label.get("font")
            or _today_label_style.font
            or config.timeline_date_font
        )
        # The label rides off the leading end of the line, and tucks just
        # inside it when there is no room there — the horizontal marker
        # drops its label below the line's top for the same reason.
        # ``label_bounds`` keeps it out of the timeband columns, which are
        # painted over this line later in the pass.
        offset = max(0.0, config.timeline_today_label_offset_y)
        width = string_width(label, self._safe_font_path(font_name), label_size)
        left_limit, right_limit = label_bounds or (0.0, self._page_width)
        if line_left - offset - width >= left_limit:
            label_x, anchor = line_left - offset, "end"
            label_x = max(left_limit + width, min(label_x, right_limit))
        else:
            label_x, anchor = max(line_left, left_limit) + offset, "start"
            label_x = max(left_limit, min(label_x, right_limit - width))
        self._draw_text(
            label_x,
            y - label_size * 0.35,
            label,
            font_name,
            label_size,
            fill=tk_today_label.get("color") or _today_label_style.color,
            fill_opacity=0.85,
            anchor=anchor,
            css_class="ec-today-label",
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
        """Draw the vertical 'today' line (and its label) when today —
        or the ``timeline_today_date`` override — falls in range.
        ``timeline_today_line_direction`` (above/below/both) and
        ``_length`` (0 = full span) shape the line around the axis."""
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
    def _axis_tick_height(config: "CalendarConfig") -> float:
        """Half-length of a month tick mark, above and below the axis."""
        return max(6.0, config.timeline_axis_width * 2.5)

    @staticmethod
    def _tick_label_offset(
        tick_h: float,
        label_size: float,
        gap: float | None,
        offset: float | None,
    ) -> float:
        """Distance from the axis to a tick's date label, in points.

        ``offset`` is that distance outright; ``gap`` is measured from the
        tick's tip, so it moves with ``tick_length``.  With neither, the
        label sits 1.5 label heights past the tick.  Shared by the built-in
        month ticks and the ``timeline.ticks`` bands, which described the
        same three rules separately until a theme key existed for the
        built-in path.
        """
        if offset is not None:
            return float(offset)
        if gap is not None:
            return tick_h + float(gap)
        return tick_h + label_size * 1.5

    @staticmethod
    def _axis_tick_label_size(config: "CalendarConfig") -> float:
        """Font size of the month tick labels."""
        return max(7.0, float(config.weekly_name_text_font_size or 10.0) * 0.8)

    def _axis_label_clearance(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        orientation: Orientation = Orientation.HORIZONTAL,
    ) -> float:
        """Room the tick marks and their labels claim beside the axis.

        The innermost callout row sits exactly ``layer_gap`` off the axis,
        so without this the month labels — which share that band — end up
        printed inside that row's boxes.  Across a horizontal axis a label
        claims its own height; beside a vertical one it claims its *width*,
        which is several times more, so the two are measured differently.
        Returns 0 when no labels will be drawn, leaving the theme's layer
        gap untouched.
        """
        ticks = self._month_tick_arrows(start, end)
        # Mirrors _draw_month_ticks: no ticks, or too many to label, means
        # nothing is drawn up there.
        if not ticks or len(ticks) > 18:
            return 0.0

        label_size = self._axis_tick_label_size(config)
        baseline = self._tick_label_offset(
            self._axis_tick_height(config),
            label_size,
            config.timeline_tick_label_gap,
            config.timeline_tick_label_offset_y,
        )
        if orientation is Orientation.VERTICAL:
            font_path = self._safe_font_path(
                self._tk("text:event_date").get("font") or config.timeline_date_font
            )
            widest = max(
                string_width(
                    format_arrow_date(m, config.timeline_tick_label_format),
                    font_path,
                    label_size,
                )
                for m in ticks
            )
            return baseline + widest + _AXIS_LABEL_MARGIN
        # Glyphs rise about 0.8 of the size above their own baseline, so the
        # row has to clear the configured offset plus that.
        return baseline + (label_size * 0.8) + _AXIS_LABEL_MARGIN

    def _callout_date_label(
        self, config: "CalendarConfig", item: "TimelineCallout"
    ) -> str:
        """The date shown inside a callout box, or "" when it has none.

        A vertical timeline used to leave this blank on the theory that the
        axis already orders the events — but the box reserves the cell
        whichever way the axis runs, and a reader looking for a date should
        not have to measure the leader against the ticks.
        """
        return format_arrow_date(
            self._safe_day(item.event.start, fallback=arrow.now()),
            config.timeline_date_format,
        )

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
