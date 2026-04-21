"""Blockplan SVG renderer."""

from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import arrow
import drawsvg

from config.config import get_font_path
from renderers.svg_base import BaseSVGRenderer, _is_none_color
from renderers.text_utils import string_width
from shared.data_models import Event
from shared.fiscal_renderer import build_fiscal_quarter_segments
from shared.day_classifier import classify_day, day_rule_matches
from shared.icon_band import compute_icon_band_days


def _nwd_fill_for_classes(
    classes: frozenset[str],
    band_fill_rules: list[dict] | None,
    config: "CalendarConfig",
) -> str | None:
    """Resolve a non-workday fill override for a single-day cell.

    Order of precedence:

    1. Band-level ``fill_rules`` — first matching rule wins.
    2. Config-level defaults — ``federal_holiday`` → ``company_holiday`` →
       ``weekend``.

    Returns ``None`` if the day has no non-workday classes or no override
    is configured.
    """
    if not classes:
        return None
    if band_fill_rules:
        for rule in band_fill_rules:
            if not isinstance(rule, dict):
                continue
            match = rule.get("match") or {}
            if not isinstance(match, dict):
                continue
            if day_rule_matches(classes, match):
                color = rule.get("color")
                if color:
                    return str(color)
    if "federal_holiday" in classes and config.blockplan_federal_holiday_fill_color:
        return config.blockplan_federal_holiday_fill_color
    if "company_holiday" in classes and config.blockplan_company_holiday_fill_color:
        return config.blockplan_company_holiday_fill_color
    if "weekend" in classes and config.blockplan_weekend_fill_color:
        return config.blockplan_weekend_fill_color
    return None


def _nwd_icon_for_classes(
    classes: frozenset[str], config: "CalendarConfig"
) -> tuple[str, str] | None:
    """Resolve a global non-workday icon for a single-day cell.

    Returns ``(icon_name, color)`` or ``None``.  Priority:
    federal_holiday → company_holiday → weekend.  The icon colour reuses
    the matching fill colour (or a default "#333333" when none is set).
    """
    if not classes:
        return None
    if "federal_holiday" in classes and config.blockplan_federal_holiday_icon:
        return (
            config.blockplan_federal_holiday_icon,
            config.blockplan_federal_holiday_fill_color or "#333333",
        )
    if "company_holiday" in classes and config.blockplan_company_holiday_icon:
        return (
            config.blockplan_company_holiday_icon,
            config.blockplan_company_holiday_fill_color or "#333333",
        )
    if "weekend" in classes and config.blockplan_weekend_icon:
        return (
            config.blockplan_weekend_icon,
            config.blockplan_weekend_fill_color or "#333333",
        )
    return None

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


@dataclass(frozen=True)
class _BandSegment:
    start: date
    end_exclusive: date
    label: str


