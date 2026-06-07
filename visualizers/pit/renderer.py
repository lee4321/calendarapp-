"""
PIT (Points in Time) SVG renderer.

Phase 1 MVP: horizontal axis, single-side labels (PRIMARY), event dots,
labella bezier leaders, label boxes, and label text.

Later phases add: vertical direction, Side.BOTH, opposite-side date
labels, milestones, custom marker icons, SVG marker-start/end on axis +
leaders + today line, fully themeable today line, ec-* CSS class
emission with data-* attrs, rule-engine integration, and the 7 theme
YAML blocks.

The renderer never imports labella directly — it goes through
`pit/labella_adapter.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import arrow
import drawsvg

from renderers.svg_base import BaseSVGRenderer
from shared.data_models import Event
from visualizers.pit.labella_adapter import (
    PITPlacement,
    layout_pit_callouts,
)
from visualizers.pit.markers import draw_marker, resolve_marker
from shared.date_utils import format_arrow_date
from visualizers.timeline.orientation import Orientation, Side, opposite

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


# Inset from the PITArea edges to the axis endpoints (in fractional axis
# coords). 0.04 = 4% margin on each end so the first/last dot has space
# to draw without colliding with the page margin.
_AXIS_INSET: float = 0.04


def _xml_escape(s: str) -> str:
    """Minimal XML attribute escape — & " < > only."""
    return (
        s.replace("&", "&amp;")
         .replace('"', "&quot;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


class PITRenderer(BaseSVGRenderer):
    """Renderer for the PIT (Points in Time) visualization.

    Phase 1 MVP — see module docstring for what is and is not yet wired.
    """

    def __init__(self):
        super().__init__()
        # Per-render dedup of <marker> defs. Key = (kind, color, size);
        # value = the assigned id used in the marker-start/end attributes.
        # Reset at the top of _render_content so re-rendering does not
        # accumulate ids across runs.
        self._pit_marker_ids: dict[tuple[str, str, float], str] = {}

    # ------------------------------------------------------------------
    # Required override
    # ------------------------------------------------------------------
    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        """Render the PIT axis + callouts. Returns (overflow_count, [])."""
        # Reset per-render state.
        self._pit_marker_ids = {}
        area_x, area_y, area_w, area_h = coordinates.get(
            "PITArea", (0.0, 0.0, config.pageX, config.pageY)
        )

        # 1) Resolve date range. Prefer userstart/userend so the axis
        #    matches the user-typed range exactly (consistent with
        #    timeline renderer).
        user_start_str = getattr(config, "userstart", None) or config.adjustedstart
        user_end_str = getattr(config, "userend", None) or config.adjustedend
        start = arrow.get(user_start_str, "YYYYMMDD")
        end = arrow.get(user_end_str, "YYYYMMDD")
        if end < start:
            start, end = end, start

        # 2) Convert event dicts → Event dataclasses.
        event_objs: list[Event] = [Event.from_dict(e) for e in events]
        # MVP: drop any duration events that slipped past the filter.
        # The shared filter_events() already does this when
        # config.includedurations=False, but we belt-and-braces here so
        # PIT never tries to place a multi-day event.
        point_events = [e for e in event_objs if not e.is_duration]
        dropped = len(event_objs) - len(point_events)
        if dropped:
            import logging
            logging.getLogger(__name__).info(
                "PIT: skipped %d multi-day events (use the timeline "
                "visualizer for durations)",
                dropped,
            )

        # 3) Compute axis geometry. Phase 1 is horizontal-only.
        direction = Orientation(config.pit_direction)
        side = Side(config.pit_label_side)

        if direction is Orientation.HORIZONTAL:
            axis_left = area_x + (area_w * _AXIS_INSET)
            axis_right = area_x + (area_w * (1.0 - _AXIS_INSET))
            axis_y = area_y + (area_h * 0.5)  # mid-band horizontally
            axis_origin = (axis_left, axis_y)
            axis_length = axis_right - axis_left
            axis_end = (axis_right, axis_y)
        else:
            axis_top = area_y + (area_h * _AXIS_INSET)
            axis_bottom = area_y + (area_h * (1.0 - _AXIS_INSET))
            # Center the vertical axis when labels are on both sides;
            # bias to one side otherwise so the labels have room.
            if side is Side.BOTH:
                axis_x = area_x + (area_w * 0.5)
            elif side is Side.SECONDARY:
                axis_x = area_x + (area_w * (1.0 - _AXIS_INSET * 4))
            else:
                axis_x = area_x + (area_w * (_AXIS_INSET * 4))
            axis_origin = (axis_x, axis_top)
            axis_length = axis_bottom - axis_top
            axis_end = (axis_x, axis_bottom)

        # 4) Date → axis-position mapping. Linear over the project range.
        total_days = max(1, (end - start).days)

        def pos_for_day(day: arrow.Arrow) -> float:
            offset = (day - start).days
            return max(0.0, min(float(offset) / total_days * axis_length, axis_length))

        # 5) Ask labella to place the callouts.
        placements = layout_pit_callouts(
            point_events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            direction=direction,
            side=side,
            config=config,
            pos_for_day=pos_for_day,
        )

        # 6) Load DB icon cache (best-effort) and draw the SVG.
        #    Order:
        #      - <g class="ec-pit-axis-group"> axis + (future ticks)
        #      - today line (above axis, below callouts)
        #      - one <g class="ec-pit-callout-group ec-pit-side-…"
        #            data-…> per event, holding its leader, marker,
        #        label box, label texts, and date label.
        self._load_icon_svg_cache(db)
        self._draw_axis_group(config, axis_origin, axis_end)
        if config.pit_show_today_line:
            self._draw_today_line(
                config, start, end, axis_origin, axis_end, direction,
                pos_for_day,
            )
        self._draw_callout_groups(config, placements, direction, side)

        return 0, []

    # ------------------------------------------------------------------
    # Draw helpers
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # SVG <marker> defs (arrow-head etc.) — independent start/end per line
    # ------------------------------------------------------------------
    def _ensure_marker_def(
        self,
        kind: str,
        color: str,
        size: float,
    ) -> str | None:
        """Inject (once) and return the id of a built-in SVG marker.

        Args:
            kind: "arrow-head" or "none". Anything else degrades to a
                no-op return.
            color: Fill color for the marker glyph.
            size: ``markerWidth`` / ``markerHeight`` in user units.

        Returns:
            The fragment id (without the leading ``#``) suitable for
            embedding in a ``marker-start="url(#…)"`` attribute, or
            ``None`` when ``kind`` is "none" / unknown / size <= 0.
        """
        if not kind or kind == "none" or size <= 0:
            return None
        key = (kind, color, round(float(size), 3))
        existing = self._pit_marker_ids.get(key)
        if existing:
            return existing
        # Slugify color for the id. Hex stays as is sans '#'; non-hex
        # gets a quick alphanumeric squeeze.
        slug = "".join(ch for ch in color if ch.isalnum()) or "c"
        size_slug = str(round(size, 2)).replace(".", "_")
        marker_id = f"pit-marker-{kind}-{slug}-{size_slug}"

        if kind == "arrow-head":
            # An equilateral-ish triangle whose tip sits at refX/refY so
            # the line endpoint coincides with the tip.
            s = float(size)
            inner = (
                f'<marker id="{marker_id}" markerUnits="userSpaceOnUse" '
                f'viewBox="0 0 {s} {s}" '
                f'markerWidth="{s}" markerHeight="{s}" '
                f'refX="{s}" refY="{s/2}" orient="auto" '
                f'class="ec-pit-marker-arrow-head">'
                f'<path d="M 0 0 L {s} {s/2} L 0 {s} Z" '
                f'fill="{color}" stroke="none"/>'
                f'</marker>'
            )
            self._drawing.append_def(drawsvg.Raw(inner))
            self._pit_marker_ids[key] = marker_id
            return marker_id

        return None

    @staticmethod
    def _marker_attr_pair(kind: str, color: str, size: float) -> str:
        """Return the leading-space attribute fragment for a non-empty
        marker (or "" when none should be drawn).

        The caller chooses which attribute (``marker-start`` /
        ``marker-end``) the fragment is prefixed with via ``ensure``.
        """
        # Intentional no-op — kept as the seam tests can monkey-patch
        # when they want to assert "marker emitted nothing".
        return f' fill="{color}" size="{size}" kind="{kind}"'

    def _draw_axis_group(
        self,
        config: "CalendarConfig",
        axis_origin: tuple[float, float],
        axis_end: tuple[float, float],
    ) -> None:
        """Wrap the axis line (and future ticks) in ec-pit-axis-group."""
        self._drawing.append(drawsvg.Raw('<g class="ec-pit-axis-group">'))
        self._draw_axis(config, axis_origin, axis_end)
        self._drawing.append(drawsvg.Raw('</g>'))

    def _draw_callout_groups(
        self,
        config: "CalendarConfig",
        placements: list[PITPlacement],
        direction: Orientation,
        side_config: Side,
    ) -> None:
        """Emit one <g class="ec-pit-callout-group ec-pit-side-…"
        data-…> per placement containing its leader, marker, box, label
        text(s), and the opposite-side date label.
        """
        if not placements:
            return

        # Pre-compute shared styling values once.
        leader_color = config.theme_pit_leader_color or "#555555"
        leader_width = float(config.pit_leader_stroke_width)
        leader_opacity = float(config.pit_leader_stroke_opacity)
        leader_dasharray = config.pit_leader_stroke_dasharray
        leader_linecap = config.pit_leader_stroke_linecap
        leader_linejoin = config.pit_leader_stroke_linejoin
        leader_arrow_color = config.theme_pit_arrow_head_color or leader_color
        ms_id = self._ensure_marker_def(
            config.pit_leader_marker_start, leader_arrow_color,
            float(config.pit_leader_marker_start_size),
        )
        me_id = self._ensure_marker_def(
            config.pit_leader_marker_end, leader_arrow_color,
            float(config.pit_leader_marker_end_size),
        )
        ms_attr = f' marker-start="url(#{ms_id})"' if ms_id else ""
        me_attr = f' marker-end="url(#{me_id})"' if me_id else ""
        dash_attr = (
            f' stroke-dasharray="{leader_dasharray}"' if leader_dasharray else ""
        )

        # Marker defaults
        dot_color_default = config.theme_pit_dot_color or "#2d5fae"
        ms_color_default = config.theme_pit_milestone_color or "#c0392b"
        marker_size = float(config.pit_marker_size)
        dot_size = float(config.pit_dot_radius) * 2.0
        icon_map = getattr(self, "_icon_svg_map", {}) or {}

        # Label-box style
        label_stroke = config.theme_pit_label_stroke_color or "#444444"
        label_sw = float(config.pit_label_stroke_width)
        label_rx = float(config.pit_label_corner_radius)
        label_fill_color = config.theme_pit_label_fill_color or "none"
        label_fill_opacity = float(config.pit_label_fill_opacity)

        # Label text fonts
        name_font = (
            config.pit_name_text_font_name
            or config.timeline_name_text_font_name
            or "Roboto-Bold"
        )
        notes_font = (
            config.pit_notes_text_font_name
            or config.timeline_notes_text_font_name
            or "Roboto-Regular"
        )
        name_size = float(config.pit_name_text_font_size or 11.0)
        notes_size = float(config.pit_notes_text_font_size or name_size * 0.85)
        name_color = config.theme_pit_label_text_color or "#1b1f24"
        notes_color = config.theme_pit_label_text_color or "#5a6470"
        pad_x = float(config.pit_label_padding_x)
        pad_y = float(config.pit_label_padding_y)
        show_notes = bool(getattr(config, "includenotes", False))

        # Date-label style
        date_color = config.theme_pit_date_text_color or "#444444"
        date_font = (
            config.theme_pit_date_text_font_name
            or config.pit_name_text_font_name
            or "Roboto-Regular"
        )
        date_size = float(
            config.theme_pit_date_text_font_size or (name_size * 0.85)
        )
        date_offset = float(config.pit_date_text_offset)
        date_fmt = config.pit_date_format

        for p in placements:
            ev = p.event
            side_class = (
                "ec-pit-side-primary" if p.side is Side.PRIMARY
                else "ec-pit-side-secondary"
            )
            groups_attr = ev.resource_group or ""
            # Open the per-event group with data-* attrs.
            self._drawing.append(drawsvg.Raw(
                f'<g class="ec-pit-callout-group {side_class}" '
                f'data-event-date="{ev.start}" '
                f'data-milestone="{str(bool(ev.milestone)).lower()}" '
                f'data-priority="{int(ev.priority or 0)}" '
                f'data-groups="{_xml_escape(groups_attr)}">'
            ))

            # Leader (axis-local path inside a translate() group).
            ox, oy = p.axis_origin
            if p.leader_path_d:
                self._drawing.append(drawsvg.Raw(
                    f'<g transform="translate({ox:.2f},{oy:.2f})" '
                    f'class="ec-callout-leader">'
                    f'<path d="{p.leader_path_d}" '
                    f'stroke="{leader_color}" stroke-width="{leader_width:.3f}" '
                    f'stroke-opacity="{leader_opacity}" '
                    f'stroke-linecap="{leader_linecap}" '
                    f'stroke-linejoin="{leader_linejoin}" '
                    f'fill="none"{dash_attr}{ms_attr}{me_attr}/>'
                    f'</g>'
                ))

            # Marker.
            spec = resolve_marker(ev, config=config, icon_svg_map=icon_map)
            base_color = ms_color_default if ev.milestone else dot_color_default
            color = ev.color or base_color
            if spec.is_icon:
                m_size = marker_size
            elif spec.shape == "circle" and not ev.milestone:
                m_size = dot_size
            else:
                m_size = marker_size
            draw_marker(
                self._drawing, spec, p.x_dot, p.y_dot,
                size=m_size, color=color,
                strip_svg_wrapper=self._strip_svg_wrapper,
            )

            # Label box.
            self._draw_rect(
                p.x_label, p.y_label, p.label_w, p.label_h,
                fill=label_fill_color,
                stroke=label_stroke,
                fill_opacity=label_fill_opacity,
                stroke_width=label_sw,
                rx=label_rx,
                css_class="ec-callout-box",
            )

            # Label text — name + (optional) notes.
            tx = p.x_label + pad_x
            ty = p.y_label + pad_y + name_size
            self._draw_text(
                tx, ty, ev.task_name, name_font, name_size,
                fill=name_color,
                anchor="start",
                max_width=max(8.0, p.label_w - 2 * pad_x),
                css_class="ec-event-name",
            )
            if show_notes and ev.notes:
                ny = ty + notes_size * 1.2
                self._draw_text(
                    tx, ny, ev.notes, notes_font, notes_size,
                    fill=notes_color,
                    anchor="start",
                    max_width=max(8.0, p.label_w - 2 * pad_x),
                    css_class="ec-event-notes",
                )

            # Date on the opposite side of the axis from the label,
            # anchored at the marker (not the displaced label).
            date_side = opposite(p.side)
            try:
                day = arrow.get(ev.start, "YYYYMMDD")
                date_text = format_arrow_date(day, date_fmt)
            except Exception:
                date_text = ""
            if date_text:
                if direction is Orientation.HORIZONTAL:
                    if date_side is Side.PRIMARY:
                        dx, dy = p.x_dot, p.y_dot - date_offset
                    else:
                        dx, dy = p.x_dot, p.y_dot + date_offset + date_size
                    anchor = "middle"
                else:
                    if date_side is Side.PRIMARY:
                        dx = p.x_dot + date_offset
                        dy = p.y_dot + date_size * 0.35
                        anchor = "start"
                    else:
                        dx = p.x_dot - date_offset
                        dy = p.y_dot + date_size * 0.35
                        anchor = "end"
                self._draw_text(
                    dx, dy, date_text, date_font, date_size,
                    fill=date_color,
                    anchor=anchor,
                    css_class="ec-event-date",
                )

            self._drawing.append(drawsvg.Raw('</g>'))

    def _draw_axis(
        self,
        config: "CalendarConfig",
        axis_origin: tuple[float, float],
        axis_end: tuple[float, float],
    ) -> None:
        """Draw the main axis line, with optional marker-start/end."""
        color = config.theme_pit_axis_color or "#333333"
        width = float(config.pit_axis_stroke_width)
        arrow_color = config.theme_pit_arrow_head_color or color

        ms_id = self._ensure_marker_def(
            config.pit_axis_marker_start, arrow_color,
            float(config.pit_axis_marker_start_size),
        )
        me_id = self._ensure_marker_def(
            config.pit_axis_marker_end, arrow_color,
            float(config.pit_axis_marker_end_size),
        )
        ms_attr = f' marker-start="url(#{ms_id})"' if ms_id else ""
        me_attr = f' marker-end="url(#{me_id})"' if me_id else ""

        self._drawing.append(drawsvg.Raw(
            f'<line x1="{axis_origin[0]:.2f}" y1="{axis_origin[1]:.2f}" '
            f'x2="{axis_end[0]:.2f}" y2="{axis_end[1]:.2f}" '
            f'stroke="{color}" stroke-width="{width:.3f}" '
            f'class="ec-axis-line"{ms_attr}{me_attr}/>'
        ))

    def _draw_today_line(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_origin: tuple[float, float],
        axis_end: tuple[float, float],
        direction: Orientation,
        pos_for_day,
    ) -> None:
        """Draw a perpendicular "today" line at the configured as-of date.

        Honors ``pit_today_date`` for forward-dated presentations. All
        stroke attributes are themeable; an optional label is drawn on
        a configurable side.
        """
        # Resolve the "today" date — config override beats the wall clock.
        today_arrow: arrow.Arrow
        if config.pit_today_date:
            try:
                today_arrow = arrow.get(str(config.pit_today_date), "YYYYMMDD")
            except (arrow.ParserError, ValueError):
                today_arrow = arrow.now().floor("day")
        else:
            today_arrow = arrow.now().floor("day")
        # Bail if outside the project range.
        if today_arrow < start or today_arrow > end:
            return

        pos = pos_for_day(today_arrow)

        # Today line stroke vocabulary — theme overrides → config defaults.
        color = (
            config.theme_pit_today_line_color
            or getattr(config, "timeline_today_line_color", None)
            or "#c00000"
        )
        width = float(config.theme_pit_today_line_width or 1.0)
        opacity = float(config.theme_pit_today_line_opacity or 0.85)
        dasharray = (
            config.theme_pit_today_line_dasharray
            or config.pit_leader_stroke_dasharray
            or "4,2"
        )
        linecap = config.theme_pit_today_line_linecap or "round"
        linejoin = config.theme_pit_today_line_linejoin or "round"

        # Geometry — perpendicular to the axis.
        ox, oy = axis_origin
        ex, ey = axis_end
        if direction is Orientation.HORIZONTAL:
            x = ox + pos
            # Half the axis-perp clearance — use the page-area band as
            # an approximation. For MVP we extend by ±32 points.
            line_x1, line_y1 = x, oy - 32
            line_x2, line_y2 = x, oy + 32
            label_anchor = "middle"
            # Label position controls which side of the axis the text sits.
            label_pos = config.theme_pit_today_line_label_position or "end"
            if label_pos == "start":
                label_x, label_y = x, line_y1 - 2
            elif label_pos == "middle":
                label_x, label_y = x, oy - 4
            else:
                label_x, label_y = x, line_y2 + 10
        else:
            y = oy + pos
            line_x1, line_y1 = ox - 32, y
            line_x2, line_y2 = ox + 32, y
            label_anchor = "start"
            label_pos = config.theme_pit_today_line_label_position or "end"
            if label_pos == "start":
                label_x, label_y = line_x1 - 4, y + 3
                label_anchor = "end"
            elif label_pos == "middle":
                label_x, label_y = ox + 4, y - 3
            else:
                label_x, label_y = line_x2 + 4, y + 3

        # marker-start / marker-end (independent, per v5).
        arrow_color = config.theme_pit_arrow_head_color or color
        ms_id = self._ensure_marker_def(
            config.pit_today_line_marker_start, arrow_color,
            float(config.pit_today_line_marker_start_size),
        )
        me_id = self._ensure_marker_def(
            config.pit_today_line_marker_end, arrow_color,
            float(config.pit_today_line_marker_end_size),
        )
        ms_attr = f' marker-start="url(#{ms_id})"' if ms_id else ""
        me_attr = f' marker-end="url(#{me_id})"' if me_id else ""
        dash_attr = f' stroke-dasharray="{dasharray}"' if dasharray else ""

        self._drawing.append(drawsvg.Raw(
            f'<line x1="{line_x1:.2f}" y1="{line_y1:.2f}" '
            f'x2="{line_x2:.2f}" y2="{line_y2:.2f}" '
            f'stroke="{color}" stroke-width="{width:.3f}" '
            f'stroke-opacity="{opacity}" '
            f'stroke-linecap="{linecap}" stroke-linejoin="{linejoin}" '
            f'class="ec-today-line"{dash_attr}{ms_attr}{me_attr}/>'
        ))

        # Today-line label — empty string suppresses.
        label_text = config.pit_today_line_label or ""
        if label_text:
            label_color = config.theme_pit_today_line_label_color or color
            label_font = (
                config.theme_pit_today_line_label_font_name
                or config.pit_name_text_font_name
                or "Roboto-Bold"
            )
            label_size = float(
                config.theme_pit_today_line_label_font_size
                or (float(config.pit_name_text_font_size or 11.0) * 0.85)
            )
            self._draw_text(
                label_x, label_y, label_text, label_font, label_size,
                fill=label_color,
                anchor=label_anchor,
                css_class="ec-today-label",
            )

