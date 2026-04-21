"""
Day styling system for mini calendar visualization.

Maps database events, holidays, and special days to visual treatments
applied to individual day cells. The DayStyle dataclass captures all
13 formatting capabilities shown in the design reference:

  Regular, Bold, Boxed, Color Coded, Shaded, Fill Pattern,
  Outlined font, Strikethrough, Icon replace number, Add icon to number,
  Color bars, Change font, Circled Milestone Number.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from dataclasses import dataclass

from shared.fiscal_renderer import get_fiscal_period_color
from shared.rule_engine import DayContext, StyleEngine

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HashDecoration:
    """A single SVG pattern decoration for a mini calendar day cell."""

    pattern: str
    color: str | None = None
    opacity: float | None = None


@dataclass
class DayStyle:
    """Visual treatment for a single day cell in the mini calendar."""

    # Text properties
    bold: bool = False
    font_name: str | None = None  # Override font (None = use default)
    text_color: str | None = None  # Override text color (None = default)
    text_opacity: float = 1.0
    outlined: bool = False  # Stroke-only text (no fill)
    strikethrough: bool = False

    # Cell background
    shade_color: str | None = None  # Background fill color
    shade_opacity: float = 0.3
    hash_pattern: int = 0  # Diagonal fill pattern (1-15)

    # Box / border
    boxed: bool = False  # Draw border around day number
    box_color: str = "black"

    # Circle (milestone)
    circled: bool = False  # Draw circle around day number
    circle_color: str = "navy"
    circle_fill: str | None = None  # Circle fill (None = no fill)

    # Icon treatment
    icon_replace: str | None = None  # Icon replaces day number entirely
    icon_append: str | None = None  # Icon appended after day number

    # Color bar (for duration events spanning week rows)
    color_bar: str | None = None  # Color for duration bar
    color_bar_label: str | None = None  # Label text for duration bar

    # Leading/trailing month indicator
    is_adjacent_month: bool = False

    # SVG pattern decorations
    hash_decorations: list[HashDecoration] = field(default_factory=list)

    # Priority for stacking (higher = rendered last / on top)
    priority: int = 0

    # Fiscal period start label (e.g. "P1", "Q1 FY26 P1") — None if not a period start
    fiscal_period_label: str | None = None


class DayStyleResolver:
    """
    Resolves database data into DayStyle for each day in a month grid.

    Queries holidays, special days, and checks event properties to build
    a composite DayStyle per day. Each data source layer merges its
    properties onto the style (later layers override earlier ones when
    both set the same field).
    """

    def __init__(self, config: CalendarConfig, db: CalendarDB):
        self._config = config
        self._db = db

    def resolve(
        self,
        daykey: str,
        events: list[dict],
        is_adjacent: bool = False,
    ) -> DayStyle:
        """
        Determine the DayStyle for a given day.

        Args:
            daykey: Date in YYYYMMDD format
            events: Events overlapping this day (pre-filtered)
            is_adjacent: Whether this day belongs to an adjacent month

        Returns:
            Merged DayStyle for this day
        """
        style = DayStyle(is_adjacent_month=is_adjacent)

        if is_adjacent:
            style.text_color = (
                self._config.theme_mini_adjacent_month_color
                or self._config.mini_adjacent_month_color
            )
            style.text_opacity = 0.4
            return style

        holidays = self._db.get_holidays_for_date(daykey, self._config.country)
        special_days = self._db.get_special_days_for_date(daykey)

        # Layer 0: Fiscal period coloring and labels (holidays override color in Layer 1)
        if self._config.fiscal_lookup:
            fiscal_info = self._config.fiscal_lookup.get(daykey)
            if fiscal_info:
                if self._config.fiscal_use_period_colors:
                    style.shade_color = get_fiscal_period_color(fiscal_info, self._config)
                    style.shade_opacity = 0.50
                if self._config.fiscal_show_period_labels and fiscal_info.is_period_start:
                    from shared.fiscal_renderer import format_fiscal_period_label
                    style.fiscal_period_label = format_fiscal_period_label(fiscal_info, self._config)

        # Layer 1: Government holidays
        self._apply_holidays(style, holidays)

        # Layer 2: Company special days
        self._apply_special_days(style, special_days)

        # Layer 3: Events on this day
        self._apply_events(style, events)

        # Layer 3b: Day-box decorations driven by mini hash rules
        style.hash_decorations = self._resolve_hash_decorations(
            holidays=holidays,
            special_days=special_days,
            events=events,
        )

        # Layer 4: Current day shading (applied last so it overlays other styles)
        if self._config.shade_current_day:
            today_key = date.today().strftime("%Y%m%d")
            if daykey == today_key:
                style.shade_color = (
                    self._config.theme_mini_current_day_color
                    or self._config.mini_current_day_color
                )
                style.shade_opacity = 0.25

        return style

    def _apply_holidays(self, style: DayStyle, holidays: list[dict]) -> None:
        """Apply holiday styling to a DayStyle."""
        if not holidays:
            return

        holiday = holidays[0]
        # Unified: use federal holiday color (same as weekly renderer), then mini-specific overrides
        style.text_color = (
            self._config.theme_federal_holiday_color
            or self._config.theme_mini_holiday_color
            or self._config.mini_holiday_color
        )

        if holiday.get("nonworkday"):
            style.shade_color = (
                self._config.theme_federal_holiday_color
                or self._config.theme_mini_nonworkday_fill_color
                or self._config.mini_nonworkday_fill_color
            )
            style.shade_opacity = 0.2

        icon = holiday.get("icon") or holiday.get("displayiconid")
        if icon:
            style.icon_replace = str(icon)

    def _apply_special_days(self, style: DayStyle, special_days: list[dict]) -> None:
        """Apply company special day styling."""
        for sd in special_days:
            if sd.get("nonworkday"):
                # Unified: use company holiday color (same as weekly renderer), then mini-specific override
                style.shade_color = (
                    self._config.theme_company_holiday_color
                    or self._config.theme_mini_nonworkday_fill_color
                    or self._config.mini_nonworkday_fill_color
                )
                style.shade_opacity = 0.25

            pattern = sd.get("pattern", 0)
            if pattern:
                try:
                    style.hash_pattern = int(pattern)
                except (ValueError, TypeError):
                    pass

            icon = sd.get("icon")
            if icon:
                style.icon_replace = str(icon)

    def _apply_events(self, style: DayStyle, events: list[dict]) -> None:
        """Apply event-driven styling."""
        from config.config import Resource_Group_colors

        milestone_icon: str | None = None

        for event in events:
            # Milestones get circled
            if event.get("Milestone") and self._config.mini_circle_milestones:
                style.circled = True
                style.circle_color = (
                    self._config.theme_mini_milestone_color
                    or self._config.mini_milestone_stroke_color
                    or self._config.mini_milestone_color
                )
                style.bold = True
                style.priority = max(style.priority, 10)
                # Capture milestone icon separately so non-milestone events
                # cannot overwrite it.
                icon = event.get("Icon")
                if icon:
                    milestone_icon = str(icon)

            # Resource group coloring
            rg = (event.get("Resource_Group") or "").upper()
            if rg:
                rg_colors = (
                    self._config.theme_resource_group_colors or Resource_Group_colors
                )
                if rg in rg_colors:
                    style.text_color = rg_colors[rg]

            # Icon from non-milestone event (only if no milestone icon has been set)
            if not event.get("Milestone"):
                icon = event.get("Icon")
                if icon and not milestone_icon:
                    style.icon_replace = str(icon)

            # Bold for high-priority events
            priority = event.get("Priority") or 0
            if priority and int(priority) <= 1:
                style.bold = True

        # Milestone icon wins over any non-milestone icon
        if milestone_icon:
            style.icon_replace = milestone_icon

    def _resolve_hash_decorations(
        self,
        *,
        holidays: list[dict],
        special_days: list[dict],
        events: list[dict],
    ) -> list[HashDecoration]:
        """Resolve mini day-cell SVG pattern decorations from style_rules."""
        style_rules = self._config.theme_style_rules or []
        if not style_rules:
            return []

        federal_holiday = bool(holidays)
        company_holiday = any(bool(sd.get("nonworkday")) for sd in special_days)
        nonworkday = federal_holiday or company_holiday

        ctx = DayContext(
            federal_holiday=federal_holiday,
            company_holiday=company_holiday,
            nonworkday=nonworkday,
            workday=not nonworkday,
        )

        event_objects = [self._dict_to_event(e) for e in events]
        style_result = StyleEngine(style_rules).evaluate_day(ctx, event_objects)

        if not style_result.pattern:
            return []
        return [HashDecoration(
            pattern=style_result.pattern,
            color=style_result.pattern_color,
            opacity=style_result.pattern_opacity,
        )]

    @staticmethod
    def _dict_to_event(d: dict):
        """Convert a mini event dict to an Event object for rule matching."""
        from shared.data_models import Event
        try:
            pc = float(d.get("Percent_Complete") or 0.0)
        except (TypeError, ValueError):
            pc = 0.0
        try:
            pri = int(d.get("Priority") or 0)
        except (TypeError, ValueError):
            pri = 0
        return Event(
            task_name=str(d.get("Task_Name") or d.get("Task") or ""),
            start=str(d.get("Start", ""))[:8],
            end=str(d.get("End") or d.get("Finish") or d.get("Start") or "")[:8],
            notes=d.get("Notes"),
            icon=d.get("Icon"),
            resource_group=d.get("Resource_Group"),
            resource_names=d.get("Resource_Name") or d.get("Resource_Names"),
            percent_complete=pc,
            milestone=bool(d.get("Milestone")),
            rollup=bool(d.get("Rollup")),
            datekey=d.get("Datekey") or d.get("datekey"),
            priority=pri,
            wbs=d.get("WBS"),
            color=d.get("Color") or d.get("color") or None,
        )
