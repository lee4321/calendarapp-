"""
Compact Activities Plan SVG renderer.

Renders a compressed timeline with duration lines above/below a central axis,
milestone flag markers, and an optional legend keyed by resource group color.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import arrow
import drawsvg

from config.config import get_font_path
from renderers.svg_base import BaseSVGRenderer, _is_none_color
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.fiscal_renderer import (
    build_fiscal_period_segments,
    build_fiscal_quarter_segments,
)
from shared.icon_band import compute_icon_band_days

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BandSegment:
    """A labeled segment within a time-band column."""

    start: date
    end_exclusive: date
    label: str


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
        n_bands = len(time_bands)
        band_row_h = float(config.compactplan_band_row_height)
        bands_h = n_bands * band_row_h

        # header_bottom_y / key_top_y are gaps (pts) between the header/key
        # blocks and the nearest duration line or milestone.
        header_gap = float(getattr(config, "compactplan_header_bottom_y", None) or 0.0)
        key_gap = float(getattr(config, "compactplan_key_top_y", None) or 0.0)

        show_legend = bool(config.compactplan_show_legend)

        line_w = float(config.compactplan_duration_line_width)
        flag_h = float(config.compactplan_milestone_flag_height)

        # ------------------------------------------------------------------
        # PHASE 1 — Place duration rows.
        # Axis is fixed at the vertical centre of the content area so that
        # the greedy row-placement algorithm has a stable reference point.
        # ------------------------------------------------------------------
        axis_y = area_y + area_h / 2.0

        # Pre-load icon SVG cache so continuation icons and milestone icons can be drawn.
        self._load_icon_svg_cache(db)

        evt_objects = [Event.from_dict(e) if isinstance(e, dict) else e for e in events]
        group_color_map = self._assign_group_colors(evt_objects, config)
        durations = [e for e in evt_objects if e.is_duration and not e.milestone]
        milestones = [e for e in evt_objects if e.milestone]

        placed = self._place_durations(
            durations, group_color_map, day_x, area_x, area_x + area_w,
            px_per_day, config, axis_y,
        )

        # ------------------------------------------------------------------
        # PHASE 2 — Compute actual content bounds from placed rows and flags.
        # Duration lines are centred on row_y; milestone stems reach up by
        # flag_h from the axis.
        # ------------------------------------------------------------------
        if placed:
            min_content_y = min(p.row_y for p in placed) - line_w / 2.0
            max_content_y = max(p.row_y for p in placed) + line_w / 2.0
        else:
            min_content_y = axis_y
            max_content_y = axis_y

        if milestones:
            min_content_y = min(min_content_y, axis_y - flag_h)
            max_content_y = max(max_content_y, axis_y)

        # ------------------------------------------------------------------
        # PHASE 3 — Float header and key relative to content bounds.
        # Header bottom is header_gap pts above the topmost content edge.
        # Key top is key_gap pts below the bottommost content edge.
        # ------------------------------------------------------------------
        bands_y = min_content_y - header_gap - bands_h
        legend_y = max_content_y + key_gap

        # Background (full area)
        bg = str(config.compactplan_background_color or "").strip().lower()
        if bg not in {"", "none", "transparent"}:
            self._draw_rect(area_x, area_y, area_w, area_h, fill=config.compactplan_background_color, css_class="ec-background")

        # Header bands at computed floating position
        self._draw_bands(
            config, time_bands, band_row_h, area_x, bands_y, area_w, start, end,
            visible_days, px_per_day, n_vis,
            events=evt_objects,
        )

        # Axis (optional)
        if bool(config.compactplan_show_axis):
            self._draw_line(
                area_x, axis_y, area_x + area_w, axis_y,
                stroke=config.compactplan_axis_color,
                stroke_width=config.compactplan_axis_width,
                stroke_dasharray=config.compactplan_axis_dasharray or None,
                stroke_opacity=config.compactplan_axis_opacity,
                css_class="ec-axis-line",
            )

        # Duration lines
        for p in placed:
            self._draw_line(
                p.x1, p.row_y, p.x2, p.row_y,
                stroke=p.color,
                stroke_width=line_w,
                stroke_dasharray=config.compactplan_duration_stroke_dasharray or None,
                stroke_opacity=float(config.compactplan_duration_opacity),
                css_class="ec-duration-bar",
            )

        # Start icons — one unique icon at the left (start-date) end of each duration line.
        # Each duration gets its own icon by index, cycling through the configured list.
        show_dur_icons = bool(config.compactplan_show_duration_icons)
        dur_icon_h = float(config.compactplan_duration_icon_height)
        dur_icon_color_cfg = str(config.compactplan_duration_icon_color or "").strip()
        if show_dur_icons and dur_icon_h > 0:
            for p in placed:
                if p.icon_name:
                    # Centre icon vertically on the duration row (same formula as
                    # continuation icons: baseline = row_y + 0.3 * icon_h).
                    icon_baseline = p.row_y + 0.3 * dur_icon_h
                    icon_color = dur_icon_color_cfg if dur_icon_color_cfg else p.color
                    self._draw_icon_svg(
                        p.icon_name, p.x1, icon_baseline, dur_icon_h,
                        anchor="start", color=icon_color,
                        css_class="ec-duration-icon",
                    )

        # Continuation icons — drawn at the clamped right edge of any duration
        # line whose event extends beyond the timeline end date.
        show_continuation = bool(config.compactplan_show_continuation_icon)
        has_continuations = any(p.continues for p in placed)
        if show_continuation and has_continuations:
            cont_icon_name = str(config.compactplan_continuation_icon or "arrow-right")
            cont_icon_h = float(config.compactplan_continuation_icon_height or 8.0)
            cont_icon_color_cfg = (config.compactplan_continuation_icon_color or "").strip()
            for p in placed:
                if p.continues:
                    # Use configured color if set, otherwise inherit the line color.
                    icon_color = cont_icon_color_cfg if cont_icon_color_cfg else p.color
                    # Center icon vertically on the duration row.
                    # _draw_icon_svg places top at baseline_y - 0.8*size, so:
                    #   center = baseline_y - 0.8*h + h/2 = baseline_y - 0.3*h
                    # Solving for center == row_y: baseline_y = row_y + 0.3 * h
                    icon_baseline = p.row_y + 0.3 * cont_icon_h
                    self._draw_icon_svg(
                        cont_icon_name, p.x2, icon_baseline, cont_icon_h,
                        anchor="end", color=icon_color,
                        css_class="ec-duration-icon",
                    )

        # Milestones
        for m in milestones:
            self._draw_milestone(m, day_x, px_per_day, axis_y, config, db)

        # ------------------------------------------------------------------
        # Two-column section: left = group legend, right = milestone roster.
        # Both columns start at legend_y and are rendered side by side.
        # The column split is a fraction of area_w (default 0.5 = equal halves).
        # ------------------------------------------------------------------
        show_ms_list = bool(config.compactplan_show_milestone_list)
        has_legend_content = show_legend and bool(placed)
        has_ms_content = show_ms_list and bool(milestones)

        col_split = float(getattr(config, "compactplan_legend_column_split", 0.5))
        inter_col_gap = 8.0
        left_col_w = area_w * col_split
        right_col_x = area_x + left_col_w + inter_col_gap
        right_col_w = area_w - left_col_w - inter_col_gap

        left_bottom = legend_y
        if has_legend_content:
            left_bottom = self._draw_legend(
                placed, group_color_map, area_x, legend_y, left_col_w, config
            )

        right_bottom = legend_y
        if has_ms_content:
            right_bottom = self._draw_milestone_list(
                milestones, right_col_x, right_col_w, legend_y, config
            )

        rendered_bottom = max(left_bottom, right_bottom)

        # Right-side legend entries — stacked below legend_y, right-aligned to the
        # diagram edge.  Each entry advances next_right_y by one milestone row height.
        ms_row_h = float(config.compactplan_milestone_list_row_height)
        next_right_y = legend_y + ms_row_h  # first right-side legend slot

        # Continuation legend — icon + label (only when continuations exist).
        if show_continuation and has_continuations:
            self._draw_continuation_legend(area_x, area_w, next_right_y, config)
            rendered_bottom = max(rendered_bottom, next_right_y)
            next_right_y += ms_row_h  # advance to next slot

        # Axis legend — short axis-styled swatch + "timeline" label.
        show_axis_legend = bool(config.compactplan_show_axis_legend)
        if show_axis_legend and bool(config.compactplan_show_axis):
            self._draw_axis_legend(area_x, area_w, next_right_y, config)
            rendered_bottom = max(rendered_bottom, next_right_y)

        # ------------------------------------------------------------------
        # REFIT — override the viewBox to the actual rendered vertical extent.
        # _shrink_drawing_to_content() runs before _render_content() and uses
        # only the coordinate dict, so it sees the full CompactPlanArea box
        # and cannot know the floating bands_y / legend_y positions computed
        # here.  We correct the viewBox directly now that all bounds are known.
        # rendered_bottom is the true last drawn Y (last legend or milestone row).
        # ------------------------------------------------------------------
        if config.shrink_to_content:
            content_w = round(area_w, 4)
            content_h = round(max(1.0, rendered_bottom - bands_y), 4)
            vb_x = round(area_x, 4)
            vb_y = round(bands_y, 4)
            self._drawing.view_box = (vb_x, vb_y, content_w, content_h)
            self._drawing.width = content_w
            self._drawing.height = content_h
            self._content_bbox_svg = (area_x, bands_y, area_x + area_w, rendered_bottom)

        return 0, []

    # ------------------------------------------------------------------
    # Band / column header drawing
    # ------------------------------------------------------------------

    def _draw_bands(
        self,
        config: "CalendarConfig",
        time_bands: list[dict],
        band_row_h: float,
        area_x: float,
        area_y: float,
        area_w: float,
        start: date,
        end: date,
        visible_days: list[date],
        px_per_day: float,
        n_vis: int,
        events: "list[Event] | None" = None,
    ) -> None:
        font_name = self._resolve_font(
            getattr(config, "compactplan_text_font_name", None), config
        )
        font_size = float(
            getattr(config, "compactplan_text_font_size", None) or max(7.0, band_row_h * 0.35)
        )
        text_color = str(config.compactplan_text_font_color or "black")
        text_opacity = float(config.compactplan_text_font_opacity)
        _events: list[Event] = events or []

        for band_idx, band in enumerate(time_bands):
            row_y = area_y + band_idx * band_row_h
            unit = str(band.get("unit", "week")).strip().lower()

            # ── Icon band — one cell per visible day, icons driven by rules ──
            if unit == "icon":
                icon_rules = list(band.get("icon_rules") or [])
                day_icon_map = compute_icon_band_days(_events, icon_rules, visible_days)
                icon_h = float(band.get("icon_height") or band_row_h * 0.65)
                fill = str(band.get("fill_color") or "none")
                day_cells = [
                    (
                        self._seg_x(d, visible_days, area_x, area_w, n_vis, px_per_day),
                        px_per_day,
                        day_icon_map.get(d, []),
                    )
                    for d in visible_days
                ]
                self._draw_icon_band_row(day_cells, row_y, band_row_h, icon_h, fill, css_class="ec-band-cell")
                self._draw_line(
                    area_x, row_y + band_row_h, area_x + area_w, row_y + band_row_h,
                    stroke="#cccccc", stroke_width=0.5,
                    css_class="ec-separator",
                )
                continue

            segments = self._build_segments(band, start, end, config, visible_days, band_idx)

            fill_color = str(band.get("fill_color") or "none")
            alt_fill_color = str(band.get("alt_fill_color") or "none")

            # text_align per band: "left" (default) | "center" | "right"
            text_align = str(band.get("text_align", "left")).strip().lower()
            if text_align not in {"left", "center", "right"}:
                text_align = "left"

            for seg_idx, seg in enumerate(segments):
                x1 = self._seg_x(seg.start, visible_days, area_x, area_w, n_vis, px_per_day)
                x2 = self._seg_x(seg.end_exclusive, visible_days, area_x, area_w, n_vis, px_per_day)
                seg_w = max(0.0, x2 - x1)
                if seg_w <= 0:
                    continue

                fill = alt_fill_color if seg_idx % 2 else fill_color
                if not _is_none_color(fill):
                    self._draw_rect(x1, row_y, seg_w, band_row_h, fill=fill, css_class="ec-band-cell")

                # Label text, vertically centered in the band row
                label = seg.label
                if label:
                    text_y = row_y + band_row_h * 0.72
                    pad = 2.0
                    if text_align == "center":
                        text_x = x1 + seg_w / 2.0
                        anchor = "middle"
                        max_w = seg_w - pad * 2
                    elif text_align == "right":
                        text_x = x2 - pad
                        anchor = "end"
                        max_w = seg_w - pad * 2
                    else:  # left
                        text_x = x1 + pad
                        anchor = "start"
                        max_w = seg_w - pad * 2
                    self._draw_text(
                        text_x, text_y, label,
                        font_name, font_size,
                        fill=text_color,
                        fill_opacity=text_opacity,
                        anchor=anchor,
                        max_width=max_w,
                        css_class="ec-label",
                    )

            # Draw thin separator line below each band row
            sep_y = row_y + band_row_h
            self._draw_line(
                area_x, sep_y, area_x + area_w, sep_y,
                stroke="#cccccc", stroke_width=0.5,
                css_class="ec-separator",
            )

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
    ) -> list[_BandSegment]:
        unit = str(band.get("unit", "week")).strip().lower()
        segments: list[_BandSegment] = []
        one_day = timedelta(days=1)

        if unit == "week":
            # week_start: 0=Mon (default), 6=Sun
            week_start_dow = int(band.get("week_start", 0))
            delta = (start.weekday() - week_start_dow) % 7
            cursor = start - timedelta(days=delta)
            seq_n = 1
            while cursor <= end:
                next_cursor = cursor + timedelta(days=7)
                if next_cursor > start:
                    seg_start = max(cursor, start)
                    seg_end = min(next_cursor, end + one_day)
                    if seg_start < seg_end:
                        iso_week = cursor.isocalendar()[1]
                        w_end = next_cursor - one_day  # last day of the week
                        label = str(band.get("label_format", "Week {n}")).format(
                            n=seq_n,
                            week=iso_week,
                            start=cursor.strftime("%-m/%-d"),
                            end=w_end.strftime("%-m/%-d"),
                        )
                        segments.append(
                            _BandSegment(start=seg_start, end_exclusive=seg_end, label=label)
                        )
                        seq_n += 1
                cursor = next_cursor
            return segments

        if unit == "month":
            cursor = date(start.year, start.month, 1)
            fmt = str(band.get("date_format", "MMM"))
            while cursor <= end:
                next_cursor = self._shift_months(cursor, 1)
                if next_cursor > start:
                    seg_start = max(cursor, start)
                    seg_end = min(next_cursor, end + one_day)
                    if seg_start < seg_end:
                        label = arrow.get(cursor).format(fmt)
                        segments.append(
                            _BandSegment(start=seg_start, end_exclusive=seg_end, label=label)
                        )
                cursor = next_cursor
            return segments

        if unit == "fiscal_quarter":
            fiscal_start = int(band.get("fiscal_year_start_month", 10))
            lbl_fmt = str(band.get("label_format", "FY{fy} Q{q}"))
            for seg in build_fiscal_quarter_segments(
                start, end, config,
                fiscal_start_month=fiscal_start,
                label_format=lbl_fmt,
            ):
                segments.append(
                    _BandSegment(start=seg.start, end_exclusive=seg.end_exclusive, label=seg.label)
                )
            return segments

        if unit == "fiscal_period":
            for seg in build_fiscal_period_segments(start, end, config):
                segments.append(
                    _BandSegment(start=seg.start, end_exclusive=seg.end_exclusive, label=seg.label)
                )
            return segments

        if unit == "interval":
            interval_days = max(1, int(band.get("interval_days", 14)))
            prefix = str(band.get("prefix", ""))
            start_index = int(band.get("start_index", 1))
            anchor_str = band.get("anchor_date") or band.get("anchor")
            if anchor_str:
                anchor = date.fromisoformat(str(anchor_str))
                delta_days = (start - anchor).days
                if delta_days >= 0:
                    intervals_elapsed = delta_days // interval_days
                else:
                    intervals_elapsed = -((-delta_days - 1) // interval_days + 1)
                cursor = anchor + timedelta(days=intervals_elapsed * interval_days)
                index = start_index + intervals_elapsed
            else:
                cursor = start
                index = start_index
            while cursor <= end:
                next_cursor = cursor + timedelta(days=interval_days)
                seg_start = max(cursor, start)
                seg_end = min(next_cursor, end + one_day)
                if seg_start < seg_end:
                    segments.append(
                        _BandSegment(start=seg_start, end_exclusive=seg_end, label=f"{prefix}{index}".strip())
                    )
                cursor = next_cursor
                index += 1
            return segments

        # Fallback: date or day-of-week, one segment per visible day
        fmt = str(band.get("date_format", "D"))
        for d in visible_days:
            if start <= d <= end:
                segments.append(
                    _BandSegment(
                        start=d,
                        end_exclusive=d + one_day,
                        label=arrow.get(d).format(fmt),
                    )
                )
        return segments

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
        lane_spacing = float(config.compactplan_lane_spacing)
        line_w = float(config.compactplan_duration_line_width)

        # Build per-duration icon list (one unique icon per line, cycling by index).
        show_dur_icons = bool(getattr(config, "compactplan_show_duration_icons", True))
        list_name = str(
            getattr(config, "compactplan_duration_icon_list", "darksquare") or "darksquare"
        )
        icon_list: list[str] = ICON_SETS.get(list_name, []) if show_dur_icons else []

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
                    continues=continues, icon_name=icon_name,
                )
            )

        return placed

    # ------------------------------------------------------------------
    # Milestone drawing
    # ------------------------------------------------------------------

    def _draw_milestone(
        self,
        evt: Event,
        day_x: dict[date, float],
        px_per_day: float,
        axis_y: float,
        config: "CalendarConfig",
        db: "CalendarDB",
    ) -> None:
        start_d = self._parse_date(evt.start)
        if start_d is None:
            return

        x = self._date_to_x(start_d, day_x, day_x.get(start_d, 0.0), px_per_day) + px_per_day / 2.0
        if start_d in day_x:
            x = day_x[start_d] + px_per_day / 2.0

        color = evt.color or str(config.compactplan_milestone_color or "black")
        flag_h = float(config.compactplan_milestone_flag_height)
        flag_w = float(config.compactplan_milestone_flag_width)

        # Try icon first
        icon_name = evt.icon or getattr(config, "compactplan_milestone_icon", None)
        drew_icon = False
        if icon_name and db is not None:
            icon_svg = db.get_icon_svg(icon_name) if hasattr(db, "get_icon_svg") else None
            if icon_svg:
                icon_size = flag_h + 4.0
                icon_x = x - icon_size / 2.0
                icon_y = axis_y - flag_h - icon_size / 2.0
                self._drawing.append(
                    drawsvg.Raw(
                        f'<g transform="translate({icon_x:.2f},{icon_y:.2f}) scale({icon_size/24:.4f})">'
                        f'{icon_svg}</g>'
                    )
                )
                drew_icon = True

        if not drew_icon:
            self._draw_flag_marker(x, axis_y, flag_h, flag_w, color)

        # Milestone label
        if config.compactplan_show_milestone_labels and evt.task_name:
            font_name = self._resolve_font(
                getattr(config, "compactplan_name_text_font_name", None), config, italic=True
            )
            font_size = float(
                getattr(config, "compactplan_name_text_font_size", None) or 8.0
            )
            label_color = str(config.compactplan_name_text_font_color or "#595959")
            label_opacity = float(config.compactplan_name_text_font_opacity)
            label_x = x + flag_w + 3.0
            label_y = axis_y - flag_h / 2.0
            self._draw_text(
                label_x, label_y, evt.task_name,
                font_name, font_size,
                fill=label_color, fill_opacity=label_opacity,
                css_class="ec-event-name",
            )

    def _draw_flag_marker(
        self,
        x: float,
        axis_y: float,
        flag_h: float,
        flag_w: float,
        color: str,
    ) -> None:
        """Draw a flag-on-stem milestone marker matching the reference SVG design."""
        stem_top = axis_y - flag_h
        # Vertical stem
        self._draw_line(x, axis_y, x, stem_top, stroke=color, stroke_width=1.0, css_class="ec-milestone-marker")
        # Short horizontal foot tick at axis
        self._draw_line(x - 1.0, axis_y, x + 1.0, axis_y, stroke=color, stroke_width=1.0, css_class="ec-milestone-marker")

        # Pennant: a parallelogram/trapezoid to the right of stem tip
        pennant_h = flag_h * 0.7
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
    # Legend drawing
    # ------------------------------------------------------------------

    def _draw_legend(
        self,
        placed: list[_PlacedDuration],
        group_color_map: dict[str, str],
        area_x: float,
        legend_y: float,
        col_w: float,
        config: "CalendarConfig",
    ) -> float:
        """
        Draw the left-area duration legend.

        Layout has two tiers per group:
          • Group header row: [colored swatch line] [Group Name]
          • Per-duration rows: [unique icon] [task_name]

        Groups are distributed across ``legend_team_columns`` evenly balanced
        sub-columns (default 2).  The split is greedy by row count so neither
        sub-column is dramatically taller than the other.

        Returns the actual bottom Y of the tallest sub-column.
        """
        if not placed:
            return legend_y

        font_name = self._resolve_font(
            getattr(config, "compactplan_text_font_name", None), config, italic=True
        )
        font_size = float(getattr(config, "compactplan_text_font_size", None) or 8.0)

        label_color = str(config.compactplan_text_font_color or "#595959")
        label_opacity = float(config.compactplan_text_font_opacity)
        swatch_w = float(config.compactplan_legend_swatch_width)
        swatch_text_gap = 5.0
        row_h = float(config.compactplan_legend_row_height)
        line_w = float(config.compactplan_duration_line_width)

        show_dur_icons = bool(config.compactplan_show_duration_icons)
        dur_icon_h = float(config.compactplan_duration_icon_height)
        dur_icon_color_cfg = str(config.compactplan_duration_icon_color or "").strip()
        icon_text_gap = 3.0

        n_cols = max(1, int(getattr(config, "compactplan_legend_team_columns", 2) or 2))
        sub_gap = 8.0  # pts between sub-columns
        sub_col_w = (col_w - (n_cols - 1) * sub_gap) / n_cols

        # Within each sub-column the same two horizontal offsets are used:
        #   swatch/icon start at sub_x (the sub-column's left edge)
        #   text starts at sub_x + max(swatch_w, dur_icon_h) + text_gap
        left_margin = max(swatch_w, dur_icon_h if show_dur_icons else 0.0) + swatch_text_gap
        # header swatch is always drawn from sub_x; dur icon is also from sub_x
        # text column follows left_margin from sub_x
        text_offset = left_margin
        text_max_w = sub_col_w - left_margin

        # ── Build ordered group → [_PlacedDuration] ─────────────────────────
        seen_groups: dict[str, list[_PlacedDuration]] = {}
        for p in placed:
            group = (p.event.resource_group or "").strip()
            seen_groups.setdefault(group, []).append(p)

        # Row count per group: 1 header + number of named durations.
        group_items = [
            (group, gp, 1 + sum(1 for p in gp if p.event.task_name))
            for group, gp in seen_groups.items()
        ]
        total_rows = sum(rc for _, _, rc in group_items)

        # Greedy balanced split: fill sub-columns sequentially, moving to the
        # next when cumulative rows exceed the per-column target.
        target = total_rows / n_cols
        sub_columns: list[list[tuple[str, list[_PlacedDuration]]]] = [[] for _ in range(n_cols)]
        col_idx, col_rows = 0, 0
        for group, gp, rc in group_items:
            if col_idx < n_cols - 1 and col_rows >= target:
                col_idx += 1
                col_rows = 0
            sub_columns[col_idx].append((group, gp))
            col_rows += rc

        # ── Render each sub-column ───────────────────────────────────────────
        bottom_y = legend_y
        for ci, groups_in_col in enumerate(sub_columns):
            if not groups_in_col:
                continue
            sub_x = area_x + ci * (sub_col_w + sub_gap)
            cur_y = legend_y + row_h

            for group, group_placed in groups_in_col:
                group_color = group_color_map.get(group, "steelblue")
                display_group = group if group else "(unassigned)"

                # ── Group header: colored swatch + group name ──────────────
                swatch_y = cur_y - font_size * 0.3
                self._draw_line(
                    sub_x, swatch_y, sub_x + swatch_w, swatch_y,
                    stroke=group_color,
                    stroke_width=line_w,
                    stroke_opacity=float(config.compactplan_duration_opacity),
                    css_class="ec-legend-swatch",
                )
                self._draw_text(
                    sub_x + text_offset, cur_y, display_group,
                    font_name, font_size,
                    fill=label_color, fill_opacity=label_opacity,
                    max_width=text_max_w,
                    css_class="ec-heading",
                )
                cur_y += row_h

                # ── Per-duration rows: unique icon + task name ─────────────
                for p in group_placed:
                    task_name = p.event.task_name or ""
                    if not task_name:
                        continue

                    if show_dur_icons and p.icon_name:
                        icon_baseline = cur_y - font_size * 0.35 + dur_icon_h * 0.3
                        icon_color = dur_icon_color_cfg if dur_icon_color_cfg else p.color
                        self._draw_icon_svg(
                            p.icon_name, sub_x, icon_baseline, dur_icon_h,
                            anchor="start", color=icon_color,
                            css_class="ec-legend-icon",
                        )

                    self._draw_text(
                        sub_x + text_offset, cur_y, task_name,
                        font_name, font_size,
                        fill=label_color, fill_opacity=label_opacity,
                        max_width=text_max_w,
                        css_class="ec-legend-text",
                    )
                    cur_y += row_h

            bottom_y = max(bottom_y, cur_y)

        return bottom_y

    def _draw_milestone_list(
        self,
        milestones: list,
        area_x: float,
        area_w: float,
        list_y: float,
        config: "CalendarConfig",
    ) -> float:
        """Draw a date-sorted milestone roster; return the actual bottom Y of the last row."""
        # Collect milestones that have both a parseable date and a name
        entries: list[tuple[date, str]] = []
        for m in milestones:
            d = self._parse_date(m.start)
            name = (m.task_name or "").strip()
            if d is not None and name:
                entries.append((d, name))

        if not entries:
            return list_y

        entries.sort(key=lambda e: e[0])

        font_name = self._resolve_font(
            getattr(config, "compactplan_name_text_font_name", None), config
        )
        font_size = float(
            getattr(config, "compactplan_name_text_font_size", None) or 8.0
        )
        date_color = str(config.compactplan_milestone_list_date_color or "#595959")
        name_color = str(config.compactplan_name_text_font_color or "#595959")
        opacity = float(config.compactplan_name_text_font_opacity)
        row_h = float(config.compactplan_milestone_list_row_height)
        date_col_w = float(config.compactplan_milestone_list_date_col_width)
        date_fmt = str(config.compactplan_milestone_list_date_format or "M/D")

        cur_y = list_y + row_h
        for d, name in entries:
            date_str = arrow.get(d).format(date_fmt)
            self._draw_text(
                area_x, cur_y, date_str,
                font_name, font_size,
                fill=date_color, fill_opacity=opacity,
                css_class="ec-event-date",
            )
            self._draw_text(
                area_x + date_col_w, cur_y, name,
                font_name, font_size,
                fill=name_color, fill_opacity=opacity,
                max_width=area_w - date_col_w,
                css_class="ec-event-name",
            )
            cur_y += row_h

        return cur_y

    def _draw_continuation_legend(
        self,
        area_x: float,
        area_w: float,
        entry_y: float,
        config: "CalendarConfig",
    ) -> None:
        """
        Draw the continuation icon + label at *entry_y* (text baseline), right-aligned
        to the diagram's right edge (area_x + area_w).

        The label's right edge sits exactly at the diagram right edge; the icon is
        placed immediately to its left with a small gap.  This entry is overlaid at
        the same vertical position as the first milestone-roster row so it uses the
        visual space that already exists rather than extending the diagram height.
        """
        from config.config import get_font_path

        font_name = self._resolve_font(
            getattr(config, "compactplan_text_font_name", None), config, italic=True
        )
        font_size = float(getattr(config, "compactplan_text_font_size", None) or 8.0)
        label_color = str(config.compactplan_text_font_color or "#595959")
        label_opacity = float(config.compactplan_text_font_opacity)

        icon_name = str(config.compactplan_continuation_icon or "arrow-right")
        icon_h = float(config.compactplan_continuation_icon_height or 8.0)
        icon_color_cfg = (config.compactplan_continuation_icon_color or "").strip()
        icon_color = icon_color_cfg if icon_color_cfg else label_color
        legend_text = str(config.compactplan_continuation_legend_text or "activity continues")

        right_x = area_x + area_w
        icon_text_gap = 3.0  # pts between icon right edge and text left edge

        # Measure text so the icon can be placed flush to its left.
        try:
            font_path = get_font_path(font_name)
            text_w = string_width(legend_text, font_path, font_size)
        except Exception:
            text_w = 0.0

        # Icon: right edge at (right_x - text_w - icon_text_gap).
        # _draw_icon_svg with anchor="end" places the icon's right edge at x.
        # Vertically centre the icon on the text's optical mid-line.
        # _draw_icon_svg places icon top at  baseline_y - 0.8 * size,
        #   so icon centre = baseline_y - 0.3 * size.
        # Text optical centre sits ~0.35 * font_size above the text baseline.
        # Solving icon_centre == text_optical_centre:
        #   baseline_y - 0.3 * icon_h  =  entry_y - 0.35 * font_size
        #   baseline_y = entry_y - 0.35 * font_size + 0.3 * icon_h
        icon_x = right_x - text_w - icon_text_gap
        icon_baseline = entry_y - font_size * 0.35 + icon_h * 0.3
        self._draw_icon_svg(
            icon_name, icon_x, icon_baseline, icon_h,
            anchor="end", color=icon_color,
            css_class="ec-legend-icon",
        )

        # Text: right edge at diagram right edge.
        self._draw_text(
            right_x, entry_y, legend_text,
            font_name, font_size,
            fill=label_color, fill_opacity=label_opacity,
            anchor="end",
            css_class="ec-legend-text",
        )

    def _draw_axis_legend(
        self,
        area_x: float,
        area_w: float,
        entry_y: float,
        config: "CalendarConfig",
    ) -> None:
        """
        Draw an axis sample swatch + label at *entry_y* (text baseline),
        right-aligned to the diagram's right edge.

        The swatch is a short line segment styled identically to the timeline
        axis (same color, width, dasharray and opacity).  Its length equals
        ``compactplan_legend_swatch_width`` — the same as the team-color swatches
        — so it visually matches the rest of the legend.  The label text
        (default "timeline") appears immediately to the right of the swatch.
        """
        from config.config import get_font_path

        font_name = self._resolve_font(
            getattr(config, "compactplan_text_font_name", None), config, italic=True
        )
        font_size = float(getattr(config, "compactplan_text_font_size", None) or 8.0)
        label_color = str(config.compactplan_text_font_color or "#595959")
        label_opacity = float(config.compactplan_text_font_opacity)

        legend_text = str(config.compactplan_legend_axis_text or "timeline")
        swatch_w = float(config.compactplan_legend_swatch_width)

        right_x = area_x + area_w
        swatch_text_gap = 3.0  # pts between swatch right edge and text left edge

        # Measure text width so we can position the swatch flush to its left.
        try:
            font_path = get_font_path(font_name)
            text_w = string_width(legend_text, font_path, font_size)
        except Exception:
            text_w = 0.0

        # Swatch: right edge at (right_x - text_w - swatch_text_gap),
        # left edge swatch_w further to the left.
        # Y sits at the text optical mid-line (~0.3 * font_size above baseline),
        # matching the team-color swatch formula used in _draw_legend.
        swatch_x2 = right_x - text_w - swatch_text_gap
        swatch_x1 = swatch_x2 - swatch_w
        swatch_y = entry_y - font_size * 0.3

        self._draw_line(
            swatch_x1, swatch_y, swatch_x2, swatch_y,
            stroke=str(config.compactplan_axis_color or "#7f7f7f"),
            stroke_width=float(config.compactplan_axis_width),
            stroke_dasharray=config.compactplan_axis_dasharray or None,
            stroke_opacity=float(config.compactplan_axis_opacity),
            css_class="ec-legend-swatch",
        )

        # Label: right edge at diagram right edge.
        self._draw_text(
            right_x, entry_y, legend_text,
            font_name, font_size,
            fill=label_color, fill_opacity=label_opacity,
            anchor="end",
            css_class="ec-legend-text",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wrap_names_to_lines(
        prefix: str,
        names: list[str],
        font_path: str,
        font_size: float,
        max_width: float,
    ) -> list[str]:
        """
        Pack *names* greedily as comma-separated text that fits within *max_width*.

        The first returned line begins with *prefix* (e.g. ``"Engineering: "``).
        Subsequent lines contain only names (no prefix), indented visually by the
        caller.  At least one name is placed on each line even if it overflows, so
        the list is always non-empty and never causes an infinite loop.

        *font_path* must be a resolved TTF file path (not a font name string).

        If *names* is empty the prefix is returned as a single-element list with
        any trailing ``": "`` stripped.
        """
        if not names:
            return [prefix.rstrip(": ").rstrip()]

        lines: list[str] = []
        current = prefix + names[0]  # first line always has prefix + first name

        for name in names[1:]:
            trial = current + ", " + name
            if string_width(trial, font_path, font_size) <= max_width:
                current = trial
            else:
                lines.append(current)
                current = name  # new continuation line; always accept first name

        lines.append(current)
        return lines

    @staticmethod
    def _visible_days(start: date, end: date, weekend_style: int) -> list[date]:
        """Return ordered list of visible dates respecting weekend_style."""
        days: list[date] = []
        cursor = start
        while cursor <= end:
            if weekend_style == 0:
                if cursor.weekday() < 5:  # Mon–Fri only
                    days.append(cursor)
            else:
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

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
    def _shift_months(d: date, months: int) -> date:
        month_index = (d.month - 1) + months
        year = d.year + (month_index // 12)
        month = (month_index % 12) + 1
        return date(year, month, 1)


    @staticmethod
    def _resolve_font(
        font_setting: str | None, config: "CalendarConfig", italic: bool = False
    ) -> str:
        """Resolve a font name: explicit setting → base config font → safe fallback."""
        from config.config import FONT_REGISTRY, Fonts

        if font_setting:
            if font_setting in FONT_REGISTRY:
                return font_setting
        # Try base italic or regular font from config
        if italic:
            candidates = [
                getattr(config, "notes_font", None),
                getattr(config, "base_font", None),
            ]
        else:
            candidates = [getattr(config, "base_font", None)]
        for c in candidates:
            if c and c in FONT_REGISTRY:
                return c
        return Fonts.RC_LIGHT
