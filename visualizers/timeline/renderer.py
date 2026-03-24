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

from config.config import get_font_path
from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import shrinktext, string_width
from shared.data_models import Event

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


@dataclass(frozen=True)
class TimelineCallout:
    """Point-in-time event callout placement."""

    event: Event
    color: str
    x: float
    lane: int
    box_x: float
    box_y: float
    box_width: float
    box_height: float
    date_row: int = 0


@dataclass(frozen=True)
class TimelineDuration:
    """Duration bar placement below the timeline axis."""

    event: Event
    color: str
    start_x: float
    end_x: float
    lane: int
    min_width: float


class TimelineRenderer(BaseSVGRenderer):
    """Renderer for timeline visualization."""

    _CALL_OUT_DATE_ROWS = 3

    @staticmethod
    def _callout_metrics(config: "CalendarConfig") -> tuple[float, float, float]:
        """Return (title_size, notes_size, date_size) for point-event callouts."""
        title_size = (
            float(config.timeline_name_text_font_size)
            if config.timeline_name_text_font_size is not None
            else max(10.0, config.weekly_name_text_font_size + 2.0)
        )
        notes_size = (
            float(config.timeline_notes_text_font_size)
            if config.timeline_notes_text_font_size is not None
            else max(8.0, config.weekly_name_text_font_size * 0.9)
        )
        date_size = max(8.0, config.weekly_name_text_font_size * 0.95)
        return title_size, notes_size, date_size

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
            return (ts * 1.9) + ((ns * 1.7) if has_notes else 0.0)

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
        bg = str(config.timeline_background_color or "").strip().lower()
        if bg not in {"", "none", "transparent"}:
            drawing.append(
                drawsvg.Rectangle(
                    0,
                    0,
                    round(config.pageX, 2),
                    round(config.pageY, 2),
                    fill=config.timeline_background_color,
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

        start = arrow.get(config.adjustedstart, "YYYYMMDD")
        end = arrow.get(config.adjustedend, "YYYYMMDD")
        if end < start:
            start, end = end, start

        axis_left = area_x + (area_w * 0.04)
        axis_right = area_x + (area_w * 0.96)
        axis_y = area_y + (area_h * 0.44)

        event_objs = [Event.from_dict(e) for e in events]
        self._load_icon_svg_cache(db)
        point_events, duration_events = self._split_events(config, event_objs)

        callouts = self._layout_callouts(
            config,
            point_events,
            start,
            end,
            axis_left,
            axis_right,
            area_x,
            area_x + area_w,
            axis_y,
            area_h,
        )
        durations = self._layout_durations(
            config,
            duration_events,
            start,
            end,
            axis_left,
            axis_right,
            axis_y,
        )

        # Pass 1: draw all connector/aligner lines below everything else.
        all_waypoints = self._route_all_callout_connectors(config, callouts, axis_y)
        for callout, waypoints in zip(callouts, all_waypoints):
            self._draw_routed_connector(config, callout, waypoints)
        for duration in durations:
            self._draw_duration_connectors(config, duration, axis_y)

        # Main axis, ticks, and today marker on top of connectors.
        self._draw_line(
            axis_left,
            axis_y,
            axis_right,
            axis_y,
            stroke=config.timeline_axis_color,
            stroke_width=config.timeline_axis_width,
            stroke_opacity=config.timeline_axis_opacity,
            stroke_dasharray=config.timeline_axis_stroke_dasharray or None,
        )

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

        # Pass 2: draw all boxes, markers, and text on top.
        for callout in callouts:
            self._draw_callout(config, callout, axis_y)
        for duration in durations:
            self._draw_duration(config, duration, axis_y)

        # After all content is laid out, tighten the TimelineArea coordinate to
        # the actual rendered extent so _shrink_drawing_to_content() crops
        # correctly when --shrink is requested.
        if config.shrink_to_content:
            coordinates["TimelineArea"] = self._actual_content_bounds(
                config,
                callouts,
                durations,
                axis_left,
                axis_right,
                axis_y,
                area_x,
                area_y,
                area_w,
            )

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

        # Durations extend below axis_y
        if durations:
            title_size, notes_size, d_date_size, bar_h = self._duration_metrics(config)
            min_duration_offset = self._min_duration_offset(d_date_size)
            duration_offset = max(
                config.timeline_duration_offset_y, min_duration_offset
            )
            lane_gap = max(config.timeline_duration_lane_gap_y, d_date_size * 0.9)
            lane_stride = bar_h + (d_date_size * 1.8) + lane_gap

            for dur in durations:
                bar_bottom = axis_y + duration_offset
                bar_y = bar_bottom + (dur.lane * lane_stride)
                # Date labels sit below bar at bar_y + bar_h + date_size * 1.1
                label_y = bar_y + bar_h + (d_date_size * 1.1)
                max_y = max(max_y, label_y + d_date_size)

        # X: axis extent (with 4% margins already baked in as area_x offsets)
        x = axis_left
        w = axis_right - axis_left

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
        axis_left: float,
        axis_right: float,
        content_left: float,
        content_right: float,
        axis_y: float,
        area_h: float,
    ) -> list[TimelineCallout]:
        if not events:
            return []

        ordered = sorted(
            events,
            key=lambda e: (
                e.start,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )

        title_font_size, notes_font_size, date_size = self._callout_metrics(config)
        content_width = max(60.0, content_right - content_left)
        configured_w = (
            float(config.timeline_event_box_width)
            if config.timeline_event_box_width is not None
            else 0.0
        )
        configured_h = (
            float(config.timeline_event_box_height)
            if config.timeline_event_box_height is not None
            else 0.0
        )
        if configured_w > 0:
            box_w = configured_w
        else:
            box_w_pref = min(area_h * 0.46, max(140.0, self._page_width * 0.14))
            # Keep callouts narrower on small pages so near-date events can lane cleanly.
            box_w = min(box_w_pref, max(80.0, content_width * 0.30))
        if configured_h > 0:
            box_h = configured_h
        else:
            box_h = title_font_size * 1.9 + (notes_font_size * 1.7)

        lane_gap = max(10.0, title_font_size * 0.7)
        # Reserve vertical room for staggered date labels near the axis.
        date_rows = max(1, self._CALL_OUT_DATE_ROWS)
        date_row_gap_factor = 1.35
        max_date_factor = 0.9 + ((date_rows - 1) * date_row_gap_factor)
        min_callout_offset = date_size * (max_date_factor + 1.0)
        base_top = axis_y - max(config.timeline_callout_offset_y, min_callout_offset)
        min_top = self._page_height * 0.015
        top_limit = min(base_top, min_top)
        if base_top < top_limit:
            # Small paper fallback: reduce preferred offset to keep room for lanes.
            base_top = axis_y - min_callout_offset
            top_limit = min(base_top, min_top)
        # If the preferred offset leaves too few lanes, pull the base up.
        lane_step = box_h + lane_gap
        lanes_possible = (
            int(((base_top - top_limit) / lane_step) + 1) if lane_step > 0 else 1
        )
        if lanes_possible < 4:
            base_top = axis_y - min_callout_offset
            top_limit = min(base_top, min_top)

        placed_boxes: list[tuple[float, float, float, float]] = []
        out: list[TimelineCallout] = []
        palette = config.timeline_top_colors or [config.timeline_name_text_font_color]

        for idx, event in enumerate(ordered):
            day = self._safe_day(event.start, fallback=start)
            x = self._x_for_day(day, start, end, axis_left, axis_right)
            color = palette[idx % len(palette)]

            chosen: tuple[int, float, float] | None = None
            # Try multiple horizontal offsets per lane to avoid box collisions.
            # Offsets keep the date x within or near the box so the connector
            # line remains short; larger offsets are included as last resort.
            offsets = [
                0.0,  # date at box centre
                -(box_w * 0.32),  # date at 82 % from left
                box_w * 0.32,  # date at 18 % from left
                -(box_w * 0.64),  # date just past right edge
                box_w * 0.64,  # date just past left edge
                -(box_w * 0.90),  # well to the right of box
                box_w * 0.90,  # well to the left of box
            ]

            for lane in range(16):
                box_y = base_top - lane * (box_h + lane_gap)
                if box_y < top_limit:
                    break

                for offset in offsets:
                    cand_x = x - (box_w / 2) + offset
                    cand_x = max(
                        content_left + 6.0, min(cand_x, content_right - box_w - 6.0)
                    )
                    cand_box = (cand_x, box_y, cand_x + box_w, box_y + box_h)

                    if any(
                        self._boxes_overlap(cand_box, b, pad=6.0) for b in placed_boxes
                    ):
                        continue

                    chosen = (lane, cand_x, box_y)
                    break

                if chosen is not None:
                    break

            if chosen is None:
                # Fine-grained Y search to avoid overlaps on small paper sizes.
                y_step = max(3.0, notes_font_size * 0.7)
                probe_y = axis_y - min_callout_offset
                while probe_y >= top_limit and chosen is None:
                    for offset in offsets:
                        fallback_x = x - (box_w / 2) + offset
                        fallback_x = max(
                            content_left + 6.0,
                            min(fallback_x, content_right - box_w - 6.0),
                        )
                        cand_box = (
                            fallback_x,
                            probe_y,
                            fallback_x + box_w,
                            probe_y + box_h,
                        )
                        if not any(
                            self._boxes_overlap(cand_box, b, pad=4.0)
                            for b in placed_boxes
                        ):
                            chosen = (0, fallback_x, probe_y)
                            break
                    probe_y -= y_step

            if chosen is None:
                # No non-overlapping slot exists in current page area; keep distinct
                # Y to minimize overlap severity instead of collapsing to one row.
                # Start from base_top (first lane Y) so the spread events sit
                # above the lanes rather than colliding with them from below.
                spread_step = max(box_h + 2.0, notes_font_size * 1.2)
                fallback_y = base_top - (len(out) * spread_step)
                fallback_x = x - (box_w / 2)
                fallback_x = max(
                    content_left + 6.0,
                    min(fallback_x, content_right - box_w - 6.0),
                )
                chosen = (0, fallback_x, fallback_y)

            lane, box_x, box_y = chosen
            placed_boxes.append((box_x, box_y, box_x + box_w, box_y + box_h))
            out.append(
                TimelineCallout(
                    event=event,
                    color=color,
                    x=x,
                    lane=lane,
                    box_x=box_x,
                    box_y=box_y,
                    box_width=box_w,
                    box_height=box_h,
                    date_row=idx % date_rows,
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
        palette = config.timeline_bottom_colors or [config.timeline_notes_text_font_color]
        title_size, notes_size, _, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(config.timeline_notes_text_font_name)
        notes_font_path = self._safe_font_path(config.timeline_notes_text_font_name)

        out: list[TimelineDuration] = []

        for idx, event in enumerate(ordered):
            start_day = self._safe_day(event.start, fallback=start)
            end_day = self._safe_day(event.end, fallback=start_day)
            if end_day < start_day:
                start_day, end_day = end_day, start_day

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
            out.append(
                TimelineDuration(
                    event=event,
                    color=color,
                    start_x=sx,
                    end_x=ex,
                    lane=lane,
                    min_width=min_width,
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

    def _route_all_callout_connectors(
        self,
        config: "CalendarConfig",
        callouts: list[TimelineCallout],
        axis_y: float,
    ) -> list[list[tuple[float, float]]]:
        """Route all callout connectors via orthogonal routing (graph_layout library).

        Callout boxes and axis stub nodes are already in SVG coordinates (y↓),
        so waypoints are passed directly to route_all_edges + nudge_overlapping_segments
        without any coordinate conversion.

        Returns one waypoint list per callout in the same order as the input.
        Each list includes the axis start point and box-top end point.
        """
        from graph_layout.orthogonal.edge_routing import (
            nudge_overlapping_segments,
            route_all_edges,
        )
        from graph_layout.orthogonal.types import NodeBox, Side

        if not callouts:
            return []

        n = len(callouts)
        axis_screen_y = axis_y

        # Build NodeBoxes in screen coords (y increases downward).
        boxes: list[NodeBox] = []

        # Callout boxes (indices 0 .. n-1).
        for i, item in enumerate(callouts):
            box_cx = item.box_x + item.box_width / 2.0
            box_cy_svg = item.box_y + item.box_height / 2.0
            boxes.append(
                NodeBox(
                    index=i,
                    x=box_cx,
                    y=box_cy_svg,
                    width=item.box_width,
                    height=item.box_height,
                )
            )

        # Axis stubs (indices n .. 2n-1): tiny nodes whose NORTH port lands
        # exactly on the timeline axis so the connector starts at the event date.
        for i, item in enumerate(callouts):
            boxes.append(
                NodeBox(
                    index=n + i,
                    x=item.x,
                    y=axis_screen_y + 0.5,  # NORTH port = y - h/2 = axis_screen_y
                    width=2.0,
                    height=1.0,
                )
            )

        # Each edge: axis stub (n+i) → callout box (i).
        # NORTH exits top of stub toward boxes; SOUTH enters bottom of box.
        edges = [(n + i, i) for i in range(n)]
        edge_indices = list(range(n))
        port_constraints: dict[tuple[int, int], tuple[Side, Side]] = {
            (n + i, i): (Side.NORTH, Side.SOUTH) for i in range(n)
        }

        edge_separation = max(3.0, config.timeline_axis_width * 3.0)

        routed = route_all_edges(
            boxes=boxes,
            edges=edges,
            edge_indices=edge_indices,
            edge_separation=edge_separation,
            port_constraints=port_constraints,
        )
        routed = nudge_overlapping_segments(routed, boxes, edge_separation)

        box_map = {b.index: b for b in boxes}

        result: list[list[tuple[float, float]]] = []
        for edge in routed:
            src_box = box_map[edge.source]
            tgt_box = box_map[edge.target]
            src_pos = src_box.get_port_position(
                edge.source_port.side, edge.source_port.position
            )
            tgt_pos = tgt_box.get_port_position(
                edge.target_port.side, edge.target_port.position
            )
            pts_screen = [src_pos] + list(edge.bends) + [tgt_pos]
            # Waypoints are already in SVG coords — no conversion needed.
            result.append(list(pts_screen))

        return result

    def _draw_routed_connector(
        self,
        config: "CalendarConfig",
        callout: TimelineCallout,
        waypoints: list[tuple[float, float]],
    ) -> None:
        """Draw connector line segments from axis point to callout box."""
        kw: dict = dict(
            stroke=callout.color,
            stroke_width=1.1,
            stroke_opacity=0.9,
            stroke_dasharray=config.timeline_connector_stroke_dasharray or None,
        )
        for j in range(len(waypoints) - 1):
            x1, y1 = waypoints[j]
            x2, y2 = waypoints[j + 1]
            self._draw_line(x1, y1, x2, y2, **kw)

    def _draw_callout_connector(
        self,
        config: "CalendarConfig",
        item: TimelineCallout,
        axis_y: float,
        callouts: list[TimelineCallout] | None = None,
        placed_segs: list[tuple[float, float, float, float]] | None = None,
        axis_left: float | None = None,
        axis_right: float | None = None,
    ) -> None:
        """Draw only the connector line from the axis to the callout box.

        Routing strategy (in priority order):
        1. Straight vertical — when the event x falls within the box's horizontal
           span and the direct path is unobstructed.
        2. Two-segment L-shape — one bend at box-bottom level when possible.
        3. Three-segment Z-shape — elbow height chosen proportional to the
           callout's lane so higher boxes get higher elbows, distributing
           horizontal segments across the full vertical space instead of
           clustering them near the axis.
        All routes are checked against other callout boxes *and* against
        previously placed connector segments (passed in via placed_segs).
        """
        box_left = item.box_x
        box_right = item.box_x + item.box_width
        if item.x <= box_left:
            connect_x = box_left
        elif item.x >= box_right:
            connect_x = box_right
        else:
            connect_x = item.x

        others = [
            (c.box_x, c.box_y, c.box_x + c.box_width, c.box_y + c.box_height)
            for c in (callouts or [])
            if c is not item
        ]

        y0 = axis_y
        y1 = item.box_y
        x0 = item.x
        xt = connect_x
        height = max(1.0, y0 - y1)

        box_pad = 0.6
        seg_clear = 2.0  # min clearance from existing connector segments

        def _seg_hits_box(seg: tuple[float, float, float, float]) -> bool:
            return any(
                self._segment_intersects_rect(seg, rect, box_pad) for rect in others
            )

        def _seg_hits_placed(seg: tuple[float, float, float, float]) -> bool:
            if not placed_segs:
                return False
            return any(
                self._segments_collinear_overlap(seg, s, seg_clear) for s in placed_segs
            )

        def _seg_blocked(seg: tuple[float, float, float, float]) -> bool:
            return _seg_hits_box(seg) or _seg_hits_placed(seg)

        def _route_hits_any(elbow_y: float, xmid: float) -> bool:
            # The first vertical (axis → elbow) is anchored at the event's x and
            # cannot be rerouted, so only test it against boxes, not placed segs.
            if _seg_hits_box((x0, y0, x0, elbow_y)):
                return True
            # The remaining segments are optional and can be avoided.
            if abs(xmid - x0) > 0.5 and _seg_blocked((x0, elbow_y, xmid, elbow_y)):
                return True
            if _seg_blocked((xmid, elbow_y, xmid, y1)):
                return True
            if abs(xt - xmid) > 0.5 and _seg_blocked((xmid, y1, xt, y1)):
                return True
            return False

        # --- Elbow height candidates ---
        # Distribute elbows evenly across the full axis-to-box height.
        # A lane-proportional "natural" elbow is tried first so that lower
        # lanes use low elbows and higher lanes use high elbows, creating
        # a fan that keeps horizontal segments from clustering near the axis.
        max_lane = max((c.lane for c in (callouts or [item])), default=0)
        lane_frac = (item.lane + 0.5) / max(max_lane + 1, 2)
        natural_elbow = y0 - lane_frac * height * 0.85

        n_spread = 7
        spread_elbows = [
            y0 - height * (k / (n_spread + 1)) for k in range(1, n_spread + 1)
        ]
        # Sort spread candidates by closeness to the natural elbow.
        spread_sorted = sorted(spread_elbows, key=lambda e: abs(e - natural_elbow))
        elbow_candidates: list[float] = [natural_elbow] + [
            e for e in spread_sorted if abs(e - natural_elbow) > 1.0
        ]
        elbow_candidates = [e for e in elbow_candidates if y1 < e < y0]
        if not elbow_candidates:
            elbow_candidates = [y0 - height * 0.5]

        # --- Horizontal midpoint candidates ---
        gap = max(4.0, config.timeline_axis_width * 2.0)
        lane_step = max(6.0, config.timeline_axis_width * 5.0)
        # Fan-out by date_row to separate same-date connectors.
        if item.date_row <= 0:
            row_offset = 0.0
        else:
            mag = (item.date_row + 1) // 2
            row_offset = lane_step * mag * (1.0 if (item.date_row % 2 == 1) else -1.0)
        preferred_x = x0 + row_offset

        x_candidates: set[float] = {preferred_x, x0, xt}
        for left, _bot, right, _top in others:
            x_candidates.add(left - gap)
            x_candidates.add(right + gap)
        # Clamp candidates to the timeline axis bounds so the router never picks
        # an xmid that lies outside the visible timeline area.  Fall back to
        # page margins when axis bounds are not provided (e.g. unit tests).
        page_margin = max(6.0, config.timeline_axis_width * 3.0)
        x_lo = axis_left if axis_left is not None else page_margin
        x_hi = axis_right if axis_right is not None else self._page_width - page_margin
        ordered_x = [
            v
            for v in sorted(
                x_candidates, key=lambda v: (abs(v - preferred_x), abs(v - x0))
            )
            if x_lo <= v <= x_hi
        ]
        if not ordered_x:
            ordered_x = [max(x_lo, min(preferred_x, x_hi))]

        def _route_hits_boxes_only(elbow_y: float, xmid: float) -> bool:
            """Like _route_hits_any but ignores placed connector segments."""
            if _seg_hits_box((x0, y0, x0, elbow_y)):
                return True
            if abs(xmid - x0) > 0.5 and _seg_hits_box((x0, elbow_y, xmid, elbow_y)):
                return True
            if _seg_hits_box((xmid, elbow_y, xmid, y1)):
                return True
            if abs(xt - xmid) > 0.5 and _seg_hits_box((xmid, y1, xt, y1)):
                return True
            return False

        chosen: tuple[float, float] | None = None

        # Straight/L-shape optimisations only apply when date_row is 0 (no
        # fan-out needed). When date_row > 0, nearby events share the same
        # date and the Z-shape with preferred_x offset is required to
        # separate their connectors visually.
        if item.date_row == 0:
            # --- Attempt 1: Straight vertical (zero bends) ---
            if box_left <= x0 <= box_right:
                if not _seg_blocked((x0, y0, x0, y1)):
                    # Encode as "elbow at y1" — the draw step below handles this.
                    chosen = (y1, x0)

            # --- Attempt 2: L-shape (one bend at box-bottom level) ---
            if chosen is None and not _seg_blocked((x0, y0, x0, y1)):
                if abs(xt - x0) > 0.5 and not _seg_blocked((x0, y1, xt, y1)):
                    chosen = (y1, x0)

        # --- Attempt 3: Z-shape with natural-first elbow selection ---
        if chosen is None:
            for elbow_y in elbow_candidates:
                for xmid in ordered_x:
                    if not _route_hits_any(elbow_y, xmid):
                        chosen = (elbow_y, xmid)
                        break
                if chosen is not None:
                    break

        # --- Attempt 4: Relax placed_segs constraint (avoid boxes only) ---
        # Handles scenes where placed connectors fill all viable channels but a
        # box-avoiding route still exists.
        if chosen is None:
            for elbow_y in elbow_candidates:
                for xmid in ordered_x:
                    if not _route_hits_boxes_only(elbow_y, xmid):
                        chosen = (elbow_y, xmid)
                        break
                if chosen is not None:
                    break

        # --- Final fallback: draw the most direct path regardless ---
        # When the scene is too dense for any clean route, draw a straight
        # vertical to the box bottom (plus a short horizontal to connect_x if
        # needed). Portions hidden under other boxes are acceptable — at least
        # the connector is visible near the axis and near its own box.
        if chosen is None:
            chosen = (y1, x0)

        elbow_y, xmid = chosen

        kw: dict = dict(
            stroke=item.color,
            stroke_width=1.1,
            stroke_opacity=0.9,
            stroke_dasharray=config.timeline_connector_stroke_dasharray or None,
        )

        new_segs: list[tuple[float, float, float, float]] = []

        if elbow_y <= y1 + 0.5:
            # Straight/L path: vertical up, optional horizontal at box top.
            # The vertical is mandatory and not registered in placed_segs so that
            # co-located events don't block each other's first segment.
            self._draw_line(x0, y0, x0, y1, **kw)
            if abs(xt - x0) > 0.5:
                self._draw_line(x0, y1, xt, y1, **kw)
                new_segs.append((x0, y1, xt, y1))
        else:
            # Z-shape: vertical → horizontal at elbow → vertical → optional horizontal.
            # First vertical is mandatory; not registered in placed_segs.
            self._draw_line(x0, y0, x0, elbow_y, **kw)
            if abs(xmid - x0) > 0.5:
                self._draw_line(x0, elbow_y, xmid, elbow_y, **kw)
                new_segs.append((x0, elbow_y, xmid, elbow_y))
            self._draw_line(xmid, elbow_y, xmid, y1, **kw)
            new_segs.append((xmid, elbow_y, xmid, y1))
            if abs(xt - xmid) > 0.5:
                self._draw_line(xmid, y1, xt, y1, **kw)
                new_segs.append((xmid, y1, xt, y1))

        if placed_segs is not None:
            placed_segs.extend(new_segs)

    @staticmethod
    def _segment_intersects_rect(
        seg: tuple[float, float, float, float],
        rect: tuple[float, float, float, float],
        pad: float = 0.0,
    ) -> bool:
        """Check whether an axis-aligned segment intersects a rectangle."""
        x1, y1, x2, y2 = seg
        rx1, ry1, rx2, ry2 = rect
        rx1 -= pad
        ry1 -= pad
        rx2 += pad
        ry2 += pad

        if abs(x1 - x2) < 1e-9:
            x = x1
            sy1, sy2 = (y1, y2) if y1 <= y2 else (y2, y1)
            return rx1 <= x <= rx2 and not (sy2 <= ry1 or sy1 >= ry2)
        if abs(y1 - y2) < 1e-9:
            y = y1
            sx1, sx2 = (x1, x2) if x1 <= x2 else (x2, x1)
            return ry1 <= y <= ry2 and not (sx2 <= rx1 or sx1 >= rx2)
        # Non-orthogonal segments are not expected here.
        return False

    @staticmethod
    def _segments_collinear_overlap(
        seg_a: tuple[float, float, float, float],
        seg_b: tuple[float, float, float, float],
        clearance: float = 1.5,
    ) -> bool:
        """True if two axis-aligned segments share an axis within *clearance* and overlap."""
        ax1, ay1, ax2, ay2 = seg_a
        bx1, by1, bx2, by2 = seg_b
        # Both vertical?
        if abs(ax1 - ax2) < 1e-9 and abs(bx1 - bx2) < 1e-9:
            if abs(ax1 - bx1) > clearance:
                return False
            sa_lo, sa_hi = min(ay1, ay2), max(ay1, ay2)
            sb_lo, sb_hi = min(by1, by2), max(by1, by2)
            return sa_lo < sb_hi and sb_lo < sa_hi
        # Both horizontal?
        if abs(ay1 - ay2) < 1e-9 and abs(by1 - by2) < 1e-9:
            if abs(ay1 - by1) > clearance:
                return False
            sa_lo, sa_hi = min(ax1, ax2), max(ax1, ax2)
            sb_lo, sb_hi = min(bx1, bx2), max(bx1, bx2)
            return sa_lo < sb_hi and sb_lo < sa_hi
        return False

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
        self._draw_timeline_marker(
            config,
            x=item.x,
            y=axis_y,
            color=item.color,
            icon_name=None,
        )

        # Label box.
        self._draw_rect(
            item.box_x,
            item.box_y,
            item.box_width,
            item.box_height,
            fill=item.color,
            fill_opacity=config.timeline_label_fill_opacity,
            stroke=item.color,
            stroke_width=config.timeline_label_stroke_width,
            stroke_opacity=0.95,
            stroke_dasharray=config.timeline_label_stroke_dasharray or None,
        )

        has_icon = bool(item.event.icon and self._resolve_icon_svg(item.event.icon))
        icon_gap = 2.0
        icon_reserved = (title_font_size + icon_gap) if has_icon else 0.0

        title_font_path = self._safe_font_path(config.timeline_name_text_font_name)
        notes_font_path = self._safe_font_path(config.timeline_notes_text_font_name)
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

        event_text_color = config.timeline_name_text_font_color or item.color

        if has_icon:
            self._draw_icon_svg(
                item.event.icon,
                text_x,
                title_y,
                fitted_title,
                anchor="start",
                color=event_text_color,
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
            config.timeline_name_text_font_name,
            fitted_title,
            fill=event_text_color,
            max_width=title_max_w,
        )

        if notes:
            self._draw_text(
                text_x,
                notes_y,
                notes,
                config.timeline_notes_text_font_name,
                fitted_notes,
                fill=event_text_color,
                max_width=item.box_width - 12.0,
            )

        date_label = self._safe_day(item.event.start, fallback=arrow.now()).format(
            config.timeline_date_format
        )
        date_row_gap_factor = 1.35
        date_y = axis_y - (
            date_font_size * (0.9 + (item.date_row * date_row_gap_factor))
        )
        self._draw_text(
            item.x,
            date_y,
            date_label,
            config.timeline_date_font,
            date_font_size,
            fill=event_text_color,
            anchor="middle",
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
        self._draw_line(
            item.start_x,
            axis_y,
            item.start_x,
            bar_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=config.timeline_duration_bracket_stroke_dasharray or None,
        )
        self._draw_line(
            item.end_x,
            axis_y,
            item.end_x,
            bar_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=config.timeline_duration_bracket_stroke_dasharray or None,
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
        self._draw_rect(
            item.start_x,
            bar_y,
            max(1.0, item.end_x - item.start_x),
            bar_h,
            fill=item.color,
            fill_opacity=config.timeline_duration_bar_fill_opacity,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.9,
            stroke_dasharray=config.timeline_duration_bar_stroke_dasharray or None,
        )

        # Start/end markers on the main axis.
        self._draw_circle(
            item.start_x,
            axis_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=item.color,
            stroke=config.timeline_marker_stroke_color,
            stroke_width=max(0.6, config.timeline_marker_stroke_width * 0.8),
        )
        self._draw_circle(
            item.end_x,
            axis_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=item.color,
            stroke=config.timeline_marker_stroke_color,
            stroke_width=max(0.6, config.timeline_marker_stroke_width * 0.8),
        )

        title_font_path = self._safe_font_path(config.timeline_notes_text_font_name)
        notes_font_path = self._safe_font_path(config.timeline_notes_text_font_name)
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
        duration_text_color = config.timeline_name_text_font_color or item.color
        title_y = bar_y + fitted_title * 1.15
        self._draw_text(
            (item.start_x + item.end_x) / 2,
            title_y,
            title,
            config.timeline_notes_text_font_name,
            fitted_title,
            fill=duration_text_color,
            anchor="middle",
            max_width=text_w,
        )

        if notes:
            notes_y = title_y + (fitted_notes * 1.35)
            self._draw_text(
                (item.start_x + item.end_x) / 2,
                notes_y,
                notes,
                config.timeline_notes_text_font_name,
                fitted_notes,
                fill=duration_text_color,
                anchor="middle",
                max_width=text_w,
            )

        # Keep start/end labels on the same Y baseline.
        date_font = config.timeline_duration_date_font or config.timeline_date_font
        date_color = config.timeline_duration_date_color or duration_text_color
        date_y = bar_y + bar_h + (date_size * 1.1)
        self._draw_text(
            item.start_x,
            date_y,
            start_day.format(config.timeline_date_format),
            date_font,
            date_size,
            fill=date_color,
            anchor="middle",
        )
        self._draw_text(
            item.end_x,
            date_y,
            end_day.format(config.timeline_date_format),
            date_font,
            date_size,
            fill=date_color,
            anchor="middle",
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

        if icon_found:
            self._draw_circle(
                x,
                y,
                radius=radius,
                fill="none",
                stroke=effective_color,
                stroke_width=config.timeline_marker_stroke_width,
            )
            # DB-provided SVG icon centered in the circle.
            self._draw_icon_svg(
                effective_icon,
                x,
                y,
                max(7.0, config.timeline_icon_size),
                anchor="middle",
                color=effective_color,
            )
            return

        self._draw_circle(
            x,
            y,
            radius=radius,
            fill=color,
            stroke=config.timeline_marker_stroke_color,
            stroke_width=config.timeline_marker_stroke_width,
        )

    @staticmethod
    def _duration_metrics(
        config: "CalendarConfig",
    ) -> tuple[float, float, float, float]:
        """Return (title_size, notes_size, date_size, bar_height)."""
        title_size = (
            float(config.timeline_name_text_font_size * 0.85)
            if config.timeline_name_text_font_size is not None
            else max(8.0, config.weekly_name_text_font_size * 0.86)
        )
        notes_size = (
            float(config.timeline_notes_text_font_size * 0.82)
            if config.timeline_notes_text_font_size is not None
            else max(7.0, config.weekly_name_text_font_size * 0.74)
        )
        date_size = (
            float(config.timeline_duration_date_font_size)
            if config.timeline_duration_date_font_size is not None
            else max(7.0, config.weekly_name_text_font_size * 0.78)
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

        for m in ticks:
            x = self._x_for_day(m, start, end, axis_left, axis_right)
            self._draw_line(
                x,
                axis_y - tick_h,
                x,
                axis_y + tick_h,
                stroke=config.timeline_tick_color,
                stroke_width=1.0,
                stroke_opacity=0.35,
                stroke_dasharray=config.timeline_tick_stroke_dasharray or None,
            )
            if draw_labels:
                self._draw_text(
                    x,
                    axis_y - (tick_h + label_size * 1.5),
                    m.format(config.timeline_tick_label_format),
                    config.timeline_date_font,
                    label_size,
                    fill=config.timeline_tick_color,
                    fill_opacity=0.8,
                    anchor="middle",
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
        label_color = config.timeline_tick_color

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
                )
                cx = (x1 + x2) / 2.0
                cy = row_top + band_h / 2.0 + label_size * 0.35
                self._draw_text(
                    cx, cy, seg.label,
                    config.timeline_date_font,
                    label_size,
                    fill=label_color,
                    fill_opacity=0.9,
                    anchor="middle",
                    max_width=x2 - x1 - 4.0,
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

        self._draw_line(
            x,
            line_top,
            x,
            line_bottom,
            stroke=config.timeline_today_line_color,
            stroke_width=1.0,
            stroke_opacity=0.55,
            stroke_dasharray=config.timeline_today_line_dasharray or None,
        )
        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
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
            config.timeline_date_font,
            label_size,
            fill=config.timeline_today_label_color,
            fill_opacity=0.85,
            anchor="middle",
        )

    def _draw_circle(
        self,
        cx: float,
        cy: float,
        radius: float,
        fill: str,
        stroke: str,
        stroke_width: float,
    ) -> None:
        self._drawing.append(
            drawsvg.Circle(
                cx,
                cy,
                radius,
                fill=fill,
                stroke=stroke,
                stroke_width=stroke_width,
            )
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
    def _safe_font_path(font_name: str) -> str:
        try:
            return get_font_path(font_name)
        except KeyError:
            return get_font_path("RobotoCondensed-Bold")

    @staticmethod
    def _callout_metrics(config: "CalendarConfig") -> tuple[float, float, float]:
        """Return (title_size, notes_size, date_size) for point-event callouts."""
        title_size = (
            float(config.timeline_name_text_font_size)
            if config.timeline_name_text_font_size is not None
            else max(10.0, config.weekly_name_text_font_size + 2.0)
        )
        notes_size = (
            float(config.timeline_notes_text_font_size)
            if config.timeline_notes_text_font_size is not None
            else max(8.0, config.weekly_name_text_font_size * 0.9)
        )
        date_size = max(8.0, config.weekly_name_text_font_size * 0.95)
        return title_size, notes_size, date_size