class BlockPlanRenderer(BaseSVGRenderer):
    """Renderer for the blockplan spreadsheet-like visualization."""

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        area_x, area_y, area_w, area_h = coordinates.get(
            "BlockPlanArea", (0.0, 0.0, config.pageX, config.pageY)
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

        top_bands = list(getattr(config, "blockplan_top_time_bands", []) or [])
        bottom_bands = list(getattr(config, "blockplan_bottom_time_bands", []) or [])
        swimlanes = list(getattr(config, "blockplan_swimlanes", []) or [])
        if not swimlanes:
            swimlanes = [{"name": "All Items", "match": {}}]

        label_col_w = min(
            area_w * 0.45,
            max(80.0, area_w * float(config.blockplan_label_column_ratio)),
        )
        timeline_x = area_x + label_col_w
        timeline_w = max(1.0, area_w - label_col_w)

        _bg_style = config.get_box_style("ec-background")
        bg = str(_bg_style.fill or "").strip().lower()
        if bg not in {"", "none", "transparent"}:
            self._draw_rect(
                area_x, area_y, area_w, area_h, fill=_bg_style.fill,
                css_class="ec-background",
            )

        # Heights — cap combined band heights so swimlane region always has positive height
        top_bands_h = max(
            0.0,
            min(
                sum(self._band_row_h(b, config) for b in top_bands)
                if top_bands
                else 0.0,
                area_h,
            ),
        )
        bottom_bands_h = max(
            0.0,
            min(
                sum(self._band_row_h(b, config) for b in bottom_bands)
                if bottom_bands
                else 0.0,
                area_h - top_bands_h,
            ),
        )

        lanes_top = area_y + top_bands_h
        lanes_bottom = area_y + area_h - bottom_bands_h

        # ── top bands ─────────────────────────────────────────────────────────
        if top_bands:
            self._draw_time_bands(
                config=config,
                db=db,
                bands=top_bands,
                start=start,
                end=end,
                visible_days=visible_days,
                left_x=area_x,
                timeline_x=timeline_x,
                timeline_w=timeline_w,
                top_y=area_y,
                events=events,
            )

        # ── vertical lines & column fills (swimlane region only) ──────────────
        all_bands = top_bands + bottom_bands
        if all_bands:
            self._draw_configured_vertical_lines(
                config=config,
                db=db,
                bands=all_bands,
                start=start,
                end=end,
                visible_days=visible_days,
                timeline_x=timeline_x,
                timeline_w=timeline_w,
                top_y=lanes_top,
                bottom_y=lanes_bottom,
            )

        self._load_icon_svg_cache(db)

        # ── separator between top bands and swimlanes ─────────────────────────
        _grid_color, _grid_w, _grid_op, _grid_dash = self._grid_stroke(config)
        self._draw_line(
            area_x,
            lanes_top,
            area_x + area_w,
            lanes_top,
            stroke=_grid_color,
            stroke_width=_grid_w,
            stroke_opacity=_grid_op,
            stroke_dasharray=_grid_dash,
            css_class="ec-separator",
        )

        # ── swimlanes ─────────────────────────────────────────────────────────
        event_objects = [Event.from_dict(e) for e in events]
        lane_events = self._assign_events_to_lanes(config, event_objects, swimlanes)
        self._draw_swimlanes(
            config=config,
            lane_defs=lane_events,
            start=start,
            end=end,
            visible_days=visible_days,
            left_x=area_x,
            timeline_x=timeline_x,
            timeline_w=timeline_w,
            top_y=lanes_top,
            bottom_y=lanes_bottom,
        )

        # ── separator + bottom bands (drawn after swimlanes) ──────────────────
        if bottom_bands:
            self._draw_line(
                area_x,
                lanes_bottom,
                area_x + area_w,
                lanes_bottom,
                stroke=_grid_color,
                stroke_width=_grid_w,
                stroke_opacity=_grid_op,
                stroke_dasharray=_grid_dash,
                css_class="ec-separator",
            )
            self._draw_time_bands(
                config=config,
                db=db,
                bands=bottom_bands,
                start=start,
                end=end,
                visible_days=visible_days,
                left_x=area_x,
                timeline_x=timeline_x,
                timeline_w=timeline_w,
                top_y=lanes_bottom,
                events=events,
            )

        return 0, []

    @staticmethod
    def _timeband_stroke(
        config: "CalendarConfig",
    ) -> tuple[str, float, float, str | None]:
        """Stroke attrs for band/heading row cells.

        Honors blockplan.timeband_line_* when set, falling back to blockplan.grid_*.
        """
        color = config.blockplan_timeband_line_color
        if color is None:
            color = config.blockplan_grid_color
        width = config.blockplan_timeband_line_width
        if width is None:
            width = config.blockplan_grid_line_width
        opacity = config.blockplan_timeband_line_opacity
        if opacity is None:
            opacity = config.blockplan_grid_opacity
        dasharray = config.blockplan_timeband_line_dasharray
        if dasharray is None:
            dasharray = config.blockplan_grid_dasharray
        return color, float(width), float(opacity), dasharray

    @staticmethod
    def _grid_stroke(
        config: "CalendarConfig",
    ) -> tuple[str, float, float, str | None]:
        """Stroke attrs for blockplan grid lines."""
        return (
            config.blockplan_grid_color,
            float(config.blockplan_grid_line_width),
            float(config.blockplan_grid_opacity),
            config.blockplan_grid_dasharray,
        )

    @staticmethod
    def _band_row_h(band: dict[str, Any], config: "CalendarConfig") -> float:
        """Row height for one time band.

        When ``row_height`` is explicitly set on the band that value is used directly,
        allowing each band to have an independent height with font size derived from it.
        When absent the row height is derived from the band font size (``font_size`` key
        or the page-scaled ``config.blockplan_band_font_size``) plus 1 % padding —
        identical to the pre-per-band-height behaviour so existing layouts are unchanged.
        """
        if "row_height" in band:
            return float(band["row_height"])
        font_size = float(band.get("font_size") or config.blockplan_band_font_size)
        return font_size * 1.01

    @staticmethod
    def _resolve_color_list(
        fill_color: Any,
        fill_palette: Any,
        db: "CalendarDB",
    ) -> list[str]:
        """Return an ordered color list for cycling across band segments.

        Resolution priority:
        1. ``fill_color`` when it is already a list of color strings.
        2. ``fill_color`` when it is a named palette in the database.
        3. ``fill_palette`` when it is already a list of color strings.
        4. ``fill_palette`` when it is a named palette in the database.
        5. Empty list — caller should fall back to ``fill_color`` as a plain
           single-color string.
        """
        _resolver = getattr(db, "resolve_color_name", None) if db is not None else None

        def _resolve(c: str) -> str:
            return _resolver(c) if _resolver else c

        # fill_color as explicit list
        if isinstance(fill_color, list):
            colors = [_resolve(str(c)) for c in fill_color if c]
            if colors:
                return colors
        # fill_color as named palette
        if isinstance(fill_color, str) and fill_color:
            resolved = db.get_palette(fill_color)
            if resolved:
                return resolved
        # fill_palette as explicit list
        if isinstance(fill_palette, list):
            colors = [_resolve(str(c)) for c in fill_palette if c]
            if colors:
                return colors
        # fill_palette as named palette
        if isinstance(fill_palette, str) and fill_palette:
            resolved = db.get_palette(fill_palette)
            if resolved:
                return resolved
        return []

    @staticmethod
    def _shift_months(d: date, months: int) -> date:
        month_index = (d.month - 1) + months
        year = d.year + (month_index // 12)
        month = (month_index % 12) + 1
        return date(year, month, 1)

    def _build_segments(
        self,
        band: dict[str, Any],
        start: date,
        end: date,
        config: "CalendarConfig",
        visible_days: list[date] | None = None,
        db: "CalendarDB | None" = None,
    ) -> list[_BandSegment]:
        unit = str(band.get("unit", "date")).strip().lower()
        segments: list[_BandSegment] = []
        one_day = timedelta(days=1)

        if unit == "fiscal_quarter":
            fiscal_start = int(
                band.get(
                    "fiscal_year_start_month", config.blockplan_fiscal_year_start_month
                )
            )
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

        if unit == "month":
            cursor = date(start.year, start.month, 1)
            fmt = str(band.get("date_format", "MMM"))
            while cursor <= end:
                next_cursor = self._shift_months(cursor, 1)
                if next_cursor > start:
                    label = arrow.get(cursor).format(fmt)
                    segments.append(
                        _BandSegment(
                            start=max(cursor, start),
                            end_exclusive=min(next_cursor, end + one_day),
                            label=label,
                        )
                    )
                cursor = next_cursor
            return [s for s in segments if s.start < s.end_exclusive]

        if unit == "week":
            week_start = int(band.get("week_start", config.blockplan_week_start))
            delta = (start.weekday() - week_start) % 7
            cursor = start - timedelta(days=delta)
            while cursor <= end:
                next_cursor = cursor + timedelta(days=7)
                if next_cursor > start:
                    iso_week = cursor.isocalendar()[1]
                    label = str(band.get("label_format", "Week {week}")).format(
                        week=iso_week
                    )
                    segments.append(
                        _BandSegment(
                            start=max(cursor, start),
                            end_exclusive=min(next_cursor, end + one_day),
                            label=label,
                        )
                    )
                cursor = next_cursor
            return [s for s in segments if s.start < s.end_exclusive]

        if unit == "interval":
            interval_days = max(1, int(band.get("interval_days", 14)))
            prefix = str(band.get("prefix", ""))
            start_index = int(band.get("start_index", 1))
            max_index_raw = band.get("max_index")
            max_index = int(max_index_raw) if max_index_raw is not None else None
            anchor_str = band.get("anchor_date") or band.get("anchor")
            if anchor_str:
                anchor = date.fromisoformat(str(anchor_str))
                delta_days = (start - anchor).days
                if delta_days >= 0:
                    intervals_elapsed = delta_days // interval_days
                else:
                    intervals_elapsed = -((-delta_days - 1) // interval_days + 1)
                cursor = anchor + timedelta(days=intervals_elapsed * interval_days)
                if max_index is not None:
                    cycle_len = max_index - start_index + 1
                    index = start_index + (intervals_elapsed % cycle_len)
                else:
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
                        _BandSegment(
                            start=seg_start,
                            end_exclusive=seg_end,
                            label=f"{prefix}{index}".strip(),
                        )
                    )
                cursor = next_cursor
                index += 1
                if max_index is not None and index > max_index:
                    index = start_index
            return segments

        if unit in {"date", "dow"}:
            fmt = str(band.get("date_format", "D" if unit == "date" else "ddd"))
            date_source = (
                visible_days
                if (unit in {"date", "dow"} and visible_days is not None)
                else None
            )
            if date_source is not None:
                iter_days = [d for d in date_source if start <= d <= end]
            else:
                iter_days = []
                cursor = start
                while cursor <= end:
                    iter_days.append(cursor)
                    cursor += one_day
            for cursor in iter_days:
                segments.append(
                    _BandSegment(
                        start=cursor,
                        end_exclusive=cursor + one_day,
                        label=arrow.get(cursor).format(fmt),
                    )
                )
            return segments

        if unit in {"countdown", "countup"}:
            if unit == "countdown":
                ref_str = band.get("target_date") or band.get("target")
            else:
                ref_str = band.get("start_date") or band.get("start")
            if not ref_str:
                return []
            ref_date = date.fromisoformat(str(ref_str))
            skip_wk = bool(band.get("skip_weekends", False))
            skip_nwd = bool(band.get("skip_nonworkdays", False))
            label_fmt = str(band.get("label_format", "{n}"))

            # Pre-compute nonworkday dates once for the full span
            nwd_set: set[date] = set()
            if skip_nwd and db is not None:
                span_start = min(start, ref_date)
                span_end = max(end, ref_date)
                d_iter = span_start
                while d_iter <= span_end:
                    if db.is_nonworkday(d_iter.strftime("%Y%m%d")):
                        nwd_set.add(d_iter)
                    d_iter += timedelta(days=1)

            def _count_days(from_d: date, to_d: date) -> int:
                """Days from from_d (exclusive) to to_d (inclusive), skipping filtered days."""
                if from_d == to_d:
                    return 0
                sign = 1 if to_d > from_d else -1
                count = 0
                cursor = from_d + timedelta(days=sign)
                while (sign == 1 and cursor <= to_d) or (sign == -1 and cursor >= to_d):
                    if not (skip_wk and cursor.weekday() >= 5) and cursor not in nwd_set:
                        count += 1
                    cursor += timedelta(days=sign)
                return sign * count

            iter_days = [d for d in (visible_days or []) if start <= d <= end]
            if not iter_days:
                c = start
                while c <= end:
                    iter_days.append(c)
                    c += timedelta(days=1)

            for d in iter_days:
                # countdown: days remaining to ref_date  (from d → ref_date)
                # countup:   days elapsed since ref_date (from ref_date → d)
                if unit == "countdown":
                    n = _count_days(d, ref_date)
                else:
                    n = _count_days(ref_date, d)
                segments.append(
                    _BandSegment(
                        start=d,
                        end_exclusive=d + one_day,
                        label=label_fmt.format(n=n),
                    )
                )
            return segments

        return [_BandSegment(start=start, end_exclusive=end + one_day, label="")]

    def _draw_time_bands(
        self,
        *,
        config: "CalendarConfig",
        db: "CalendarDB",
        bands: list[dict[str, Any]],
        start: date,
        end: date,
        visible_days: list[date],
        left_x: float,
        timeline_x: float,
        timeline_w: float,
        top_y: float,
        events: list | None = None,
    ) -> None:
        # Any band may want non-workday fills or day-based icon rules; build a
        # classifier cache once for every visible day and reuse across bands.
        _day_classes: dict[date, frozenset[str]] = {
            d: classify_day(d, db, config) for d in visible_days
        }

        def _classify(d: date) -> frozenset[str]:
            return _day_classes.get(d, frozenset())

        # Load icon cache once if any icon bands are present (event- or
        # day-driven icon rules both need rendered icons).
        _has_icon_band = any(
            str(b.get("unit", "")).strip().lower() == "icon" for b in bands
        )
        _band_events: list[Event] = []
        if _has_icon_band:
            self._load_icon_svg_cache(db)
            if events:
                _band_events = [
                    Event.from_dict(e) if isinstance(e, dict) else e for e in events
                ]

        _n_vis = len(visible_days)
        _px_per_day = timeline_w / max(1, _n_vis)

        cumulative_h = 0.0
        for idx, band in enumerate(bands):
            has_explicit_row_h = "row_height" in band
            row_h = self._band_row_h(band, config)
            y_top = top_y + cumulative_h
            y_bottom = y_top + row_h
            cumulative_h += row_h

            unit = str(band.get("unit", "date")).strip().lower()

            # ── Icon band — one cell per visible day, icons driven by rules ──
            if unit == "icon":
                # Heading cell (left column — same as regular bands).
                _heading_cell_style = config.get_box_style("ec-heading-cell")
                heading_fill = band.get(
                    "label_fill_color", _heading_cell_style.fill
                )
                tb_color, tb_width, tb_opacity, tb_dasharray = self._timeband_stroke(config)
                stroke = band.get("stroke_color", tb_color)
                self._draw_rect(
                    left_x, y_top, timeline_x - left_x, row_h,
                    fill=heading_fill,
                    stroke=stroke, stroke_width=tb_width,
                    stroke_opacity=tb_opacity, stroke_dasharray=tb_dasharray,
                    css_class="ec-heading-cell",
                )
                _heading_text_style = config.get_text_style("ec-heading")
                heading_font = band.get("label_font", _heading_text_style.font)
                heading_font_size = float(
                    band.get("label_font_size") or (row_h * 0.65 if has_explicit_row_h else config.blockplan_header_font_size)
                )
                heading_color = band.get("label_color", _heading_text_style.color)
                heading_opacity = float(band.get("label_opacity", _heading_text_style.opacity))
                self._draw_text(
                    left_x + 6.0,
                    y_top + (row_h * 0.50) + (heading_font_size * 0.30),
                    str(band.get("label", "")),
                    heading_font, heading_font_size,
                    fill=heading_color, fill_opacity=heading_opacity,
                    anchor="start",
                    max_width=max(8.0, timeline_x - left_x - 10),
                    css_class="ec-heading",
                )
                # Icon cells.
                icon_rules = list(band.get("icon_rules") or [])
                day_icon_map = compute_icon_band_days(
                    _band_events, icon_rules, visible_days, classify_fn=_classify
                )
                icon_h = float(band.get("icon_height") or row_h * 0.65)
                fill = str(band.get("fill_color") or "none")
                day_cells = [
                    (
                        self._boundary_x(d, visible_days, timeline_x, timeline_w),
                        _px_per_day,
                        day_icon_map.get(d, []),
                    )
                    for d in visible_days
                ]
                self._draw_icon_band_row(day_cells, y_top, row_h, icon_h, fill)
                # Bottom border for the row.
                self._draw_line(
                    timeline_x, y_top + row_h, timeline_x + timeline_w, y_top + row_h,
                    stroke=stroke, stroke_width=tb_width,
                    stroke_opacity=tb_opacity, stroke_dasharray=tb_dasharray,
                    css_class="ec-grid-line",
                )
                continue

            _band_cell_style = config.get_box_style("ec-band-cell")
            _label_text_style = config.get_text_style("ec-label")
            _heading_text_style = config.get_text_style("ec-heading")
            _heading_cell_style = config.get_box_style("ec-heading-cell")
            band_fill = band.get("fill_color", _band_cell_style.fill)
            band_palette = band.get(
                "fill_palette", config.blockplan_timeband_fill_palette
            )
            color_list = self._resolve_color_list(band_fill, band_palette, db)
            band_label_color = band.get(
                "font_color", _label_text_style.color
            )
            band_label_opacity = float(
                band.get("font_opacity", _label_text_style.opacity)
            )
            band_font = band.get("font", _label_text_style.font)
            if band.get("font_size"):
                band_font_size = float(band["font_size"])
            elif has_explicit_row_h:
                band_font_size = row_h * 0.65
            else:
                band_font_size = float(config.blockplan_band_font_size)
            heading_font = band.get("label_font", _heading_text_style.font)
            if band.get("label_font_size"):
                heading_font_size = float(band["label_font_size"])
            elif has_explicit_row_h:
                heading_font_size = row_h * 0.65
            else:
                heading_font_size = float(config.blockplan_header_font_size)
            heading_color = band.get(
                "label_color", config.blockplan_header_label_color
            )
            heading_opacity = float(
                band.get("label_opacity", config.blockplan_header_label_opacity)
            )
            heading_fill = band.get(
                "label_fill_color", _heading_cell_style.fill
            )
            heading_align_h = self._normalize_halign(
                band.get("label_align_h", config.blockplan_header_label_align_h),
                default="left",
            )
            tb_color, tb_width, tb_opacity, tb_dasharray = self._timeband_stroke(config)
            stroke = band.get("stroke_color", tb_color)

            # Left heading cell
            self._draw_rect(
                left_x,
                y_top,
                timeline_x - left_x,
                row_h,
                fill=heading_fill,
                stroke=stroke,
                stroke_width=tb_width,
                stroke_opacity=tb_opacity,
                stroke_dasharray=tb_dasharray,
                css_class="ec-heading-cell",
            )
            heading_w = timeline_x - left_x
            if heading_align_h == "center":
                heading_x = left_x + (heading_w * 0.5)
                heading_anchor = "middle"
            elif heading_align_h == "right":
                heading_x = timeline_x - 6.0
                heading_anchor = "end"
            else:
                heading_x = left_x + 6.0
                heading_anchor = "start"
            self._draw_text(
                heading_x,
                y_top + (row_h * 0.50) + (heading_font_size * 0.30),
                str(band.get("label", "")),
                heading_font,
                heading_font_size,
                fill=heading_color,
                fill_opacity=heading_opacity,
                anchor=heading_anchor,
                max_width=max(8.0, timeline_x - left_x - 10),
                css_class="ec-heading",
            )

            band_fill_rules = band.get("fill_rules")
            if band_fill_rules is not None and not isinstance(band_fill_rules, list):
                band_fill_rules = None
            segments = self._build_segments(
                band, start, end, config, visible_days=visible_days, db=db
            )
            show_every = max(1, int(band.get("show_every", 1)))
            unit = str(band.get("unit", "date")).strip().lower()
            if show_every > 1 and unit in {"date", "dow"}:
                # Group within each calendar week so that no cell spans a week
                # boundary — this ensures week-band borders align with date cells.
                week_start_wd = int(band.get("week_start", config.blockplan_week_start))
                groups: list[list[_BandSegment]] = []
                bucket: list[_BandSegment] = []
                for seg in segments:
                    if bucket and (
                        seg.start.weekday() == week_start_wd
                        or len(bucket) >= show_every
                    ):
                        groups.append(bucket)
                        bucket = []
                    bucket.append(seg)
                if bucket:
                    groups.append(bucket)
            else:
                groups = [
                    segments[i : i + show_every]
                    for i in range(0, len(segments), show_every)
                ]
            for gidx, group in enumerate(groups):
                first_seg = group[0]
                last_seg = group[-1]
                seg_x0 = self._boundary_x(
                    first_seg.start, visible_days, timeline_x, timeline_w
                )
                seg_x1 = self._boundary_x(
                    last_seg.end_exclusive, visible_days, timeline_x, timeline_w
                )
                raw_w = seg_x1 - seg_x0
                if raw_w <= 0:
                    # Group has no rendered dates on the visible-day axis.
                    # Example: weekend-only slice while --weekends=0.
                    continue
                seg_w = raw_w
                if color_list:
                    seg_fill = color_list[gidx % len(color_list)]
                elif isinstance(band_fill, str):
                    _resolver = getattr(db, "resolve_color_name", None) if db is not None else None
                    seg_fill = _resolver(band_fill) if _resolver else band_fill
                else:
                    seg_fill = "none"
                # Non-workday override (single-day date/dow cells only)
                _is_single_day = (
                    unit in {"date", "dow"}
                    and len(group) == 1
                    and (first_seg.end_exclusive - first_seg.start).days == 1
                )
                if _is_single_day:
                    _nwd_fill = _nwd_fill_for_classes(
                        _classify(first_seg.start), band_fill_rules, config
                    )
                    if _nwd_fill:
                        seg_fill = _nwd_fill
                self._draw_rect(
                    seg_x0,
                    y_top,
                    seg_w,
                    row_h,
                    fill=seg_fill,
                    fill_opacity=config.blockplan_timeband_fill_opacity,
                    stroke=stroke,
                    stroke_width=tb_width,
                    stroke_opacity=tb_opacity,
                    stroke_dasharray=tb_dasharray,
                    css_class="ec-band-cell",
                )
                _lv = band.get("label_values")
                if _lv and isinstance(_lv, list):
                    _raw = _lv[gidx % len(_lv)]
                    display_label = first_seg.label if _raw is None else str(_raw)
                else:
                    display_label = first_seg.label
                if display_label:
                    self._draw_text(
                        seg_x0 + (seg_w / 2.0),
                        y_top + (row_h * 0.50) + (band_font_size * 0.30),
                        display_label,
                        band_font,
                        band_font_size,
                        fill=band_label_color,
                        fill_opacity=band_label_opacity,
                        anchor="middle",
                        max_width=max(8.0, seg_w - 4),
                        css_class="ec-label",
                    )

    def _draw_configured_vertical_lines(
        self,
        *,
        config: "CalendarConfig",
        db: "CalendarDB",
        bands: list[dict[str, Any]],
        start: date,
        end: date,
        visible_days: list[date],
        timeline_x: float,
        timeline_w: float,
        top_y: float,
        bottom_y: float,
    ) -> None:
        """Draw vertical lines (and optional column fills) pinned to time-band segments.

        Each entry in ``blockplan_vertical_lines`` supports the following keys:
          band         – band label to pin to (required)
          repeat       – True → apply to every segment in the band
          value        – specific segment label to match (used when repeat is False)
          align        – "start" (default) | "center" | "end" — where to pin the line
          color        – line stroke color (default: blockplan_vertical_line_color)
          width        – line stroke width (default: blockplan_vertical_line_width)
          opacity      – line stroke opacity (default: blockplan_vertical_line_opacity)
          dash_array   – SVG stroke-dasharray string (default: blockplan_vertical_line_dasharray)
          fill_color   – column fill color, list of colors, or named palette; colors cycle
                         through matched segments (default: blockplan_vertical_line_fill_color)
          fill_opacity – fill opacity 0–1 (default: blockplan_vertical_line_fill_opacity)
          match        – optional dict of day-class keys (weekend / federal_holiday /
                         company_holiday / nonworkday) that filters segments to only
                         those days whose classification matches; segments spanning
                         multiple days use the starting day for classification
        """
        lines = list(getattr(config, "blockplan_vertical_lines", []) or [])
        if not lines:
            return

        band_segments: dict[str, list[_BandSegment]] = {}
        for band in bands:
            band_name = str(band.get("label", "")).strip().lower()
            if not band_name:
                continue
            band_segments[band_name] = self._build_segments(
                band, start, end, config, visible_days=visible_days, db=db
            )

        def _segment_matches_rule(seg: "_BandSegment", match: dict) -> bool:
            if not isinstance(match, dict) or not match:
                return True
            classes = classify_day(seg.start, db, config)
            return day_rule_matches(classes, match)

        _vline_fill_style = config.get_box_style("ec-vline-fill")
        _vline_style = config.get_line_style("ec-vline")
        # Warn once per misconfigured rule (by dict id) so logs aren't spammed
        # across the two passes below.
        _warned: set[int] = set()

        def _skip_reason(line: dict, band_name: str, value: str, repeat: bool) -> str | None:
            if not band_name:
                return "missing 'band' key"
            if not value and not repeat:
                return "needs 'value' or 'repeat: true'"
            if band_name not in band_segments:
                return f"band '{line.get('band') or line.get('band_label')}' not found in configured time bands"
            return None

        # --- Pass 1: column fills (drawn behind lines) ---
        for line in lines:
            if not isinstance(line, dict):
                continue
            fill_color_raw = line.get(
                "fill_color", _vline_fill_style.fill
            )
            fill_opacity = float(
                line.get("fill_opacity", _vline_fill_style.fill_opacity)
            )
            color_list = self._resolve_color_list(fill_color_raw, None, db)

            band_name = (
                str(line.get("band") or line.get("band_label") or "").strip().lower()
            )
            value = str(line.get("value") or "").strip()
            repeat = bool(line.get("repeat", False))
            reason = _skip_reason(line, band_name, value, repeat)
            if reason is not None:
                if id(line) not in _warned:
                    print(
                        f"[blockplan] vertical_lines rule skipped ({reason}): "
                        f"{line}"
                    )
                    _warned.add(id(line))
                continue
            segments = band_segments.get(band_name, [])
            if not segments:
                continue

            match_rule = line.get("match") if isinstance(line.get("match"), dict) else None
            matched_idx = 0
            for seg in segments:
                if not repeat and str(seg.label) != value:
                    continue
                if match_rule is not None and not _segment_matches_rule(seg, match_rule):
                    continue
                seg_x0 = self._boundary_x(
                    seg.start, visible_days, timeline_x, timeline_w
                )
                seg_x1 = self._boundary_x(
                    seg.end_exclusive, visible_days, timeline_x, timeline_w
                )
                seg_w = seg_x1 - seg_x0
                if seg_w > 0:
                    if color_list:
                        fill = color_list[matched_idx % len(color_list)]
                    elif isinstance(fill_color_raw, str):
                        fill = fill_color_raw
                    else:
                        fill = "none"
                    if not _is_none_color(fill):
                        self._draw_rect(
                            seg_x0,
                            top_y,
                            seg_w,
                            bottom_y - top_y,
                            fill=fill,
                            fill_opacity=fill_opacity,
                            css_class="ec-vline-fill",
                        )
                matched_idx += 1

        # --- Pass 2: vertical lines (drawn on top of fills) ---
        for line in lines:
            if not isinstance(line, dict):
                continue
            band_name = (
                str(line.get("band") or line.get("band_label") or "").strip().lower()
            )
            value = str(line.get("value") or "").strip()
            repeat = bool(line.get("repeat", False))
            reason = _skip_reason(line, band_name, value, repeat)
            if reason is not None:
                if id(line) not in _warned:
                    print(
                        f"[blockplan] vertical_lines rule skipped ({reason}): "
                        f"{line}"
                    )
                    _warned.add(id(line))
                continue
            segments = band_segments.get(band_name, [])
            if not segments:
                continue

            align = str(line.get("align", "start")).strip().lower()
            match_rule = line.get("match") if isinstance(line.get("match"), dict) else None
            for seg in segments:
                if not repeat and str(seg.label) != value:
                    continue
                if match_rule is not None and not _segment_matches_rule(seg, match_rule):
                    continue
                if align == "center":
                    x0 = self._boundary_x(
                        seg.start, visible_days, timeline_x, timeline_w
                    )
                    x1 = self._boundary_x(
                        seg.end_exclusive, visible_days, timeline_x, timeline_w
                    )
                    x = (x0 + x1) / 2.0
                elif align == "end":
                    x = self._boundary_x(
                        seg.end_exclusive, visible_days, timeline_x, timeline_w
                    )
                else:
                    x = self._boundary_x(
                        seg.start, visible_days, timeline_x, timeline_w
                    )

                stroke = str(line.get("color", _vline_style.color))
                width = float(line.get("width", _vline_style.width))
                opacity = float(
                    line.get("opacity", _vline_style.opacity)
                )
                dash = line.get(
                    "dash_array",
                    line.get("dasharray", _vline_style.dasharray),
                )
                dash_value = str(dash) if dash is not None else None
                self._draw_line(
                    x,
                    top_y,
                    x,
                    bottom_y,
                    stroke=stroke,
                    stroke_width=width,
                    stroke_opacity=opacity,
                    stroke_dasharray=dash_value,
                    css_class="ec-vline",
                )

    @staticmethod
    def _event_matches_lane(event: Event, lane: dict[str, Any]) -> bool:
        match = lane.get("match", {}) if isinstance(lane, dict) else {}
        if not isinstance(match, dict) or not match:
            return True

        def _lc(v: Any) -> str:
            return str(v or "").strip().lower()

        def _list(v: Any) -> list[str]:
            if not isinstance(v, list):
                return []
            return [_lc(x) for x in v if _lc(x)]

        wbs_prefixes = _list(match.get("wbs_prefixes"))
        if wbs_prefixes:
            wbs = _lc(event.wbs)
            if not any(wbs.startswith(prefix) for prefix in wbs_prefixes):
                return False

        groups = _list(match.get("resource_groups") or match.get("groups"))
        if groups:
            group = _lc(event.resource_group)
            if group not in groups:
                return False

        resource_terms = _list(match.get("resource_names_contains"))
        if resource_terms:
            names = _lc(event.resource_names)
            if not any(term in names for term in resource_terms):
                return False

        task_terms = _list(match.get("task_contains"))
        if task_terms:
            name = _lc(event.task_name)
            if not any(term in name for term in task_terms):
                return False

        note_terms = _list(match.get("notes_contains"))
        if note_terms:
            notes = _lc(event.notes)
            if not any(term in notes for term in note_terms):
                return False

        if "milestone" in match and bool(match.get("milestone")) != bool(
            event.milestone
        ):
            return False
        if "rollup" in match and bool(match.get("rollup")) != bool(event.rollup):
            return False

        event_type = _lc(match.get("event_type", "any"))
        if event_type == "duration" and not event.is_duration:
            return False
        if event_type == "event" and event.is_duration:
            return False

        # Priority filtering: exact list, exact int, or min/max range.
        priority_filter = match.get("priority")
        if priority_filter is not None:
            allowed = (
                [int(p) for p in priority_filter]
                if isinstance(priority_filter, list)
                else [int(priority_filter)]
            )
            if event.priority not in allowed:
                return False
        priority_min = match.get("priority_min")
        if priority_min is not None and event.priority < int(priority_min):
            return False
        priority_max = match.get("priority_max")
        if priority_max is not None and event.priority > int(priority_max):
            return False

        return True

    def _assign_events_to_lanes(
        self,
        config: "CalendarConfig",
        events: list[Event],
        lanes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for lane in lanes:
            name = str(lane.get("name", "Lane")).strip() or "Lane"
            result.append(
                {
                    "name": name,
                    "lane": lane,
                    "events": [],
                    "durations": [],
                }
            )

        mode = str(
            getattr(config, "blockplan_lane_match_mode", "first") or "first"
        ).lower()
        unmatched_events: list[Event] = []

        for event in events:
            matched = False
            for lane in result:
                if self._event_matches_lane(event, lane["lane"]):
                    matched = True
                    if event.is_duration and config.includedurations:
                        lane["durations"].append(event)
                    elif (not event.is_duration) and config.includeevents:
                        lane["events"].append(event)
                    if mode != "all":
                        break
            if not matched:
                unmatched_events.append(event)

        if config.blockplan_show_unmatched_lane and unmatched_events:
            unmatched = {
                "name": config.blockplan_unmatched_lane_name,
                "lane": {"name": config.blockplan_unmatched_lane_name},
                "events": [
                    e
                    for e in unmatched_events
                    if (not e.is_duration and config.includeevents)
                ],
                "durations": [
                    e
                    for e in unmatched_events
                    if (e.is_duration and config.includedurations)
                ],
            }
            result.append(unmatched)

        return result

    @staticmethod
    def _duration_rows(
        events: list[Event], lane_top: float, lane_bottom: float
    ) -> list[tuple[Event, int]]:
        if not events:
            return []
        ordered = sorted(
            events, key=lambda e: (e.start, e.end, e.priority, e.task_name.lower())
        )
        last_end: list[str] = []
        placed: list[tuple[Event, int]] = []
        for event in ordered:
            row = 0
            while row < len(last_end):
                if event.start > last_end[row]:
                    break
                row += 1
            if row == len(last_end):
                last_end.append(event.end)
            else:
                last_end[row] = event.end
            placed.append((event, row))
        return placed

    @staticmethod
    def _event_rows(
        events: list[Event], min_separation_days: int = 2
    ) -> list[tuple[Event, int]]:
        if not events:
            return []
        ordered = sorted(
            events, key=lambda e: (e.start, e.priority, e.task_name.lower())
        )
        last_start: list[str] = []
        placed: list[tuple[Event, int]] = []
        for event in ordered:
            row = 0
            while row < len(last_start):
                try:
                    d0 = arrow.get(last_start[row], "YYYYMMDD").date()
                    d1 = arrow.get(event.start, "YYYYMMDD").date()
                    if (d1 - d0).days >= min_separation_days:
                        break
                except Exception:
                    break
                row += 1
            if row == len(last_start):
                last_start.append(event.start)
            else:
                last_start[row] = event.start
            placed.append((event, row))
        return placed

    def _draw_swimlanes(
        self,
        *,
        config: "CalendarConfig",
        lane_defs: list[dict[str, Any]],
        start: date,
        end: date,
        visible_days: list[date],
        left_x: float,
        timeline_x: float,
        timeline_w: float,
        top_y: float,
        bottom_y: float,
    ) -> None:
        lane_count = max(1, len(lane_defs))
        total_h = max(1.0, bottom_y - top_y)
        lane_h = total_h / lane_count

        # Determine from item_placement_order which content type occupies the upper section.
        # "durations" before "events"/"milestones" → durations on top (default).
        order = list(getattr(config, "item_placement_order", None) or ["priority"])
        durations_upper = True
        for token in order:
            t = str(token).strip().lower()
            if t in ("events", "milestones"):
                durations_upper = False
                break
            if t == "durations":
                durations_upper = True
                break

        global_split_ratio = float(getattr(config, "blockplan_lane_split_ratio", 0.5))

        for idx, lane in enumerate(lane_defs):
            lane_top = top_y + (idx * lane_h)
            lane_bottom = lane_top + lane_h

            # Per-lane split_ratio overrides the global default.
            lane_cfg = lane.get("lane", {})
            raw_sr = lane_cfg.get("split_ratio", None)
            split_ratio = float(raw_sr if raw_sr is not None else global_split_ratio)
            split_ratio = max(0.0, min(1.0, split_ratio))

            # split = Y position of dividing line.
            # split_ratio = fraction of lane_h for the upper section.
            split = lane_top + lane_h * split_ratio
            show_split_line = 0.0 < split_ratio < 1.0

            # Per-lane visual style overrides (fall back to global config values).
            _lane_heading_cell_style = config.get_box_style("ec-heading-cell")
            _lg_color, _lg_w, _lg_op, _lg_dash = self._grid_stroke(config)
            heading_fill = (
                lane_cfg.get("fill_color") or _lane_heading_cell_style.fill
            )
            timeline_fill = lane_cfg.get("timeline_fill_color") or "none"

            # Lane framing
            self._draw_rect(
                left_x,
                lane_top,
                timeline_x - left_x,
                lane_h,
                fill=heading_fill,
                stroke=_lg_color,
                stroke_width=_lg_w,
                stroke_opacity=_lg_op,
                stroke_dasharray=_lg_dash,
                css_class="ec-heading-cell",
            )
            self._draw_rect(
                timeline_x,
                lane_top,
                timeline_w,
                lane_h,
                fill=timeline_fill,
                stroke=_lg_color,
                stroke_width=_lg_w,
                stroke_opacity=_lg_op,
                stroke_dasharray=_lg_dash,
                css_class="ec-band-cell",
            )
            if show_split_line:
                self._draw_line(
                    timeline_x,
                    split,
                    timeline_x + timeline_w,
                    split,
                    stroke=_lg_color,
                    stroke_width=_lg_w,
                    stroke_opacity=_lg_op,
                    stroke_dasharray=_lg_dash,
                    css_class="ec-separator",
                )

            # Lane label (single or multiline), with configurable alignment.
            self._draw_lane_label(
                config=config,
                lane_name=lane["name"],
                lane_cfg=lane_cfg,
                left_x=left_x,
                right_x=timeline_x,
                lane_bottom=lane_bottom,
                lane_top=lane_top,
            )

            durations = lane.get("durations", [])
            events = lane.get("events", [])
            if not show_split_line:
                # No divider line (ratio 0.0 or 1.0).  When both content types
                # are present, split the lane proportional to the number of rows
                # each type needs so items from different types never overlap.
                # When only one type is present, it gets the full lane.
                if durations and events:
                    dur_placed = self._duration_rows(durations, lane_top, lane_bottom)
                    dur_row_count = max((r for _, r in dur_placed), default=0) + 1
                    evt_row_count = (
                        max((r for _, r in self._event_rows(events)), default=0) + 1
                    )
                    shared_row_h = lane_h / (dur_row_count + evt_row_count)
                    if durations_upper:
                        dur_sect_top = lane_top
                        dur_sect_bot = lane_top + dur_row_count * shared_row_h
                        evt_sect_top = dur_sect_bot
                        evt_sect_bot = lane_bottom
                    else:
                        evt_sect_top = lane_top
                        evt_sect_bot = lane_top + evt_row_count * shared_row_h
                        dur_sect_top = evt_sect_bot
                        dur_sect_bot = lane_bottom
                    self._draw_lane_durations(
                        config=config,
                        events=durations,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=dur_sect_top,
                        bottom=dur_sect_bot,
                    )
                    self._draw_lane_events(
                        config=config,
                        events=events,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=evt_sect_top,
                        bottom=evt_sect_bot,
                    )
                else:
                    # Only one type present — give it the full lane.
                    self._draw_lane_durations(
                        config=config,
                        events=durations,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=lane_top,
                        bottom=lane_bottom,
                    )
                    self._draw_lane_events(
                        config=config,
                        events=events,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=lane_top,
                        bottom=lane_bottom,
                    )
            elif durations_upper:
                self._draw_lane_durations(
                    config=config,
                    events=durations,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=lane_top,
                    bottom=split,
                )
                self._draw_lane_events(
                    config=config,
                    events=events,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=split,
                    bottom=lane_bottom,
                )
            else:
                self._draw_lane_events(
                    config=config,
                    events=events,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=lane_top,
                    bottom=split,
                )
                self._draw_lane_durations(
                    config=config,
                    events=durations,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=split,
                    bottom=lane_bottom,
                )

    def _draw_lane_durations(
        self,
        *,
        config: "CalendarConfig",
        events: list[Event],
        start: date,
        end: date,
        visible_days: list[date],
        timeline_x: float,
        timeline_w: float,
        top: float,
        bottom: float,
    ) -> None:
        if not events:
            return
        rows = self._duration_rows(events, top, bottom)
        max_row = max((r for _, r in rows), default=0)
        row_count = max(1, max_row + 1)
        row_h = (bottom - top) / row_count

        for event, row in rows:
            try:
                ev_start = arrow.get(event.start, "YYYYMMDD").date()
                ev_end = arrow.get(event.end, "YYYYMMDD").date()
            except Exception:
                continue
            if ev_end < start or ev_start > end:
                continue
            draw_start = max(ev_start, start)
            draw_end = min(ev_end, end)
            x0 = self._boundary_x(draw_start, visible_days, timeline_x, timeline_w)
            x1 = self._boundary_x(
                draw_end + timedelta(days=1), visible_days, timeline_x, timeline_w
            )
            w = max(2.0, x1 - x0)
            if x1 <= x0:
                continue
            has_notes = bool(event.notes and str(event.notes).strip())
            weekly_style_with_notes = bool(config.include_notes and has_notes)

            bar_h = min(float(config.blockplan_duration_bar_height), row_h * 0.95)
            if weekly_style_with_notes:
                notes_font_size = float(config.blockplan_notes_text_font_size)
            y = top + (row * row_h) + ((row_h - bar_h) / 2.0)

            _dur_bar_style = config.get_line_style("ec-duration-bar")
            _event_name_style = config.get_text_style("ec-event-name")
            _event_notes_style = config.get_text_style("ec-event-notes")
            _palette = config.blockplan_palette or [_event_name_style.color]
            color = (
                event.color if event.color else _palette[event.priority % len(_palette)]
            )
            _dur_stroke_color = (
                config.blockplan_duration_stroke_color
                if config.blockplan_duration_stroke_color is not None
                else _dur_bar_style.color
            )
            _dur_stroke_dash = (
                config.blockplan_duration_stroke_dasharray
                if config.blockplan_duration_stroke_dasharray is not None
                else _dur_bar_style.dasharray
            )
            self._draw_rect(
                x0,
                y,
                w,
                bar_h,
                fill=color,
                fill_opacity=config.blockplan_duration_fill_opacity,
                stroke=_dur_stroke_color,
                stroke_opacity=float(config.blockplan_duration_stroke_opacity),
                stroke_width=float(config.blockplan_duration_stroke_width),
                stroke_dasharray=_dur_stroke_dash,
                css_class="ec-duration-bar",
            )
            has_dates = bool(
                config.blockplan_duration_show_start_date
                or config.blockplan_duration_show_end_date
            )
            _dur_date_style = config.get_text_style("ec-duration-date")
            if has_dates:
                date_font_size = float(config.blockplan_duration_date_font_size)
                date_baseline_y = y + bar_h + date_font_size
                date_color = _dur_date_style.color
                date_fmt = config.blockplan_duration_date_format
                date_font = _dur_date_style.font
                try:
                    _dur_date_font_path = get_font_path(date_font)
                except Exception:
                    _dur_date_font_path = ""
            dur_text_color = _event_name_style.color
            dur_notes_color = _event_notes_style.color
            _dur_notes_font_name = _event_notes_style.font
            show_icon = bool(config.blockplan_duration_icon_visible) and bool(
                event.icon
            )

            # --- shared icon-layout helper ---
            def _draw_icon_and_text(
                baseline_y: float, font_size: float, max_w: float
            ) -> None:
                """Draw icon (if show_icon) + task name on a single baseline row."""
                if show_icon:
                    icon_size = font_size
                    try:
                        _fp = get_font_path(_event_name_style.font)
                        text_w = string_width(event.task_name, _fp, font_size)
                    except Exception:
                        text_w = len(event.task_name) * font_size * 0.55
                    gap = 2.0
                    total_w = icon_size + gap + text_w
                    available_w = max(8.0, max_w)
                    icon_scale_x = (
                        min(1.0, available_w / total_w)
                        if total_w > available_w
                        else 1.0
                    )
                    effective_icon_w = icon_size * icon_scale_x
                    group_x0 = (
                        x0
                        + (
                            w
                            - (
                                effective_icon_w
                                + gap
                                + min(
                                    text_w * icon_scale_x,
                                    available_w - effective_icon_w - gap,
                                )
                            )
                        )
                        / 2.0
                    )
                    draw_x = max(x0, group_x0)
                    icon_transform = None
                    if icon_scale_x < 1.0:
                        icon_transform = (
                            f"translate({draw_x:.4f} {baseline_y:.4f}) "
                            f"scale({icon_scale_x:.6f} 1) "
                            f"translate({-draw_x:.4f} {-baseline_y:.4f})"
                        )
                    icon_drawn = self._draw_icon_svg(
                        event.icon,
                        draw_x,
                        baseline_y,
                        icon_size,
                        anchor="start",
                        color=dur_text_color,
                        fallback_name=config.default_missing_icon,
                        fallback_color=dur_text_color,
                        transform=icon_transform,
                        css_class="ec-event-icon",
                    )
                    text_x = (
                        draw_x + effective_icon_w + gap
                        if icon_drawn
                        else x0 + (w / 2.0)
                    )
                    self._draw_text(
                        text_x,
                        baseline_y,
                        event.task_name,
                        _event_name_style.font,
                        font_size,
                        fill=dur_text_color,
                        anchor="start" if icon_drawn else "middle",
                        max_width=max(8.0, x0 + w - text_x - 2),
                        css_class="ec-event-name",
                    )
                else:
                    self._draw_text(
                        x0 + (w / 2.0),
                        baseline_y,
                        event.task_name,
                        _event_name_style.font,
                        font_size,
                        fill=dur_text_color,
                        anchor="middle",
                        max_width=max(8.0, max_w),
                        css_class="ec-event-name",
                    )

            if weekly_style_with_notes:
                _draw_icon_and_text(y + (bar_h * 0.42), notes_font_size, w - 4)
                self._draw_text(
                    x0 + (w / 2.0),
                    y + (bar_h * 0.80),
                    str(event.notes),
                    _dur_notes_font_name,
                    float(config.blockplan_notes_text_font_size),
                    fill=dur_notes_color,
                    anchor="middle",
                    max_width=max(8.0, w - 4),
                    css_class="ec-event-notes",
                )
            else:
                _draw_icon_and_text(
                    y + (bar_h * 0.80),
                    float(config.blockplan_name_text_font_size),
                    w - 4,
                )


            # --- Date row (outside bar, below rectangle) — shared for both layout modes ---
            if has_dates:
                show_start = config.blockplan_duration_show_start_date
                show_end = config.blockplan_duration_show_end_date
                both = show_start and show_end
                half_w = max(8.0, w / 2.0 - 4)

                start_label = end_label = ""
                if show_start:
                    try:
                        start_label = arrow.get(ev_start).format(date_fmt)
                    except Exception:
                        start_label = str(ev_start)
                if show_end:
                    try:
                        end_label = arrow.get(ev_end).format(date_fmt)
                    except Exception:
                        end_label = str(ev_end)

                # Compute a shared scale so both dates squish uniformly.
                shared_scale = 1.0
                if both and _dur_date_font_path:
                    s_w = (
                        string_width(start_label, _dur_date_font_path, date_font_size)
                        if start_label
                        else 0.0
                    )
                    e_w = (
                        string_width(end_label, _dur_date_font_path, date_font_size)
                        if end_label
                        else 0.0
                    )
                    scale_s = min(1.0, half_w / s_w) if s_w > half_w else 1.0
                    scale_e = min(1.0, half_w / e_w) if e_w > half_w else 1.0
                    shared_scale = min(scale_s, scale_e)

                if show_start:
                    sx = x0 + 2.0
                    xform = None
                    if both and shared_scale < 1.0:
                        xform = (
                            f"translate({sx:.4f} {date_baseline_y:.4f}) "
                            f"scale({shared_scale:.6f} 1) "
                            f"translate({-sx:.4f} {-date_baseline_y:.4f})"
                        )
                    self._draw_text(
                        sx,
                        date_baseline_y,
                        start_label,
                        date_font,
                        date_font_size,
                        fill=date_color,
                        anchor="start",
                        max_width=None if both else half_w,
                        transform=xform,
                        css_class="ec-duration-date",
                    )
                if show_end:
                    ex = x0 + w - 2.0
                    xform = None
                    if both and shared_scale < 1.0:
                        xform = (
                            f"translate({ex:.4f} {date_baseline_y:.4f}) "
                            f"scale({shared_scale:.6f} 1) "
                            f"translate({-ex:.4f} {-date_baseline_y:.4f})"
                        )
                    self._draw_text(
                        ex,
                        date_baseline_y,
                        end_label,
                        date_font,
                        date_font_size,
                        fill=date_color,
                        anchor="end",
                        max_width=None if both else half_w,
                        transform=xform,
                        css_class="ec-duration-date",
                    )

    def _draw_lane_events(
        self,
        *,
        config: "CalendarConfig",
        events: list[Event],
        start: date,
        end: date,
        visible_days: list[date],
        timeline_x: float,
        timeline_w: float,
        top: float,
        bottom: float,
    ) -> None:
        if not events or self._drawing is None:
            return

        ordered = sorted(
            events, key=lambda e: (e.start, e.priority, e.task_name.lower())
        )
        _evt_name_style = config.get_text_style("ec-event-name")
        _evt_notes_style = config.get_text_style("ec-event-notes")
        _evt_date_style = config.get_text_style("ec-event-date")
        event_size = float(config.blockplan_name_text_font_size)
        notes_size = float(config.blockplan_notes_text_font_size)
        date_size = float(
            config.blockplan_event_date_font_size or max(6.0, event_size * 0.9)
        )
        show_date = bool(getattr(config, "blockplan_event_show_date", False))
        icon_r = max(1.5, float(config.blockplan_marker_radius))
        try:
            event_font_path = get_font_path(_evt_name_style.font)
        except Exception:
            event_font_path = ""
        _event_notes_font_name = _evt_notes_style.font
        try:
            notes_font_path = get_font_path(_event_notes_font_name)
        except Exception:
            notes_font_path = event_font_path
        try:
            date_font_path = get_font_path(_evt_date_style.font)
        except Exception:
            date_font_path = event_font_path

        # Each row keeps the occupied [x0,x1] spans already placed on that row.
        row_spans: list[list[tuple[float, float]]] = []
        placements: list[tuple[Event, int, float, bool, bool, str]] = []
        visible_set = set(visible_days)

        for event in ordered:
            try:
                ev_day = arrow.get(event.start, "YYYYMMDD").date()
            except Exception:
                continue
            if ev_day < start or ev_day > end:
                continue
            if ev_day not in visible_set:
                continue
            x = self._boundary_x(ev_day, visible_days, timeline_x, timeline_w)
            has_notes = bool(
                config.include_notes and event.notes and str(event.notes).strip()
            )
            has_date = show_date
            date_text = ""
            if has_date:
                try:
                    date_text = arrow.get(event.start, "YYYYMMDD").format(
                        config.blockplan_event_date_format
                    )
                except Exception:
                    date_text = str(event.start)
            name_w = (
                string_width(event.task_name, event_font_path, event_size)
                if event_font_path
                else (len(event.task_name) * event_size * 0.55)
            )
            notes_w = (
                string_width(str(event.notes), notes_font_path, notes_size)
                if (has_notes and notes_font_path)
                else (len(str(event.notes or "")) * notes_size * 0.52)
            )
            date_w = (
                string_width(date_text, date_font_path, date_size)
                if (has_date and date_font_path)
                else (len(date_text) * date_size * 0.52)
            )
            label_w = max(
                name_w, notes_w if has_notes else 0.0, date_w if has_date else 0.0
            )
            span_x0 = x - icon_r - 2.0
            span_x1 = x + icon_r + 4.0 + label_w
            pad = 4.0

            target_row = 0
            while True:
                if target_row >= len(row_spans):
                    row_spans.append([])
                overlaps = any(
                    not ((span_x1 + pad) <= x0 or span_x0 >= (x1 + pad))
                    for x0, x1 in row_spans[target_row]
                )
                if not overlaps:
                    row_spans[target_row].append((span_x0, span_x1))
                    placements.append(
                        (event, target_row, x, has_notes, has_date, date_text)
                    )
                    break
                target_row += 1

        row_count = max(1, len(row_spans))
        row_h = (bottom - top) / row_count

        for event, row, x, has_notes, has_date, date_text in placements:
            y_center = top + ((row + 0.5) * row_h)
            marker_drawn = False
            icon_size = max(6.0, event_size * 1.1)
            if has_notes and has_date:
                name_baseline = y_center - (event_size * 0.70)
                notes_baseline = y_center + (notes_size * 0.15)
                date_baseline = y_center + (notes_size * 1.30)
            elif has_notes:
                date_baseline = None
                name_baseline = y_center - (event_size * 0.35)
                notes_baseline = y_center + (notes_size * 0.85)
            elif has_date:
                name_baseline = y_center - (event_size * 0.20)
                date_baseline = y_center + (date_size * 1.00)
                notes_baseline = None
            else:
                date_baseline = None
                name_baseline = y_center + (event_size * 0.35)
                notes_baseline = None
            if event.icon:
                marker_drawn = self._draw_icon_svg(
                    event.icon,
                    x,
                    name_baseline,
                    icon_size,
                    anchor="start",
                    color=_evt_name_style.color,
                    fallback_name=config.default_missing_icon,
                    fallback_color="red",
                    css_class="ec-event-icon",
                )

            if not marker_drawn:
                _circle = drawsvg.Circle(
                    x,
                    y_center,
                    icon_r,
                    fill=_evt_name_style.color,
                    stroke=_evt_name_style.color,
                    class_="ec-milestone-marker",
                )
                self._drawing.append(_circle)
            marker_extent = icon_size if marker_drawn else icon_r
            label_x = x + marker_extent + 2.0
            max_width = max(8.0, (timeline_x + timeline_w) - x - 6)
            if has_date and date_baseline is not None:
                self._draw_text(
                    label_x,
                    date_baseline,
                    date_text,
                    _evt_date_style.font,
                    date_size,
                    fill=_evt_date_style.color,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-date",
                )
            if has_notes:
                self._draw_text(
                    label_x,
                    name_baseline,
                    event.task_name,
                    _evt_name_style.font,
                    event_size,
                    fill=_evt_name_style.color,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-name",
                )
                self._draw_text(
                    label_x,
                    notes_baseline
                    if notes_baseline is not None
                    else y_center - (notes_size * 0.85),
                    str(event.notes),
                    _event_notes_font_name,
                    notes_size,
                    fill=_evt_notes_style.color,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-notes",
                )
            else:
                self._draw_text(
                    label_x,
                    name_baseline,
                    event.task_name,
                    _evt_name_style.font,
                    event_size,
                    fill=_evt_name_style.color,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-name",
                )

    @staticmethod
    def _visible_days(start: date, end: date, weekend_style: int) -> list[date]:
        days: list[date] = []
        cursor = start
        while cursor <= end:
            if weekend_style == 0:
                if cursor.weekday() < 5:
                    days.append(cursor)
            else:
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

    @staticmethod
    def _boundary_x(
        day: date,
        visible_days: list[date],
        timeline_x: float,
        timeline_w: float,
    ) -> float:
        # Boundary position is the count of visible days strictly before 'day'.
        count = bisect_left(visible_days, day)
        total = max(1, len(visible_days))
        ratio = max(0.0, min(1.0, count / total))
        return timeline_x + (ratio * timeline_w)

    def _draw_lane_label(
        self,
        *,
        config: "CalendarConfig",
        lane_name: str,
        lane_cfg: dict[str, Any],
        left_x: float,
        right_x: float,
        lane_bottom: float,
        lane_top: float,
    ) -> None:
        text = str(lane_name or "")
        lines = [ln for ln in text.splitlines() if ln != ""]
        if not lines:
            return

        fs = float(
            config.blockplan_lane_label_font_size or config.weekly_name_text_font_size or 9.0
        )
        line_gap = fs * 1.20
        total_baseline_span = (len(lines) - 1) * line_gap

        # ── rotation ───────────────────────────────────────────────────────────
        raw_rot = lane_cfg.get("label_rotation")
        if raw_rot is None:
            raw_rot = config.blockplan_lane_label_rotation
        rotation = float(raw_rot or 0.0)
        cell_cx = (left_x + right_x) / 2.0
        cell_cy = (lane_top + lane_bottom) / 2.0
        xform = (
            f"rotate({rotation:.6g},{cell_cx:.4f},{cell_cy:.4f})" if rotation else None
        )
        # For ±90° rotations the text runs along the lane height, so clamp
        # max_width to the lane height rather than the narrow column width.
        cross_axis = 45.0 < abs(rotation % 180.0) < 135.0

        align_h = (
            str(
                lane_cfg.get("label_align_h", config.blockplan_lane_label_align_h)
                or config.blockplan_lane_label_align_h
            )
            .strip()
            .lower()
        )
        align_v = (
            str(
                lane_cfg.get("label_align_v", config.blockplan_lane_label_align_v)
                or config.blockplan_lane_label_align_v
            )
            .strip()
            .lower()
        )
        if align_h not in {"left", "center", "right"}:
            align_h = "left"
        if align_v not in {"top", "middle", "bottom"}:
            align_v = "middle"

        if align_h == "center":
            x = left_x + ((right_x - left_x) * 0.5)
            anchor = "middle"
        elif align_h == "right":
            x = right_x - 6.0
            anchor = "end"
        else:
            x = left_x + 6.0
            anchor = "start"

        if align_v == "top":
            first_baseline = lane_top + (fs * 0.85)
        elif align_v == "bottom":
            last_baseline = lane_bottom - (fs * 0.25)
            first_baseline = last_baseline - total_baseline_span
        else:
            lane_mid = (lane_top + lane_bottom) / 2.0
            first_baseline = lane_mid - (total_baseline_span * 0.5)

        _lane_label_style = config.get_text_style("ec-heading")
        label_color = lane_cfg.get("label_color") or _lane_label_style.color
        max_width = (
            max(8.0, lane_bottom - lane_top - 10.0)
            if cross_axis
            else max(8.0, right_x - left_x - 10.0)
        )
        for i, line in enumerate(lines):
            y = first_baseline + (i * line_gap)
            self._draw_text(
                x,
                y,
                line,
                _lane_label_style.font,
                fs,
                fill=label_color,
                anchor=anchor,
                max_width=max_width,
                transform=xform,
                css_class="ec-heading",
            )

    @staticmethod
    def _normalize_halign(value: str | None, default: str = "left") -> str:
        v = str(value or default).strip().lower()
        return v if v in {"left", "center", "right"} else default
