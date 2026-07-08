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

from datetime import date, timedelta
from typing import TYPE_CHECKING

import arrow
import drawsvg

from renderers.svg_base import BaseSVGRenderer
from shared.data_models import Event
from shared.rule_engine import StyleEngine, StyleResult
from shared.timeband import build_segments
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
from shared.date_utils import format_arrow_date
from shared.orientation import Orientation, Side, opposite

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


def _pit_style_rules(config: "CalendarConfig") -> list:
    """Source the raw style_rules list for the PIT StyleEngine.

    Mirrors _timeline_style_rules: prefers the parsed UnifiedTheme so the
    renderer doesn't depend on the legacy theme_style_rules bridge.
    """
    theme = getattr(config, "theme", None)
    if theme is not None:
        rules = theme.sections.get("style_rules")
        if isinstance(rules, list):
            return rules
    return list(getattr(config, "theme_style_rules", None) or [])


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
        # Reset SVG pattern dedup caches (mirrors weekly renderer pattern).
        self._pattern_svg_cache: dict[str, str] = {}
        self._registered_pattern_ids: set[str] = set()
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
            sr = style_engine.evaluate_event(ev)
            event_styles[id(ev)] = sr
            event_icon_svgs[id(ev)] = resolve_label_icon(
                ev, config=config, icon_svg_map=icon_map, style_result=sr,
            )

        # Label-icon geometry constants used both here and in the draw pass.
        label_icon_size = float(
            getattr(config, "pit_label_icon_size", None)
            or (config.pit_name_text_font_size or 11.0)
        )
        label_icon_gap = float(getattr(config, "pit_label_icon_gap", 4.0) or 0.0)
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
        )

        # Map placement index → StyleResult so callout drawing can read it.
        per_event_styles: dict[int, StyleResult] = {
            i: event_styles.get(id(p.event), StyleResult())
            for i, p in enumerate(placements)
        }
        # Same mapping for the pre-resolved label-icon SVG (or None).
        per_event_label_icons: dict[int, str | None] = {
            i: event_icon_svgs.get(id(p.event))
            for i, p in enumerate(placements)
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
        self._draw_axis_group(
            config, axis_origin, axis_end, start, end, direction,
            pos_for_day, db, side,
        )
        if config.pit_show_today_line:
            self._draw_today_line(
                config, start, end, axis_origin, axis_end, direction,
                pos_for_day,
            )
        self._draw_callout_groups(
            config, placements, direction, side, per_event_styles
        )

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
        start: arrow.Arrow,
        end: arrow.Arrow,
        direction: Orientation,
        pos_for_day,
        db: "CalendarDB",
        side: Side = Side.PRIMARY,
    ) -> None:
        """Wrap the axis line and its ticks in ec-pit-axis-group."""
        self._drawing.append(drawsvg.Raw('<g class="ec-pit-axis-group">'))
        if config.pit_show_ticks:
            self._draw_axis_ticks(
                config, start, end, axis_origin, direction, pos_for_day, db,
                side,
            )
        self._draw_axis(config, axis_origin, axis_end)
        self._drawing.append(drawsvg.Raw('</g>'))

    # ------------------------------------------------------------------
    # Axis ticks (timeband segments → perpendicular marks + labels)
    # ------------------------------------------------------------------
    def _pit_tick_bands(self, config: "CalendarConfig") -> list[dict]:
        """Return the list of tick-band dicts to draw on the axis.

        When ``config.pit_ticks`` is set it takes precedence (a single dict is
        normalized to a one-element list); otherwise a single band is
        synthesized from the scalar ``pit_tick_*`` fields for backward
        compatibility.
        """
        raw = getattr(config, "pit_ticks", None)
        if raw:
            bands = [raw] if isinstance(raw, dict) else list(raw)
            return [b for b in bands if isinstance(b, dict)]

        band: dict = {
            "unit": config.pit_tick_unit or "month",
            "interval_days": config.pit_tick_interval,
            "show_labels": config.pit_show_tick_labels,
            "tick_length": config.pit_tick_length,
        }
        if config.pit_tick_label_format:
            band["label_format"] = config.pit_tick_label_format
        return [band]

    def _pit_tick_segments(
        self,
        config: "CalendarConfig",
        band: dict,
        start: arrow.Arrow,
        end: arrow.Arrow,
        db: "CalendarDB",
    ) -> list[tuple[date, date, str]]:
        """Return (start, end_exclusive, label) tick segments for one band.

        Delegates unit handling to shared.timeband.build_segments so PIT
        ticks match every other timeband-driven visualizer. ``year`` is
        handled locally since build_segments has no year unit.

        Label rule (matches the timeline visualizer): when ``label_format``
        (or ``date_format``) is given it is treated as an Arrow *date* format
        applied to each tick's own date — independent of the band unit. This
        lets any unit (including ``interval``) produce dated tick labels like
        "MMM D". A ``prefix`` string, when present, is prepended to the
        formatted date so e.g. ``prefix: "Week of "`` + ``label_format:
        "MM/DD"`` yields "Week of 02/01". When no format is given, the unit's
        own generated label is used (e.g. the running index for ``interval``
        — which also honors ``prefix`` — "Week N" for ``week``, "FY26 Q1" for
        ``fiscal_quarter``).
        """
        start_d = start.floor("day").date()
        end_d = end.floor("day").date()
        unit = str(band.get("unit") or "month").strip().lower()
        label_fmt = band.get("label_format") or band.get("date_format")
        prefix = str(band.get("prefix") or "")

        if unit == "year":
            segs: list[tuple[date, date, str]] = []
            fmt = label_fmt or "YYYY"
            for yr in range(start_d.year, end_d.year + 1):
                seg_start = max(date(yr, 1, 1), start_d)
                seg_end = min(date(yr + 1, 1, 1), end_d + timedelta(days=1))
                if seg_start < seg_end:
                    label = prefix + format_arrow_date(arrow.get(date(yr, 1, 1)), fmt)
                    segs.append((seg_start, seg_end, label))
            return segs

        # Forward the full band so unit-specific keys (interval prefix,
        # start_index, anchor_date, week start, etc.) reach build_segments;
        # it reads only the keys it knows and ignores PIT styling keys.
        seg_band: dict = dict(band)
        seg_band["unit"] = unit
        if "interval_days" not in seg_band and band.get("interval") is not None:
            seg_band["interval_days"] = int(band.get("interval") or 1)

        visible_days: list[date] = []
        d = start_d
        while d <= end_d:
            visible_days.append(d)
            d += timedelta(days=1)

        segments = build_segments(
            seg_band, start_d, end_d, config,
            visible_days=visible_days,
            db=db,
            week_start_default=0,
            fiscal_year_start_month_default=int(
                getattr(config, "blockplan_fiscal_year_start_month", 2) or 2
            ),
        )
        out: list[tuple[date, date, str]] = []
        for s in segments:
            # With a date format, the prefix is prepended here (build_segments
            # only applies prefix to its own index labels). Without a format,
            # the unit's generated label already includes any prefix.
            label = (
                prefix + format_arrow_date(arrow.get(s.start), label_fmt)
                if label_fmt
                else s.label
            )
            out.append((s.start, s.end_exclusive, label))
        return out

    def _draw_axis_ticks(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_origin: tuple[float, float],
        direction: Orientation,
        pos_for_day,
        db: "CalendarDB",
        side: Side = Side.PRIMARY,
    ) -> None:
        """Draw one row of ticks per band, each perpendicular tick at a
        segment boundary with the segment label positioned per the band's
        ``label_align`` (``center`` by default, ``start`` to align with the
        boundary tick, ``end`` with the next boundary).

        By default tick labels are placed on the opposite side of the axis
        from the callout label boxes: for ``Side.SECONDARY`` the boxes occupy
        the below/left side, so the labels flip to above/right; ``Side.PRIMARY``
        and ``Side.BOTH`` keep the default below/left placement. A band may
        override this with ``label_side`` to pin its labels to a specific side
        of the axis regardless of the callout side: ``above``/``below`` for a
        horizontal axis, ``left``/``right`` for a vertical one (``primary`` /
        ``secondary`` work for either orientation).

        A single band reproduces the legacy single-tick behavior; multiple
        bands (via ``config.pit_ticks``) stack additional tick rows, each
        with its own unit, styling, and label offset away from the axis.
        """
        bands = self._pit_tick_bands(config)
        if not bands:
            return

        default_tick_color = (
            config.theme_pit_tick_color
            or config.theme_pit_axis_color
            or "#666666"
        )
        default_tick_len = float(config.pit_tick_length)
        default_show_labels = bool(config.pit_show_tick_labels)
        default_label_size = float(
            config.theme_pit_date_text_font_size
            or (float(config.pit_name_text_font_size or 11.0) * 0.8)
        )
        default_label_font = (
            config.theme_pit_date_text_font_name
            or config.pit_name_text_font_name
            or "Roboto-Regular"
        )
        ox, oy = axis_origin

        # Tick labels go on the opposite side of the axis from the callout
        # boxes. Boxes occupy below/left for SECONDARY, so labels flip to
        # above/right; PRIMARY and BOTH keep the default below/left.
        flip_labels = side is Side.SECONDARY

        def _pos(d: date) -> float:
            return pos_for_day(arrow.Arrow(d.year, d.month, d.day))

        for band in bands:
            segments = self._pit_tick_segments(config, band, start, end, db)
            if not segments:
                continue

            tick_len = float(band.get("tick_length", default_tick_len))
            tick_color = str(band.get("tick_color") or default_tick_color)
            tick_width = float(band.get("tick_width", 1.0))
            _t_op = band.get("tick_opacity")
            tick_opacity = float(_t_op) if _t_op is not None else 1.0
            tick_dash = band.get("tick_dasharray")

            label_size = float(
                band.get("label_font_size") or band.get("font_size") or default_label_size
            )
            label_font = str(band.get("font") or default_label_font)
            label_color = str(
                band.get("label_color") or band.get("font_color") or tick_color
            )
            _l_op = band.get("label_opacity")
            label_opacity = float(_l_op) if _l_op is not None else 1.0
            show_labels = bool(
                band.get("show_labels", default_show_labels)
            ) and len(segments) <= int(band.get("max_label_count", 60))

            # Distance of the label baseline away from the axis (on the label
            # side). Defaults preserve the legacy single-band placement.
            _l_off = band.get("label_offset")
            _l_gap = band.get("label_gap")
            if _l_off is not None:
                label_off = float(_l_off)
            elif _l_gap is not None:
                label_off = tick_len + float(_l_gap)
            elif direction is Orientation.HORIZONTAL:
                label_off = tick_len + label_size
            else:
                label_off = tick_len

            # How the label sits relative to its segment along the axis:
            #   "center" (default) — centered in the span between this tick
            #                        and the next.
            #   "start"            — anchored at this tick (the segment's
            #                        start boundary, e.g. the first of the
            #                        month) so the label aligns with it.
            #   "end"              — anchored at the next boundary.
            # "left"/"right" are accepted as synonyms for start/end.
            label_align = str(band.get("label_align", "center")).strip().lower()
            if label_align in ("left", "top"):
                label_align = "start"
            elif label_align in ("right", "bottom"):
                label_align = "end"

            # Which side of the axis this band's labels sit on. Defaults to
            # the callout-driven side (``flip_labels``); a band can override:
            #   horizontal axis: "above"/"top" vs "below"/"bottom"
            #   vertical axis:   "right" vs "left"
            #   "secondary"/"primary" work for either orientation.
            _side = str(band.get("label_side", "")).strip().lower()
            if _side in ("above", "top", "right", "secondary"):
                band_flip = True
            elif _side in ("below", "bottom", "left", "primary"):
                band_flip = False
            else:
                band_flip = flip_labels

            for seg_start, seg_end, label in segments:
                p0 = _pos(seg_start)
                p1 = _pos(seg_end)
                if direction is Orientation.HORIZONTAL:
                    tx = ox + p0
                    self._draw_line(
                        tx, oy - tick_len, tx, oy + tick_len,
                        stroke=tick_color, stroke_width=tick_width,
                        stroke_opacity=tick_opacity, stroke_dasharray=tick_dash,
                        css_class="ec-axis-tick",
                    )
                    if show_labels and label:
                        if label_align == "start":
                            lx, l_anchor = tx, "start"
                        elif label_align == "end":
                            lx, l_anchor = ox + p1, "end"
                        else:
                            lx, l_anchor = ox + (p0 + p1) / 2.0, "middle"
                        ly = oy - label_off if band_flip else oy + label_off
                        self._draw_text(
                            lx, ly, label,
                            label_font, label_size,
                            fill=label_color, fill_opacity=label_opacity,
                            anchor=l_anchor,
                            css_class="ec-label",
                        )
                else:
                    ty = oy + p0
                    self._draw_line(
                        ox - tick_len, ty, ox + tick_len, ty,
                        stroke=tick_color, stroke_width=tick_width,
                        stroke_opacity=tick_opacity, stroke_dasharray=tick_dash,
                        css_class="ec-axis-tick",
                    )
                    if show_labels and label:
                        if label_align == "start":
                            lpos = p0
                        elif label_align == "end":
                            lpos = p1
                        else:
                            lpos = (p0 + p1) / 2.0
                        ly = oy + lpos + label_size * 0.35
                        if band_flip:
                            lx, l_anchor = ox + label_off + 2.0, "start"
                        else:
                            lx, l_anchor = ox - label_off - 2.0, "end"
                        self._draw_text(
                            lx, ly, label,
                            label_font, label_size,
                            fill=label_color, fill_opacity=label_opacity,
                            anchor=l_anchor,
                            css_class="ec-label",
                        )

    # _ensure_svg_pattern_def() is inherited from BaseSVGRenderer; the
    # pattern string helpers live in renderers/svg_patterns.py.

    # ------------------------------------------------------------------
    # Label fill resolution
    # ------------------------------------------------------------------
    def _resolve_label_fill(
        self,
        config: "CalendarConfig",
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
        # 1) Per-rule override.
        if label_override:
            fc = label_override.get("fill_color")
            fo = label_override.get("fill_opacity")
            if fc is not None:
                return str(fc), float(fo) if fo is not None else float(config.pit_label_fill_opacity)

        # 3) Global theme fill color.
        if config.theme_pit_label_fill_color:
            return config.theme_pit_label_fill_color, float(config.pit_label_fill_opacity)

        # 4) Palette round-robin.
        palette_name = config.theme_pit_label_palette
        if palette_name:
            palette = self._label_palette_cache.get(palette_name)
            if palette and len(palette) > 0:
                color = palette[event_index % len(palette)]
                return str(color), float(config.pit_label_fill_opacity) or 0.85

        # 5) Default.
        return "none", float(config.pit_label_fill_opacity)

    def _draw_callout_groups(
        self,
        config: "CalendarConfig",
        placements: list[PITPlacement],
        direction: Orientation,
        side_config: Side,
        per_event_styles: dict[int, StyleResult] | None = None,
    ) -> None:
        """Emit one <g class="ec-pit-callout-group ec-pit-side-…"
        data-…> per placement containing its leader, marker, box, label
        text(s), and the opposite-side date label.
        """
        if not placements:
            return

        per_event_styles = per_event_styles or {}

        # Build label palette cache for round-robin fill resolution.
        self._label_palette_cache: dict[str, list] = {}
        palette_name = config.theme_pit_label_palette
        if palette_name and hasattr(self, "_db") and self._db:
            try:
                palettes = self._db.get_all_palettes()
                if palette_name in palettes:
                    self._label_palette_cache[palette_name] = palettes[palette_name]
            except Exception:
                pass

        # Pre-compute shared (non-per-rule) styling values once.
        # Leader defaults — per-rule overrides are applied inside the loop.
        global_leader_color = config.theme_pit_leader_color or "#555555"
        global_leader_width = float(config.pit_leader_stroke_width)
        global_leader_opacity = float(config.pit_leader_stroke_opacity)
        global_leader_dasharray = config.pit_leader_stroke_dasharray
        global_leader_linecap = config.pit_leader_stroke_linecap
        global_leader_linejoin = config.pit_leader_stroke_linejoin
        leader_arrow_color = config.theme_pit_arrow_head_color or global_leader_color

        # Marker defaults
        dot_color_default = config.theme_pit_dot_color or "#2d5fae"
        ms_color_default = config.theme_pit_milestone_color or "#c0392b"
        marker_size = float(config.pit_marker_size)
        dot_size = float(config.pit_dot_radius) * 2.0

        # Label-box defaults (per-rule can override)
        default_label_stroke = config.theme_pit_label_stroke_color or "#444444"
        default_label_sw = float(config.pit_label_stroke_width)
        default_label_rx = float(config.pit_label_corner_radius)
        default_label_pattern = config.theme_pit_label_pattern
        default_label_pattern_opacity = float(getattr(config, "hash_pattern_opacity", 0.15))

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
        show_notes = bool(config.include_notes)

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
        date_placement = getattr(config, "pit_date_placement", "inline")

        for i, p in enumerate(placements):
            ev = p.event
            sr: StyleResult = per_event_styles.get(i, StyleResult())
            leader_ovr: dict = sr.leader_override or {}
            label_ovr: dict = sr.label_override or {}

            # Per-side leader color override.
            if p.side is Side.PRIMARY:
                side_leader_color = config.theme_pit_leader_primary_color
            else:
                side_leader_color = config.theme_pit_leader_secondary_color

            # Resolve effective leader attributes (per-rule > per-side > global).
            leader_color = (
                leader_ovr.get("color")
                or side_leader_color
                or global_leader_color
            )
            leader_width = float(leader_ovr.get("width") or global_leader_width)
            leader_opacity = float(leader_ovr.get("opacity") or global_leader_opacity)
            leader_dasharray = leader_ovr.get("dasharray") or global_leader_dasharray
            leader_linecap = leader_ovr.get("linecap") or global_leader_linecap
            leader_linejoin = leader_ovr.get("linejoin") or global_leader_linejoin

            # Per-rule leader markers (fall back to global config).
            l_ms_kind = leader_ovr.get("marker_start") or config.pit_leader_marker_start
            l_ms_size = float(leader_ovr.get("marker_start_size") or config.pit_leader_marker_start_size)
            l_me_kind = leader_ovr.get("marker_end") or config.pit_leader_marker_end
            l_me_size = float(leader_ovr.get("marker_end_size") or config.pit_leader_marker_end_size)
            l_arrow_color = leader_ovr.get("arrow_color") or leader_arrow_color

            ms_id = self._ensure_marker_def(l_ms_kind, l_arrow_color, l_ms_size)
            me_id = self._ensure_marker_def(l_me_kind, l_arrow_color, l_me_size)
            ms_attr = f' marker-start="url(#{ms_id})"' if ms_id else ""
            me_attr = f' marker-end="url(#{me_id})"' if me_id else ""
            dash_attr = (
                f' stroke-dasharray="{leader_dasharray}"' if leader_dasharray else ""
            )

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

            # Axis marker — always a built-in shape (circle for events,
            # diamond for milestones). DB icons are drawn inside the
            # label box instead (see further below).
            spec = resolve_marker(ev)
            base_color = ms_color_default if ev.milestone else dot_color_default
            color = ev.color or base_color
            if ev.milestone:
                m_size = marker_size
            else:
                m_size = dot_size
            draw_marker(
                self._drawing, spec, p.x_dot, p.y_dot,
                size=m_size, color=color,
            )

            # Resolve label-box style (per-rule > global theme > defaults).
            eff_label_stroke = label_ovr.get("stroke_color") or default_label_stroke
            eff_label_sw = float(label_ovr.get("stroke_width") or default_label_sw)
            eff_label_rx = float(label_ovr.get("corner_radius") or default_label_rx)
            eff_label_text_color = label_ovr.get("text_color") or name_color
            eff_label_notes_color = label_ovr.get("text_color") or notes_color
            eff_pad_x = float(label_ovr.get("padding_x") or pad_x)
            eff_pad_y = float(label_ovr.get("padding_y") or pad_y)
            # Fill with precedence chain (per-rule > theme color > palette).
            eff_fill, eff_fill_opacity = self._resolve_label_fill(
                config, i, p.side, label_ovr if label_ovr else None
            )
            # Pattern fill (per-rule > global theme default).
            eff_pattern = label_ovr.get("pattern") or default_label_pattern
            eff_pattern_opacity = float(
                label_ovr.get("pattern_opacity") or default_label_pattern_opacity
            )

            # Label box — draw rect first, then optional pattern overlay.
            self._draw_rect(
                p.x_label, p.y_label, p.label_w, p.label_h,
                fill=eff_fill,
                stroke=eff_label_stroke,
                fill_opacity=eff_fill_opacity,
                stroke_width=eff_label_sw,
                rx=eff_label_rx,
                css_class="ec-callout-box",
            )
            if eff_pattern:
                pat_id = self._ensure_svg_pattern_def(eff_pattern, eff_label_stroke)
                if pat_id:
                    self._drawing.append(drawsvg.Raw(
                        f'<rect x="{p.x_label:.2f}" y="{p.y_label:.2f}" '
                        f'width="{p.label_w:.2f}" height="{p.label_h:.2f}" '
                        f'fill="url(#{pat_id})" '
                        f'fill-opacity="{eff_pattern_opacity}" '
                        f'rx="{eff_label_rx:.2f}" stroke="none" '
                        f'class="ec-pit-label-pattern"/>'
                    ))

            # Label text — name, optional notes, then the inline date.
            tx = p.x_label + eff_pad_x
            ty = p.y_label + eff_pad_y + name_size
            text_max_w = max(8.0, p.label_w - 2 * eff_pad_x)

            # Resolve the (pre-computed) label-box icon for this event.
            # When present, draw it on the same baseline as the name and
            # shift the name's starting x to the right by icon + gap.
            label_icon_svg = (
                getattr(self, "_pit_label_icons", {}) or {}
            ).get(i)
            label_icon_sz = float(
                getattr(self, "_pit_label_icon_size", 0.0) or 0.0
            )
            label_icon_gp = float(
                getattr(self, "_pit_label_icon_gap", 0.0) or 0.0
            )
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
                # Push the name right so it clears the icon.
                shift = label_icon_sz + label_icon_gp
                name_tx = tx + shift
                # Keep the *name* text from being clipped by the icon.
                name_max_w = max(8.0, text_max_w - shift)
            else:
                name_max_w = text_max_w

            self._draw_text(
                name_tx, ty, ev.task_name, name_font, name_size,
                fill=eff_label_text_color,
                anchor="start",
                max_width=name_max_w,
                css_class="ec-event-name",
            )
            line_y = ty
            if show_notes and ev.notes:
                line_y += notes_size * 1.2
                self._draw_text(
                    tx, line_y, ev.notes, notes_font, notes_size,
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
                    tx, line_y, date_text, date_font, date_size,
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

