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

from config import role_styles
from config.role_styles import role_text
from renderers.lines import draw_line
from renderers.svg_base import BaseSVGRenderer
from renderers.timescale import ScaleContext, draw_axis_beside, draw_axis_edges, plan_axis_scale
from renderers.today_line import draw_today
from shared.callouts import evaluate_callout_style, leader_ends, leader_style
from shared.data_models import Event
from shared.date_utils import format_arrow_date
from shared.orientation import Orientation, Side, opposite
from shared.palettes import resolve_palette
from shared.rule_engine import StyleEngine, StyleResult
from shared.span import Frame
from visualizers.pit.labella_adapter import (
    PITPlacement,
    layout_pit_callouts,
)
from visualizers.pit.markers import (
    draw_label_icon,
    draw_marker,
    resolve_label_icon,
    resolve_marker,
)

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
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _pit_style_rules(config: CalendarConfig) -> list:
    """The theme's conditional style rules, for the StyleEngine."""
    return role_styles.style_rules(config.theme_v3)


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
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list]:
        """Render the PIT axis + callouts. Returns (overflow_count, [])."""
        self._adopt_theme_roles(config)
        # Reset per-render state.
        self._pit_marker_ids = {}
        # Reset SVG pattern dedup caches (mirrors weekly renderer pattern).
        self._pattern_svg_cache: dict[str, str] = {}
        self._registered_pattern_ids: set[str] = set()
        area_x, area_y, area_w, area_h = coordinates.get("PITArea", (0.0, 0.0, config.pageX, config.pageY))

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
        from renderers.details_record import KIND_MULTI_DAY_SKIPPED

        for skipped in event_objs:
            if skipped.is_duration:
                self._note_exception(
                    KIND_MULTI_DAY_SKIPPED,
                    skipped.task_name or "",
                    str(skipped.start)[:8],
                    start=str(skipped.start)[:8],
                    end=str(skipped.end)[:8],
                    detail="use the timeline visualizer for durations",
                    event=skipped,
                )
        if dropped:
            import logging

            logging.getLogger(__name__).info(
                "PIT: skipped %d multi-day events (use the timeline visualizer for durations)",
                dropped,
            )

        # 3) Compute axis geometry.
        direction = Orientation(config.theme_v3.timescale.axis.orientation)
        side = Side(config.theme_v3.pit.label_side)

        # The theme's timescale, planned for this axis: rows beside the axis (ticks,
        # holiday marks) and bands at the outer edges, which the axis makes room for.
        theme = config.theme_v3
        if direction is Orientation.HORIZONTAL:
            along0, along1 = area_x + (area_w * _AXIS_INSET), area_x + (area_w * (1.0 - _AXIS_INSET))
        else:
            along0, along1 = area_y + (area_h * _AXIS_INSET), area_y + (area_h * (1.0 - _AXIS_INSET))
        scale_frame = Frame.over_range(direction, start, end, along0, along1, 0.0)
        scale = plan_axis_scale(theme, scale_frame.span, ScaleContext(theme, config, db, event_objs))
        edge_low, edge_high = scale.edge_low(scale_frame), scale.edge_high(scale_frame)

        if direction is Orientation.HORIZONTAL:
            axis_left, axis_right = along0, along1
            axis_y = area_y + edge_low + ((area_h - edge_low - edge_high) * 0.5)  # mid-band horizontally
            axis_origin = (axis_left, axis_y)
            axis_length = axis_right - axis_left
            axis_end = (axis_right, axis_y)
        else:
            axis_top, axis_bottom = along0, along1
            inner_x, inner_w = area_x + edge_low, area_w - edge_low - edge_high
            # Center the vertical axis when labels are on both sides;
            # bias to one side otherwise so the labels have room.
            if side is Side.BOTH:
                axis_x = inner_x + (inner_w * 0.5)
            elif side is Side.SECONDARY:
                axis_x = inner_x + (inner_w * (1.0 - _AXIS_INSET * 4))
            else:
                axis_x = inner_x + (inner_w * (_AXIS_INSET * 4))
            axis_origin = (axis_x, axis_top)
            axis_length = axis_bottom - axis_top
            axis_end = (axis_x, axis_bottom)

        # 4) Date → axis-position mapping: every day of the range owns a cell.
        along0, along1, cross = (
            (axis_origin[0], axis_end[0], axis_origin[1])
            if direction is Orientation.HORIZONTAL
            else (axis_origin[1], axis_end[1], axis_origin[0])
        )
        frame = Frame.over_range(direction, start, end, along0, along1, cross)
        local_span = Frame.over_range(direction, start, end, 0.0, axis_length, 0.0).span

        def pos_for_day(day: arrow.Arrow) -> float:
            return local_span.center(day.date())

        # 5) Load DB caches (icons + patterns) and build StyleEngine BEFORE
        #    layout, so the label-box icon width can be reserved per event.
        self._load_icon_svg_cache(db)
        self._db = db  # stash for palette lookups in _draw_callout_groups
        try:
            self._pattern_svg_cache = db.get_all_patterns()
        except Exception:
            self._pattern_svg_cache = {}

        style_engine = StyleEngine(_pit_style_rules(config))
        icon_map = getattr(self, "_icon_svg_map", {}) or {}

        # Pre-resolve per-event style + label-icon presence so the layout
        # adapter can reserve extra width for events that get a glyph.
        event_styles: dict[int, StyleResult] = {}
        event_icon_svgs: dict[int, str | None] = {}
        for ev in point_events:
            sr = evaluate_callout_style(style_engine, ev)
            event_styles[id(ev)] = sr
            event_icon_svgs[id(ev)] = resolve_label_icon(
                ev,
                config=config,
                icon_svg_map=icon_map,
                style_result=sr,
            )

        # Label-icon geometry constants used both here and in the draw pass.
        label_icon_size = float(config.theme_v3.pit.label.icon_size or role_text(config, "event_name").size)
        label_icon_gap = float(config.theme_v3.pit.label.icon_gap or 0.0)
        icon_extra = label_icon_size + label_icon_gap

        def _extra_width_for_event(ev: Event) -> float:
            return icon_extra if event_icon_svgs.get(id(ev)) else 0.0

        # 6) Ask labella to place the callouts, with reserved icon space.
        placements = layout_pit_callouts(
            point_events,
            axis_origin=axis_origin,
            axis_length=axis_length,
            direction=direction,
            side=side,
            config=config,
            pos_for_day=pos_for_day,
            extra_width_for_event=_extra_width_for_event,
            min_layer_gap=scale.beside_height(*((Side.PRIMARY, Side.SECONDARY) if side is Side.BOTH else (side,))),
        )

        # Map placement index → StyleResult so callout drawing can read it.
        per_event_styles: dict[int, StyleResult] = {
            i: event_styles.get(id(p.event), StyleResult()) for i, p in enumerate(placements)
        }
        # Same mapping for the pre-resolved label-icon SVG (or None).
        per_event_label_icons: dict[int, str | None] = {
            i: event_icon_svgs.get(id(p.event)) for i, p in enumerate(placements)
        }
        # Stash on self so _draw_callout_groups can read them without an
        # extra parameter (matches the existing per_event_styles pattern).
        self._pit_label_icons = per_event_label_icons
        self._pit_label_icon_size = label_icon_size
        self._pit_label_icon_gap = label_icon_gap

        # Draw:
        #   - <g class="ec-pit-axis-group"> axis + ticks
        #   - today line (above axis, below callouts)
        #   - per-event callout groups
        self.drawing.append(drawsvg.Raw('<g class="ec-pit-axis-group">'))
        draw_axis_beside(self, theme, scale, frame)
        self._draw_axis(config, axis_origin, axis_end)
        self.drawing.append(drawsvg.Raw("</g>"))
        if direction is Orientation.HORIZONTAL:
            draw_axis_edges(self, scale, frame, area_y, area_y + area_h)
        else:
            draw_axis_edges(self, scale, frame, area_x, area_x + area_w)
        if direction is Orientation.HORIZONTAL:
            draw_today(self, config.theme_v3, frame, area_y, area_y + area_h)
        else:
            draw_today(self, config.theme_v3, frame, area_x, area_x + area_w)
        self._draw_callout_groups(config, placements, direction, per_event_styles)

        return 0, []

    # ------------------------------------------------------------------
    # Draw helpers
    # ------------------------------------------------------------------
    # SVG <marker> defs (arrow-head etc.) — independent start/end per line
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Axis ticks (timeband segments → perpendicular marks + labels)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Label fill resolution
    # ------------------------------------------------------------------
    def _resolve_label_fill(
        self,
        config: CalendarConfig,
        event_index: int,
        side: Side,
        label_override: dict | None,
    ) -> tuple[str, float]:
        """Return (fill_color, fill_opacity) for a label box.

        Precedence:
          1. per-rule label_override["fill_color"] / ["fill_opacity"]
          2. per-side theme_pit_label_{primary|secondary}_fill_color (not in
             config yet — reserved for future theme decomposition; skipped)
          3. theme_pit_label_fill_color
          4. theme_pit_label_palette (round-robin by chronological index)
          5. module default: ("none", 0.0)
        """
        box = config.theme_v3.boxes.callout
        # 1) Per-rule override.
        if label_override:
            fc = label_override.get("fill_color")
            fo = label_override.get("fill_opacity")
            if fc is not None:
                return str(fc), float(fo) if fo is not None else float(box.fill_opacity)

        # 2) The callout box's palette, round-robin by chronological index.
        if self._label_palette:
            return str(self._label_palette[event_index % len(self._label_palette)]), float(box.fill_opacity)

        # 3) The callout box's own fill.
        return box.fill, float(box.fill_opacity)

    def _draw_callout_groups(
        self,
        config: CalendarConfig,
        placements: list[PITPlacement],
        direction: Orientation,
        per_event_styles: dict[int, StyleResult] | None = None,
    ) -> None:
        """Emit one <g class="ec-pit-callout-group ec-pit-side-…"
        data-…> per placement containing its leader, marker, box, label
        text(s), and the opposite-side date label.
        """
        if not placements:
            return

        per_event_styles = per_event_styles or {}

        self._label_palette = resolve_palette(config.theme_v3.boxes.callout.fill_palette, self._db)

        theme = config.theme_v3
        callout = theme.boxes.callout
        dot_color_default = theme.icons.event.color
        ms_color_default = theme.icons.milestone.color
        marker_size = float(theme.timescale.axis.marker_size)
        dot_size = float(theme.events.marker.radius) * 2.0

        # Label-box defaults (per-rule can override)
        default_label_stroke = callout.stroke
        default_label_sw = float(callout.stroke_width)
        default_label_rx = float(callout.corner_radius)
        default_label_pattern = callout.pattern
        default_label_pattern_opacity = float(callout.pattern_opacity)

        name = role_text(config, "event_name")
        notes = role_text(config, "event_notes")
        date = role_text(config, "event_date")
        name_font, notes_font = name.font, notes.font
        name_size, notes_size = name.size, notes.size
        name_color, notes_color = name.color, notes.color
        pad_x = float(config.theme_v3.pit.label.padding_x)
        pad_y = float(config.theme_v3.pit.label.padding_y)
        show_notes = bool(config.include_notes)

        # Date-label style
        date_color, date_font, date_size = date.color, date.font, date.size
        date_offset = float(config.theme_v3.pit.date_offset)
        date_fmt = theme.events.date.format
        date_placement = config.theme_v3.pit.date_placement

        for i, p in enumerate(placements):
            ev = p.event
            sr: StyleResult = per_event_styles.get(i, StyleResult())
            leader_ovr: dict = sr.leader_override or {}
            label_ovr: dict = sr.label_override or {}

            side_class = "ec-pit-side-primary" if p.side is Side.PRIMARY else "ec-pit-side-secondary"
            groups_attr = ev.resource_group or ""
            # Open the per-event group with data-* attrs.
            self.drawing.append(
                drawsvg.Raw(
                    f'<g class="ec-pit-callout-group {side_class}" '
                    f'data-event-date="{ev.start}" '
                    f'data-milestone="{str(bool(ev.milestone)).lower()}" '
                    f'data-priority="{int(ev.priority or 0)}" '
                    f'data-groups="{_xml_escape(groups_attr)}">'
                )
            )

            # Leader: dot to label box, styled by lines.leader (+ side colour, + rule override).
            ends = leader_ends((p.x_dot, p.y_dot), (p.x_label, p.y_label, p.label_w, p.label_h), p.side, direction)
            draw_line(
                self,
                leader_style(config.theme_v3, p.side, leader_ovr),
                ends.start,
                ends.end,
                start_heading=ends.start_heading,
                end_heading=ends.end_heading,
                css_class="ec-callout-leader",
            )

            # Axis marker — always a built-in shape (circle for events,
            # diamond for milestones). DB icons are drawn inside the
            # label box instead (see further below).
            spec = resolve_marker(ev)
            base_color = ms_color_default if ev.milestone else dot_color_default
            color = sr.fill_color or ev.color or base_color
            m_size = marker_size if ev.milestone else dot_size
            draw_marker(
                self._drawing,
                spec,
                p.x_dot,
                p.y_dot,
                size=m_size,
                color=color,
            )
            note = self._details_note(ev)
            if note is not None:
                note.assigned_color = color
                note.color_source = "style rule" if sr.fill_color else ("event color" if ev.color else "theme")
            with self._event_scope(ev):
                self._note_mark("diamond" if ev.milestone else "dot", color, "milestone" if ev.milestone else "event")

            # Resolve label-box style (per-rule > global theme > defaults).
            eff_label_stroke = label_ovr.get("stroke_color") or default_label_stroke
            eff_label_sw = float(label_ovr.get("stroke_width") or default_label_sw)
            eff_label_rx = float(label_ovr.get("corner_radius") or default_label_rx)
            eff_label_text_color = label_ovr.get("text_color") or name_color
            eff_label_notes_color = label_ovr.get("text_color") or notes_color
            eff_pad_x = float(label_ovr.get("padding_x") or pad_x)
            eff_pad_y = float(label_ovr.get("padding_y") or pad_y)
            # Fill with precedence chain (per-rule > theme color > palette).
            eff_fill, eff_fill_opacity = self._resolve_label_fill(config, i, p.side, label_ovr if label_ovr else None)
            # Pattern fill (per-rule > global theme default).
            eff_pattern = label_ovr.get("pattern") or default_label_pattern
            eff_pattern_opacity = float(label_ovr.get("pattern_opacity") or default_label_pattern_opacity)

            # Label box — draw rect first, then optional pattern overlay.
            self._draw_rect(
                p.x_label,
                p.y_label,
                p.label_w,
                p.label_h,
                fill=eff_fill,
                stroke=eff_label_stroke,
                fill_opacity=eff_fill_opacity,
                stroke_width=eff_label_sw,
                rx=eff_label_rx,
                css_class="ec-callout-box",
            )
            if eff_pattern:
                pat_id = self._ensure_svg_pattern_def(eff_pattern, eff_label_stroke, config)
                if pat_id:
                    self.drawing.append(
                        drawsvg.Raw(
                            f'<rect x="{p.x_label:.2f}" y="{p.y_label:.2f}" '
                            f'width="{p.label_w:.2f}" height="{p.label_h:.2f}" '
                            f'fill="url(#{pat_id})" '
                            f'fill-opacity="{eff_pattern_opacity}" '
                            f'rx="{eff_label_rx:.2f}" stroke="none" '
                            f'class="ec-pit-label-pattern"/>'
                        )
                    )

            # Label text — name, optional notes, then the inline date.
            tx = p.x_label + eff_pad_x
            ty = p.y_label + eff_pad_y + name_size
            text_max_w = max(8.0, p.label_w - 2 * eff_pad_x)

            # Resolve the (pre-computed) label-box icon for this event.
            # When present, draw it on the same baseline as the name and
            # shift the name's starting x to the right by icon + gap.
            label_icon_svg = (getattr(self, "_pit_label_icons", {}) or {}).get(i)
            label_icon_sz = float(getattr(self, "_pit_label_icon_size", 0.0) or 0.0)
            label_icon_gp = float(getattr(self, "_pit_label_icon_gap", 0.0) or 0.0)
            name_tx = tx
            if label_icon_svg and label_icon_sz > 0:
                # Vertical center of the name's cap-height row (visually).
                icon_y_center = ty - name_size * 0.35
                draw_label_icon(
                    self._drawing,
                    label_icon_svg,
                    x_left=tx,
                    y_center=icon_y_center,
                    size=label_icon_sz,
                    color=color,
                    strip_svg_wrapper=self._strip_svg_wrapper,
                )
                label_icon_name = (
                    sr.icon
                    or ev.icon
                    or (config.theme_v3.icons.milestone.name if ev.milestone else config.theme_v3.icons.event.name)
                )
                with self._event_scope(ev):
                    self._record_icon(label_icon_name, color, None, "milestone" if ev.milestone else "event")
                # Push the name right so it clears the icon.
                shift = label_icon_sz + label_icon_gp
                name_tx = tx + shift
                # Keep the *name* text from being clipped by the icon.
                name_max_w = max(8.0, text_max_w - shift)
            else:
                name_max_w = text_max_w

            self._draw_text(
                name_tx,
                ty,
                ev.task_name,
                name_font,
                name_size,
                fill=eff_label_text_color,
                anchor="start",
                max_width=name_max_w,
                css_class="ec-event-name",
            )
            line_y = ty
            if show_notes and ev.notes:
                line_y += notes_size * 1.2
                self._draw_text(
                    tx,
                    line_y,
                    ev.notes,
                    notes_font,
                    notes_size,
                    fill=eff_label_notes_color,
                    anchor="start",
                    max_width=text_max_w,
                    css_class="ec-event-notes",
                )

            try:
                day = arrow.get(ev.start, "YYYYMMDD")
                date_text = format_arrow_date(day, date_fmt)
            except Exception:
                date_text = ""

            if date_text and date_placement == "inline":
                # Date as a line inside the box, below name/notes. The box
                # was sized to fit it, so it inherits the boxes' spacing.
                line_y += date_size * 1.2
                self._draw_text(
                    tx,
                    line_y,
                    date_text,
                    date_font,
                    date_size,
                    fill=date_color,
                    anchor="start",
                    max_width=text_max_w,
                    css_class="ec-event-date",
                )
            elif date_text and date_placement == "axis":
                # Date on the opposite side of the axis from the label,
                # anchored at the marker (not the displaced label).
                date_side = opposite(p.side)
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
                    dx,
                    dy,
                    date_text,
                    date_font,
                    date_size,
                    fill=date_color,
                    anchor=anchor,
                    css_class="ec-event-date",
                )

            self.drawing.append(drawsvg.Raw("</g>"))

    def _draw_axis(
        self,
        config: CalendarConfig,
        axis_origin: tuple[float, float],
        axis_end: tuple[float, float],
    ) -> None:
        """Draw the main axis line, styled by ``lines.axis`` (markers included)."""
        draw_line(self, config.theme_v3.lines.axis, axis_origin, axis_end, css_class="ec-axis-line")
