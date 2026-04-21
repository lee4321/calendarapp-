"""
Weekly calendar SVG renderer.

Renders weekly calendar visualization using drawsvg for SVG generation.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

import drawsvg

import arrow

from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import shrinktext, string_width
from shared.date_utils import get_week_number
from shared.data_models import Event
from shared.day_classifier import classify_day
from shared.rule_engine import DayContext, StyleResult, StyleEngine
from shared.fiscal_renderer import (
    get_fiscal_period_color,
    format_fiscal_period_label,
    format_fiscal_period_end_label,
)
from config.config import (
    FONT_REGISTRY,
    FederalHolidayColor,
    FederalHolidayAlpha,
    CompanyHolidayColor,
    CompanyHolidayAlpha,
    get_font_path,
    weekend_style_is_workweek,
    weekend_style_starts_sunday,
    weekend_style_starts_monday,
    monthcolors,
    hashlinecolor,
    Resource_Group_colors,
    resolve_page_margins,
)

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict, VisualizationResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OverflowEntry:
    """Record of an event or duration that could not fit on the calendar."""

    start: str  # YYYYMMDD
    end: str  # YYYYMMDD
    task_name: str
    datekey: str  # The daykey where overflow was detected


class WeeklyCalendarRenderer(BaseSVGRenderer):
    """
    Renderer for weekly calendar visualization.

    Produces an SVG with a grid of day boxes, events placed on days,
    and multi-day durations spanning across boxes.
    """

    def __init__(self):
        """Initialize the renderer with pattern caching state."""
        super().__init__()
        self._pattern_svg_cache: dict[str, str] = {}
        self._registered_pattern_ids: set[str] = set()

    def _build_day_boxes(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        db: CalendarDB,
        adjustedstart: arrow.Arrow,
        adjustedend: arrow.Arrow,
        events_by_day: dict[str, list[Event]],
    ) -> tuple[list[str], dict]:
        """
        First pass: draw all day boxes and return visible day keys and row coords.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            db: Database access instance
            adjustedstart: Calendar start as arrow object
            adjustedend: Calendar end as arrow object
            events_by_day: Events keyed by YYYYMMDD for style rule evaluation

        Returns:
            Tuple of (days_to_print list, rows_on_days dict)
        """
        rows_on_days = defaultdict(dict)
        days_to_print = []
        style_engine = StyleEngine(config.theme_style_rules or [])

        for oneday in arrow.Arrow.range("day", adjustedstart, adjustedend):
            daykey = oneday.format("YYYYMMDD")

            # Not all days may be on calendar (weekends may be hidden)
            if daykey not in coordinates:
                continue

            X, Y, W, H = coordinates[daykey]
            days_to_print.append(daykey)

            dbc = self._day_box_coords(config, X, Y, W, H)
            rows_on_days[daykey] = dbc["Row_Coords"]

            shadespecialday = self._get_special_markings(daykey, db, config.country)
            daytitle, dayicon = self._get_special_day_title(daykey, db, config.country)

            day_classes = classify_day(oneday.date(), db, config)
            ctx = DayContext(
                date=daykey,
                federal_holiday="federal_holiday" in day_classes,
                company_holiday="company_holiday" in day_classes,
                nonworkday=bool(day_classes),
                workday=not bool(day_classes),
                weekend="weekend" in day_classes,
            )
            style_result = style_engine.evaluate_day(ctx, events_by_day.get(daykey, []))

            self._draw_day_box(
                config,
                oneday,
                X,
                Y,
                W,
                H,
                daytitle,
                dayicon,
                shadespecialday,
                style_result=style_result,
            )

        return days_to_print, rows_on_days

    @staticmethod
    def _placement_sort_key(event: Event, order: list[str]) -> tuple:
        """Return a sort key for event placement ordering.

        Args:
            event: The Event to classify.
            order: List of placement tokens.  Type tokens ("milestones",
                   "events", "durations") define grouping rank by their
                   position in the list.  Special tokens "priority" and
                   "alphabetical" control the secondary sort within groups.
        """
        is_milestone = event.milestone
        is_duration = event.start != event.end
        # An "event" is single-day and not a milestone
        is_event = not is_milestone and not is_duration

        # Map this event to its type token
        if is_milestone:
            event_type = "milestones"
        elif is_duration:
            event_type = "durations"
        else:
            event_type = "events"

        # Derive type rank from the ordered list (ignoring special tokens)
        type_tokens = [o for o in order if o in ("milestones", "events", "durations")]
        if type_tokens:
            # Events whose type is not listed go after all listed types
            type_rank = (
                type_tokens.index(event_type)
                if event_type in type_tokens
                else len(type_tokens)
            )
        else:
            # No type tokens (e.g. ["priority"] or ["alphabetical"]) — no grouping
            type_rank = 0

        name = (event.task_name or "").lower()
        if "alphabetical" in order:
            return (type_rank, name)
        return (type_rank, event.priority, name)

    def _place_all_events(
        self,
        config: CalendarConfig,
        event_objects: list[Event],
        days_to_print: list[str],
        rows_on_days: dict,
    ) -> tuple[dict, int, list[OverflowEntry]]:
        """
        Second pass: place events and durations onto the calendar.

        Args:
            config: Calendar configuration
            event_objects: Normalized Event objects
            days_to_print: List of visible day keys
            rows_on_days: Row availability dict (mutated in place)

        Returns:
            Tuple of (rows_on_days, overflow_count, overflow_entries)
        """
        overflow_count = 0
        overflow_entries: list[OverflowEntry] = []

        order = config.item_placement_order
        if order != ["priority"]:
            event_objects = sorted(
                event_objects,
                key=lambda e: self._placement_sort_key(e, order),
            )

        for t in event_objects:
            daystart = arrow.get(arrow.get(t.start).date())
            dayend = arrow.get(arrow.get(t.end).date())

            if t.notes and t.notes in ("HOLIDAY", "USFederal", "CanFED"):
                continue

            if config.ignorecomplete and t.percent_complete == 1:
                continue

            if config.milestones and t.milestone:
                if t.datekey in days_to_print:
                    rows_on_days, had_overflow = self._place_event_and_notes(
                        config, rows_on_days, t, t.datekey
                    )
                    if had_overflow:
                        overflow_count += 1
                        overflow_entries.append(
                            OverflowEntry(
                                start=t.start,
                                end=t.end,
                                task_name=t.task_name or "",
                                datekey=t.datekey,
                            )
                        )

            elif (
                (daystart == dayend)
                and config.includeevents
                and (t.task_name and t.task_name.strip())
            ):
                if t.datekey in days_to_print:
                    rows_on_days, had_overflow = self._place_event_and_notes(
                        config, rows_on_days, t, t.datekey
                    )
                    if had_overflow:
                        overflow_count += 1
                        overflow_entries.append(
                            OverflowEntry(
                                start=t.start,
                                end=t.end,
                                task_name=t.task_name or "",
                                datekey=t.datekey,
                            )
                        )

            elif (daystart != dayend) and config.includedurations:
                rows_on_days, had_overflow = self._place_duration(
                    config, days_to_print, rows_on_days, t, t.datekey
                )
                if had_overflow:
                    overflow_count += 1
                    overflow_entries.append(
                        OverflowEntry(
                            start=t.start,
                            end=t.end,
                            task_name=t.task_name or "",
                            datekey=t.datekey,
                        )
                    )

        return rows_on_days, overflow_count, overflow_entries

    def _render_content(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list[OverflowEntry]]:
        """
        Render weekly calendar content.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            events: Event list
            db: Database access instance

        Returns:
            Tuple of (overflow_count, list of OverflowEntry records)
        """
        adjustedstart = arrow.get(config.adjustedstart, "YYYYMMDD")
        adjustedend = arrow.get(config.adjustedend, "YYYYMMDD")
        event_objects = [Event.from_dict(e) for e in events]

        # Preload all SVG patterns and reset per-page def registry.
        self._pattern_svg_cache = db.get_all_patterns()
        self._registered_pattern_ids = set()
        self._load_icon_svg_cache(db)

        events_by_day = self._build_events_by_day(
            config,
            event_objects,
            adjustedstart,
            adjustedend,
        )

        days_to_print, rows_on_days = self._build_day_boxes(
            config, coordinates, db, adjustedstart, adjustedend, events_by_day
        )

        rows_on_days, overflow_count, overflow_entries = self._place_all_events(
            config, event_objects, days_to_print, rows_on_days
        )

        overflow_entries.sort(key=lambda e: (e.start, e.end, e.task_name))
        return overflow_count, overflow_entries

    def _day_box_coords(
        self,
        config: CalendarConfig,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> dict:
        """
        Calculate positions of individual elements within a single day box.

        Args:
            config: Calendar configuration
            x: X coordinate of day box
            y: Y coordinate of day box
            width: Width of day box
            height: Height of day box

        Returns:
            Dict with coordinates for Number, Event positions, Row_Coords, etc.
        """
        textrowheight = round(config.weekly_name_text_font_size * 1.3, 2)
        daynumheight = config.day_box_number_font_size

        # All Y coordinates are in SVG space: y is the TOP edge of the day box,
        # y + height is the BOTTOM edge, and Y increases downward.
        numX = round((x + width) - (config.day_box_number_font_size * 0.25), 2)
        numY = round(y + (config.day_box_number_font_size * 0.9), 2)

        monthX = round(x + (width * 0.1), 2)
        monthY = round(y + textrowheight, 2)

        eventIconX = round(x + (width * 0.01), 2)
        eventIconY = round(numY + (textrowheight * 1.1), 2)

        eventTextX = round(eventIconX + (textrowheight * 1.1), 2)
        eventTextY = eventIconY
        eventTextWidth = round(width - (textrowheight * 2.1), 2)

        overflowindicatorX = eventIconX
        overflowindicatorY = round(numY - (textrowheight / 2), 2)

        dayIconX = overflowindicatorX
        dayIconY = overflowindicatorY
        dayNameX = round(dayIconX + (textrowheight * 1.1), 2)
        dayNameY = dayIconY

        # Calculate virtual rows for events and durations
        MaxRows = int((height - daynumheight - (textrowheight * 0.2)) / textrowheight)
        config.maxrows = MaxRows

        Row_Coords = {}
        Y = eventTextY
        H = textrowheight
        iconx = eventIconX
        textx = eventTextX
        # In SVG space, text baseline sits ~80% from the top of the row
        # (equivalent to 20% from the bottom in the original PDF convention).
        texty = Y + (textrowheight * 0.8)
        icony = texty

        for r in range(MaxRows):
            coord_tuple = (x, Y, width, H, textx, texty, iconx, icony, False)
            Row_Coords[r] = coord_tuple
            Y = round(Y + textrowheight, 2)
            texty = Y + (textrowheight * 0.8)
            icony = texty

        return {
            "Number": (numX, numY),
            "Day_Icon": (dayIconX, dayIconY),
            "Event_Icon": (eventIconX, eventIconY),
            "Event_Text": (eventTextX, eventTextY),
            "Day_Name": (dayNameX, dayNameY),
            "Overflow": (overflowindicatorX, overflowindicatorY),
            "MaxRows": MaxRows,
            "Row_Coords": Row_Coords,
        }

    def _get_special_markings(
        self,
        daykey: str,
        db: CalendarDB,
        country: str | None = None,
    ) -> str:
        """
        Get special markings for a day that affect shading.

        Args:
            daykey: Date in YYYYMMDD format
            db: CalendarDB instance
            country: Country code filter for government holiday lookup

        Returns:
            shadespecialday is "government", "company", or "" (no shade)
        """
        shadespecialday = ""

        # Government holidays take priority
        if db.is_government_nonworkday(daykey, country):
            shadespecialday = "government"

        # Company special days (only if not already a government nonworkday)
        markings = db.get_special_markings_for_date(daykey)
        if not shadespecialday and markings.get("nonworkday", False):
            shadespecialday = "company"

        return shadespecialday

    def _get_special_day_title(
        self,
        daykey: str,
        db: CalendarDB,
        country: str | None = None,
    ) -> tuple[str | bool, str]:
        """
        Determine if this day is a special day (holiday) and get its title.

        Args:
            daykey: Date in YYYYMMDD format
            db: CalendarDB instance
            country: Country code filter; None selects all countries.

        Returns:
            Tuple of (daytitle: str|False, dayicon: str)
        """
        daytitle = False
        dayicon = ""

        title, icon = db.get_holiday_title_for_date(daykey, country)
        if title:
            daytitle = title
            dayicon = icon or ""

        return daytitle, dayicon

    def _build_events_by_day(
        self,
        config: CalendarConfig,
        event_objects: list[Event],
        adjustedstart: arrow.Arrow,
        adjustedend: arrow.Arrow,
    ) -> dict[str, list[Event]]:
        """Build a mapping from YYYYMMDD datekey to Event objects present on that day."""
        result: dict[str, list[Event]] = defaultdict(list)

        for t in event_objects:
            daystart = arrow.get(arrow.get(t.start).date())
            dayend = arrow.get(arrow.get(t.end).date())

            span_start = max(daystart, adjustedstart)
            span_end = min(dayend, adjustedend)
            if span_end < span_start:
                continue

            if t.milestone and config.milestones:
                day_key = t.datekey or daystart.format("YYYYMMDD")
                result[day_key].append(t)
            elif daystart == dayend and config.includeevents:
                day_key = t.datekey or daystart.format("YYYYMMDD")
                result[day_key].append(t)
            elif daystart != dayend and config.includedurations:
                for oneday in arrow.Arrow.range("day", span_start, span_end):
                    result[oneday.format("YYYYMMDD")].append(t)

        return dict(result)

    def _resolve_day_box_fill(
        self,
        config: CalendarConfig,
        oneday_str: str,
        month: str,
        shadespecialday: str | bool,
    ) -> tuple[str, float]:
        """Return (fill_color, fill_opacity) for a day box."""
        _monthcolors = config.theme_month_colors or monthcolors

        if shadespecialday == "government":
            fill_color = config.theme_federal_holiday_color or FederalHolidayColor
            fill_alpha = config.theme_federal_holiday_alpha
            fill_opacity = fill_alpha if fill_alpha is not None else FederalHolidayAlpha
        elif shadespecialday:
            fill_color = config.theme_company_holiday_color or CompanyHolidayColor
            fill_alpha = config.theme_company_holiday_alpha
            fill_opacity = fill_alpha if fill_alpha is not None else CompanyHolidayAlpha
        elif config.fiscal_use_period_colors and config.fiscal_lookup:
            fiscal_info = config.fiscal_lookup.get(oneday_str)
            if fiscal_info:
                fill_color = get_fiscal_period_color(fiscal_info, config)
            else:
                fill_color = _monthcolors[month]
            fill_opacity = 0.50
        else:
            fill_color = _monthcolors[month]
            fill_opacity = 0.50

        # Shade current day if option enabled (applied last, overrides above)
        if config.shade_current_day:
            today = arrow.now().format("YYYYMMDD")
            if today == oneday_str:
                fill_color = "lightblue"
                fill_opacity = 0.25

        return fill_color, fill_opacity

    def _build_day_number_label(
        self,
        config: CalendarConfig,
        oneday: arrow.Arrow,
        oneday_str: str,
    ) -> str:
        """Build the day number string with optional month indicator prefix."""
        boxdate = oneday.format("D")
        monthname = oneday.format("MMM")
        dayoftheweek = oneday.format("ddd")

        month_indicator = ""
        if config.include_month_name:
            month_indicator = monthname + " "

        if boxdate == "1":
            boxdate = month_indicator + boxdate
        elif oneday_str == config.adjustedstart:
            boxdate = month_indicator + boxdate
        elif (
            weekend_style_is_workweek(config.weekend_style)
            and (boxdate == "2" or boxdate == "3")
            and (dayoftheweek == "Mon")
        ):
            boxdate = month_indicator + boxdate

        return boxdate

    def _draw_fiscal_label(
        self,
        config: CalendarConfig,
        oneday: arrow.Arrow,
        oneday_str: str,
        dbc: dict,
        label_x: float,
    ) -> float:
        """Draw fiscal period label on the left side of the day number row.

        Returns the pixel width of the drawn label (0.0 if nothing drawn).
        """
        if not (config.fiscal_lookup and config.fiscal_show_period_labels):
            return 0.0

        fiscal_info = config.fiscal_lookup.get(oneday_str)
        is_week_start = (
            oneday.isoweekday() == 7
            if weekend_style_starts_sunday(config.weekend_style)
            else oneday.isoweekday() == 1
        )

        # If weeks start on Monday but fiscal period starts on Sunday,
        # render the label in the first column (Monday) instead.
        if (
            not (fiscal_info and fiscal_info.is_period_start)
            and is_week_start
            and not weekend_style_starts_sunday(config.weekend_style)
        ):
            prev_day = oneday.shift(days=-1)
            prev_info = config.fiscal_lookup.get(prev_day.format("YYYYMMDD"))
            if prev_info and prev_info.is_period_start:
                fiscal_info = prev_info

        is_period_end = False
        if fiscal_info:
            next_day = oneday.shift(days=1)
            next_info = config.fiscal_lookup.get(next_day.format("YYYYMMDD"))
            is_period_end = (
                next_info is None
                or next_info.fiscal_period != fiscal_info.fiscal_period
            )

        label_parts = []
        if fiscal_info and fiscal_info.is_period_start:
            label_parts.append(format_fiscal_period_label(fiscal_info, config))

        if fiscal_info and is_period_end:
            label_parts.append(format_fiscal_period_end_label(fiscal_info, config))

        if not label_parts:
            return 0.0

        fiscal_label = " ".join(label_parts).strip()
        label_font_size = (
            config.fiscal_period_label_font_size
            or config.day_box_number_font_size * 0.7
        )
        label_y = dbc["Number"][1]
        _ts_fiscal = config.get_text_style("ec-fiscal-label")
        font_path = get_font_path(_ts_fiscal.font)
        label_width = 0.0
        if font_path:
            label_width = string_width(fiscal_label, font_path, label_font_size)
        self._draw_text(
            label_x,
            label_y,
            fiscal_label,
            _ts_fiscal.font,
            label_font_size,
            fill=_ts_fiscal.color,
            css_class="ec-fiscal-label",
        )
        return label_width

    def _draw_week_number_label(
        self,
        config: CalendarConfig,
        oneday: arrow.Arrow,
        y1: float,
        box_left: float,
        label_x: float,
        label_width: float,
    ) -> None:
        """Draw week number on week-start days at the same baseline as the day number."""
        if not (config.include_week_numbers and config.week_number_font_size):
            return

        week_start_sunday = weekend_style_starts_sunday(config.weekend_style)
        is_week_start = (
            oneday.isoweekday() == 7 if week_start_sunday else oneday.isoweekday() == 1
        )
        if not is_week_start:
            return

        anchor = None
        if config.week_number_mode == "custom" and config.week1_start:
            try:
                anchor = arrow.get(config.week1_start, "YYYYMMDD")
            except Exception:
                anchor = None
        week_num = get_week_number(
            oneday,
            mode=config.week_number_mode,
            anchor=anchor,
        )
        if week_num <= 0:
            return

        try:
            week_text = config.week_number_label_format.format(num=week_num)
        except (KeyError, ValueError):
            week_text = f"W{week_num:02d}"
        margins = resolve_page_margins(config)
        if margins["left"] > 0:
            wn_x = box_left - 2.0
            anchor = "end"
        else:
            gap = config.day_box_number_font_size * 0.3
            wn_x = label_x + (label_width + gap if label_width else 0.0)
            anchor = "start"
        _ts_wn = config.get_text_style("ec-week-number")
        self._draw_text(
            wn_x,
            y1,
            week_text,
            _ts_wn.font,
            config.week_number_font_size,
            fill=_ts_wn.color,
            anchor=anchor,
            css_class="ec-week-number",
        )

    def _draw_special_day_title(
        self,
        config: CalendarConfig,
        dbc: dict,
        x1: float,
        X: float,
        baseline_y: float,
        daytitle: str | bool,
        dayicon: str,
        day_num_rendered_width: float = 0.0,
    ) -> None:
        """Draw special day (holiday) title text and icon in the day box.

        baseline_y is the shared text baseline for this row (same as the day
        number), so the title and icon are baseline-aligned with the day number.
        """
        if not daytitle:
            return

        _ts_ht = config.get_text_style("ec-holiday-title")
        _is_ei = config.get_icon_style("ec-event-icon")
        x1_name, _ = dbc["Day_Name"]
        gap = config.day_box_number_font_size * 0.15
        available_right = x1 - day_num_rendered_width - gap
        daytitlewidth = max(available_right - x1_name, 0.0)
        font_path = get_font_path(_ts_ht.font)
        fontsize = shrinktext(
            daytitle,
            daytitlewidth,
            font_path,
            config.weekly_name_text_font_size,
        )
        self._draw_text(
            x1_name,
            baseline_y,
            daytitle,
            _ts_ht.font,
            fontsize,
            fill=_ts_ht.color,
            css_class="ec-holiday-title",
        )

        x1_icon, _ = dbc["Day_Icon"]
        self._draw_icon_svg(
            dayicon,
            x1_icon,
            baseline_y,
            fontsize,
            color=_is_ei.color,
            css_class="ec-event-icon",
        )

    def _draw_day_box(
        self,
        config: CalendarConfig,
        oneday: arrow.Arrow,
        X: float,
        Y: float,
        W: float,
        H: float,
        daytitle: str | bool,
        dayicon: str,
        shadespecialday: str | bool,
        style_result: StyleResult | None = None,
    ):
        """
        Create day box rectangle and place day number, fiscal labels,
        week numbers, and special day titles.

        Args:
            config: Calendar configuration
            oneday: Date as arrow object
            X, Y, W, H: Box coordinates
            daytitle: Holiday title or False
            dayicon: Holiday icon
            shadespecialday: Whether to shade as special day
            style_result: Accumulated style overrides from matched style_rules
        """
        dbc = self._day_box_coords(config, X, Y, W, H)
        oneday_str = oneday.format("YYYYMMDD")
        month = oneday.format("MM")
        x1, y1 = dbc["Number"]

        # Background fill (style_result overrides holiday/fiscal defaults)
        fill_color, fill_opacity = self._resolve_day_box_fill(
            config, oneday_str, month, shadespecialday
        )
        if style_result is not None and style_result.fill_color is not None:
            fill_color = style_result.fill_color
        if style_result is not None and style_result.fill_opacity is not None:
            fill_opacity = style_result.fill_opacity
        self._draw_rect(
            X,
            Y,
            W,
            H,
            fill=fill_color,
            stroke=config.day_box_stroke_color,
            fill_opacity=fill_opacity,
            stroke_opacity=config.day_box_stroke_opacity,
            stroke_width=config.day_box_stroke_width,
            rx=5,
            stroke_dasharray=config.day_box_stroke_dasharray or None,
            css_class="ec-cell",
        )

        # SVG pattern decoration from style_rules
        if style_result is not None and style_result.pattern:
            _color = style_result.pattern_color or config.theme_hash_line_color or hashlinecolor
            self._draw_svg_pattern(config, X, Y, W, H, style_result.pattern, _color, style_result.pattern_opacity)
        elif config.theme_weekly_hash_pattern:
            _color = config.theme_hash_line_color or hashlinecolor
            self._draw_svg_pattern(config, X, Y, W, H, config.theme_weekly_hash_pattern, _color, None)

        # Day number with optional month indicator
        _ts_dn = config.get_text_style("ec-day-number")
        boxdate = self._build_day_number_label(config, oneday, oneday_str)
        day_num_width = string_width(
            boxdate,
            get_font_path(_ts_dn.font),
            config.day_box_number_font_size,
        )
        self._draw_text(
            x1,
            y1,
            boxdate,
            _ts_dn.font,
            config.day_box_number_font_size,
            fill=_ts_dn.color,
            anchor="end",
            css_class="ec-day-number",
        )

        # Fiscal period label and week number
        label_x = X + (W * 0.02)
        label_width = self._draw_fiscal_label(config, oneday, oneday_str, dbc, label_x)
        self._draw_week_number_label(config, oneday, y1, X, label_x, label_width)

        # Holiday title and icon share the day-number baseline so all elements
        # on the same row are baseline-aligned (standard typographic convention).
        self._draw_special_day_title(
            config, dbc, x1, X, y1, daytitle, dayicon, day_num_width
        )

    # =========================================================================
    # SVG pattern decoration
    # =========================================================================

    @staticmethod
    def _parse_svg_tile_size(svg: str) -> tuple[float, float]:
        """
        Extract tile width and height from an SVG string.

        Tries viewBox first (most reliable), then falls back to width/height
        attributes.  Returns (20, 20) if nothing can be parsed.
        """
        m = re.search(r'viewBox=["\'][\d.]+ [\d.]+ ([\d.]+) ([\d.]+)["\']', svg)
        if m:
            return float(m.group(1)), float(m.group(2))
        mw = re.search(r'<svg[^>]+width=["\'](\d+)(?:px)?["\']', svg)
        mh = re.search(r'<svg[^>]+height=["\'](\d+)(?:px)?["\']', svg)
        if mw and mh:
            return float(mw.group(1)), float(mh.group(1))
        return 20.0, 20.0

    @staticmethod
    def _colorize_pattern_svg(svg: str, color: str | None) -> str:
        """
        Replace black fill declarations in a pattern SVG with *color*.

        Handles the three common forms: fill="#000000", fill="#000",
        fill="black".  No-ops when color is None.
        """
        if not color:
            return svg
        result = re.sub(r'fill="#000000"', f'fill="{color}"', svg, flags=re.IGNORECASE)
        result = re.sub(r'fill="#000"', f'fill="{color}"', result, flags=re.IGNORECASE)
        result = re.sub(r'fill="black"', f'fill="{color}"', result, flags=re.IGNORECASE)
        return result

    def _ensure_svg_pattern_def(
        self,
        pattern_name: str,
        color: str | None,
    ) -> str | None:
        """
        Guarantee that a <pattern> element exists in the SVG <defs> for
        (pattern_name, color) and return the element id for use in
        fill="url(#...)".  Returns None if the pattern is unknown.

        Pattern elements are registered at most once per Drawing instance;
        call sites need not guard against duplicates.
        """
        raw_svg = self._pattern_svg_cache.get(pattern_name)
        if not raw_svg:
            return None

        safe_color = (color or "black").replace("#", "").replace(" ", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", pattern_name)
        pat_id = f"pat-{safe_name}-{safe_color}"

        if pat_id in self._registered_pattern_ids:
            return pat_id

        tile_w, tile_h = self._parse_svg_tile_size(raw_svg)
        colorized = self._colorize_pattern_svg(raw_svg, color)

        # Strip XML declaration and peel off the outer <svg> wrapper so that
        # only the tile content is embedded inside the <pattern> element.
        inner = re.sub(r"<\?xml[^>]*\?>", "", colorized)
        inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner)
        inner = re.sub(r"<svg[^>]*>", "", inner, count=1)
        inner = inner.rsplit("</svg>", 1)[0].strip()

        pattern_xml = (
            f'<pattern id="{pat_id}" x="0" y="0" '
            f'width="{tile_w}" height="{tile_h}" '
            f'patternUnits="userSpaceOnUse">'
            f"{inner}"
            f"</pattern>"
        )
        self._drawing.append_def(drawsvg.Raw(pattern_xml))
        self._registered_pattern_ids.add(pat_id)
        return pat_id

    def _draw_svg_pattern(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        w: float,
        h: float,
        pattern_name: str,
        color: str | None,
        opacity: float | None = None,
    ):
        """
        Draw an SVG pattern tile over the body of the day box, leaving the
        top row (day number + holiday name area) clear for readability.

        The pattern is tiled using patternUnits="userSpaceOnUse" so tile
        sizes are in document coordinates.  Opacity defaults to
        config.hash_pattern_opacity but can be overridden per-decoration.
        """
        pat_id = self._ensure_svg_pattern_def(pattern_name, color)
        if not pat_id:
            logger.warning("SVG pattern '%s' not found in database", pattern_name)
            return

        # Reserve the top row (day number + holiday name) from pattern coverage.
        # In PDF coordinates Y increases upward, so shrinking h trims the top.
        top_clearance = config.day_box_number_font_size * 1.2
        pattern_h = max(0.0, h - top_clearance)

        if pattern_h <= 0:
            return

        effective_opacity = (
            opacity if opacity is not None else config.hash_pattern_opacity
        )
        self._draw_rect(
            x,
            y,
            w,
            pattern_h,
            fill=f"url(#{pat_id})",
            fill_opacity=effective_opacity,
            stroke="none",
            rx=5,
            css_class="ec-pattern-fill",
        )

    def _place_event_text(
        self,
        config: CalendarConfig,
        myText: str,
        X: float,
        Y: float,
        Width: float,
        Height: float,
        iconx: float,
        icony: float,
        t: Event,
    ):
        """
        Draw event text in specific group color or default color.

        Args:
            config: Calendar configuration
            myText: Text to display
            X, Y, Width, Height: Text area coordinates
            iconx, icony: Icon position
            t: Event object
        """
        _ts_en = config.get_text_style("ec-event-name")
        _is_ei = config.get_icon_style("ec-event-icon")
        textcolor = _ts_en.color
        iconcolor = _is_ei.color

        _rg_colors = config.theme_resource_group_colors or Resource_Group_colors
        group = (t.resource_group or "").lower()
        if group and group in _rg_colors:
            textcolor = _rg_colors[group]
            iconcolor = textcolor

        if not t.icon:
            self._draw_text(
                iconx,
                icony,
                str(myText),
                _ts_en.font,
                config.weekly_name_text_font_size,
                fill=textcolor,
                max_width=Width,
                css_class="ec-event-name",
            )
        else:
            self._draw_text(
                X,
                icony,
                str(myText),
                _ts_en.font,
                config.weekly_name_text_font_size,
                fill=textcolor,
                max_width=(Width - (config.weekly_name_text_font_size * 1.5)),
                css_class="ec-event-name",
            )

            self._draw_icon_svg(
                t.icon,
                iconx,
                icony,
                config.event_icon_font_size,
                color=iconcolor,
                fallback_name=config.default_missing_icon,
                fallback_color="red",
                css_class="ec-event-icon",
            )

    def _process_overflow(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        t: Event,
        daykey: str,
    ):
        """
        Handle overflow condition by placing indicator icon.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            t: Event object
            daykey: Date key
        """
        X, Y, W, H = coordinates[daykey]
        dbc = self._day_box_coords(config, X, Y, W, H)
        indicatorX, _ = dbc["Overflow"]

        # Place overflow icon on the day-number baseline, left-aligned.
        numX, numY = dbc["Number"]
        indicatorY = numY

        _is_oi = config.get_icon_style("ec-overflow-icon")
        font_size = config.day_box_number_font_size
        self._draw_icon_svg(
            config.overflow_indicator_icon,
            indicatorX,
            indicatorY,
            font_size,
            color=_is_oi.color,
            css_class="ec-overflow-icon",
        )

    def _place_event_and_notes(
        self,
        config: CalendarConfig,
        row_coords: dict,
        t: Event,
        daykey: str,
    ) -> tuple[dict, bool]:
        """
        Place event text and notes on calendar.

        Args:
            config: Calendar configuration
            row_coords: Row coordinate tracking dict
            t: Event object
            daykey: Date key

        Returns:
            Tuple of (updated row_coords, had_overflow)
        """
        rownotfound = True
        numofrows = len(row_coords[daykey])

        for rownumber in row_coords[daykey]:
            (X, Y, Width, Height, textx, texty, iconx, icony, used) = row_coords[
                daykey
            ][rownumber]

            if not used:
                has_notes = bool(t.notes and str(t.notes).strip())
                if config.include_notes and has_notes:
                    if (rownumber + 1) < numofrows:
                        nrow = rownumber + 1
                        (
                            nX,
                            nY,
                            nWidth,
                            nHeight,
                            ntextx,
                            ntexty,
                            niconx,
                            nicony,
                            nused,
                        ) = row_coords[daykey][nrow]

                        if not nused:
                            self._place_event_text(
                                config,
                                t.task_name,
                                textx,
                                texty,
                                Width,
                                Height,
                                iconx,
                                icony,
                                t,
                            )
                            row_coords[daykey][rownumber] = (
                                X,
                                Y,
                                Width,
                                Height,
                                textx,
                                texty,
                                iconx,
                                icony,
                                True,
                            )

                            # Place notes — start at the same X as the event
                            # name: after the icon column when an icon is shown,
                            # or at the icon-column left edge when there is none.
                            notes_x = ntextx if t.icon else niconx
                            notes_max_w = (
                                nWidth - (ntextx - niconx) if t.icon else nWidth
                            )
                            _ts_notes = config.get_text_style("ec-event-notes")
                            self._draw_text(
                                notes_x,
                                nicony,
                                str(t.notes),
                                _ts_notes.font,
                                config.weekly_notes_text_font_size,
                                fill=_ts_notes.color,
                                max_width=notes_max_w,
                                css_class="ec-event-notes",
                            )

                            row_coords[daykey][nrow] = (
                                nX,
                                nY,
                                nWidth,
                                nHeight,
                                ntextx,
                                ntexty,
                                niconx,
                                nicony,
                                True,
                            )
                            rownotfound = False
                            break
                    else:
                        continue
                else:
                    self._place_event_text(
                        config,
                        t.task_name,
                        textx,
                        texty,
                        Width,
                        Height,
                        iconx,
                        icony,
                        t,
                    )
                    row_coords[daykey][rownumber] = (
                        X,
                        Y,
                        Width,
                        Height,
                        textx,
                        texty,
                        iconx,
                        icony,
                        True,
                    )
                    rownotfound = False
                    break

            rownotfound = True
            continue

        if rownotfound:
            self._process_overflow(config, config.CalendarCoord, t, daykey)
            return row_coords, True

        return row_coords, False

    def _mark_rows_used(
        self,
        days_to_print: list,
        rowcoords: dict,
        rowids: list,
    ) -> dict:
        """
        Update rowcoords showing the rows have been used.

        Args:
            days_to_print: List of date keys
            rowcoords: Row coordinate tracking dict
            rowids: List of row IDs to mark

        Returns:
            Updated rowcoords
        """
        for daykey in days_to_print:
            for rownumber in rowids:
                X, Y, Width, Height, textx, texty, iconx, icony, boolean = rowcoords[
                    daykey
                ][rownumber]
                rowcoords[daykey][rownumber] = (
                    X,
                    Y,
                    Width,
                    Height,
                    textx,
                    texty,
                    iconx,
                    icony,
                    True,
                )
        return rowcoords

    def _place_duration_rect(
        self,
        config: CalendarConfig,
        t: Event,
        days_to_print: list,
        rowcoords: dict,
        rowids: list,
        inline_notes: bool = False,
    ):
        """
        Calculate position and draw duration rectangles.

        Args:
            config: Calendar configuration
            t: Event object
            days_to_print: List of date keys
            rowcoords: Row coordinate tracking dict
            rowids: List of row IDs
            inline_notes: If True, append notes to name on one line (name: notes)
                          instead of using a second row. Used when duration >= 3 days.
        """
        list_of_rects = []
        days_to_print = sorted(days_to_print)
        rowids = sorted(rowids)

        has_notes = bool(t.notes and str(t.notes).strip())
        use_double_height = config.include_notes and has_notes and not inline_notes

        # In SVG space rowids[0] is always the top row (smallest Y = highest on
        # page).  Use it as the rect's anchor regardless of single/double height.
        rowid = rowids[0]
        lower_rowid = rowids[1] if len(rowids) > 1 else rowids[0]

        oneday = days_to_print[0]
        (X, Y, W, H, tx, ty, ix, iy, B) = rowcoords[oneday][rowid]
        if use_double_height:
            H = H * 2
            # rowids[0] is the top row in SVG space (smaller Y = higher on page);
            # its texty is where the task name should appear.
            # rowids[1] is the row below it; its texty is where notes appear.
            name_ty = ty  # ty from rowids[0], the top row
            (_, _, _, _, _, notes_ty, _, _, _) = rowcoords[oneday][lower_rowid]
        else:
            name_ty = ty
            notes_ty = ty

        for i, oneday in enumerate(days_to_print):
            (Xb, Yb, Wb, Hb, txb, tyb, ixb, iyb, Bb) = rowcoords[oneday][rowid]
            if i > 0 and Y == Yb:
                W = W + Wb
            if Y != Yb:
                list_of_rects.append((X, Y, W, H, tx, name_ty, ix, iy, notes_ty))
                X, Y, W, H = Xb, Yb, Wb, Hb
                tx, ty, ix, iy = txb, tyb, ixb, iyb
                if use_double_height:
                    H = H * 2
                    name_ty = ty  # ty from rowids[0] for the new week segment
                    (_, _, _, _, _, notes_ty, _, _, _) = rowcoords[oneday][lower_rowid]
                else:
                    name_ty = ty
                    notes_ty = ty

        list_of_rects.append((X, Y, W, H, tx, name_ty, ix, iy, notes_ty))

        _ls_dur = config.get_line_style("ec-duration-bar")
        _ts_en = config.get_text_style("ec-event-name")
        _ts_notes = config.get_text_style("ec-event-notes")
        for X, Y, Width, Height, tx, name_ty, ix, iy, notes_ty in list_of_rects:
            self._draw_rect(
                X,
                Y,
                Width,
                Height,
                fill="lightsteelblue",
                stroke="white",
                stroke_width=0.5,
                rx=2,
                stroke_dasharray=_ls_dur.dasharray or None,
                css_class="ec-duration-bar",
            )

            if inline_notes and has_notes:
                display_name = f"{t.task_name}: {t.notes}"
            else:
                display_name = t.task_name
            centerX = X + (Width / 2)
            self._draw_text(
                centerX,
                name_ty,
                display_name,
                _ts_en.font,
                config.weekly_name_text_font_size,
                fill=_ts_en.color,
                anchor="middle",
                max_width=Width,
                css_class="ec-event-name",
            )

            if use_double_height:
                self._draw_text(
                    centerX,
                    notes_ty,
                    str(t.notes),
                    _ts_notes.font,
                    config.weekly_notes_text_font_size,
                    fill=_ts_notes.color,
                    anchor="middle",
                    max_width=Width,
                    css_class="ec-event-notes",
                )

    def _place_duration(
        self,
        config: CalendarConfig,
        days_to_print: list,
        rowcoords: dict,
        t: Event,
        daykey: str,
    ) -> tuple[dict, bool]:
        """
        Place multi-day duration on calendar.

        Args:
            config: Calendar configuration
            days_to_print: List of all calendar days
            rowcoords: Row coordinate tracking dict
            t: Event object
            daykey: Starting date key

        Returns:
            Tuple of (updated rowcoords, had_overflow)
        """
        duration_dates = []
        daystart = arrow.get(t.start)
        daystart = arrow.get(daystart.date())
        dayend = arrow.get(t.end)
        dayend = arrow.get(dayend.date())

        for oneday in arrow.Arrow.range("day", daystart, dayend):
            duration_dates.append(oneday.format("YYYYMMDD"))

        calendardays = set(days_to_print)
        possible_dates = duration_dates.copy()

        for oneday in possible_dates:
            if oneday not in calendardays:
                duration_dates.remove(oneday)

        if len(duration_dates) == 0:
            return rowcoords, False

        List_of_Possibilities = []

        for dateid in duration_dates:
            for rowid in rowcoords[dateid]:
                (X, Y, W, H, tx, ty, ix, iy, B) = rowcoords[dateid][rowid]
                if B == False:
                    List_of_Possibilities.append(rowid)

        List_of_Possibilities.sort()
        rowids = []
        rownotfound = True

        has_notes = bool(t.notes and str(t.notes).strip())
        use_double_height = config.include_notes and has_notes
        use_inline_notes = False

        if use_double_height:
            for rowid in range(1, config.maxrows):
                if List_of_Possibilities.count(rowid) == len(
                    duration_dates
                ) and List_of_Possibilities.count(rowid - 1) == len(duration_dates):
                    rownotfound = False
                    rowids = [rowid - 1, rowid]
                    self._place_duration_rect(
                        config, t, duration_dates, rowcoords, rowids, inline_notes=False
                    )
                    rowcoords = self._mark_rows_used(duration_dates, rowcoords, rowids)
                    break
        else:
            for rowid in range(config.maxrows):
                if List_of_Possibilities.count(rowid) == len(duration_dates):
                    rownotfound = False
                    rowids = [rowid]
                    self._place_duration_rect(
                        config,
                        t,
                        duration_dates,
                        rowcoords,
                        rowids,
                        inline_notes=use_inline_notes,
                    )
                    rowcoords = self._mark_rows_used(duration_dates, rowcoords, rowids)
                    break

        if rownotfound:
            logger.debug(f"Row not found for duration: {t.task_name}")
            # Use first visible calendar date, not t.datekey which may be a
            # hidden weekend when weekend_style == 0.
            overflow_daykey = duration_dates[0]
            self._process_overflow(config, config.CalendarCoord, t, overflow_daykey)
            return rowcoords, True

        return rowcoords, False
