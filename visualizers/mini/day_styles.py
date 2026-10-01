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

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from config import role_styles
from shared import style_trace
from shared.fiscal_renderer import get_fiscal_period_color
from shared.holidays import style_for
from shared.rule_engine import DayContext, StyleEngine

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


def _mini_style_rules(config: CalendarConfig) -> list:
    """The theme's conditional style rules."""
    return role_styles.style_rules(config.theme_v3)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HashDecoration:
    """A single SVG pattern decoration for a mini calendar day cell."""

    pattern: str
    color: str | None = None
    opacity: float | None = None


#: Rank each icon source carries into the corner ordering. Higher ranks take
#: the earlier corners (top-right first, then clockwise), so the mark a reader
#: most needs to see is the one in the most prominent corner. The values echo
#: the precedence text-mini already assigns its symbols, so the two views rank
#: a day's marks the same way.
ICON_RANK_STYLE_RULE = 110
ICON_RANK_HOLIDAY = 100
ICON_RANK_SPECIAL_DAY = 90
ICON_RANK_MILESTONE = 80
ICON_RANK_EVENT = 50


@dataclass(frozen=True)
class DayIcon:
    """One icon to draw in a day cell's corner, and how it earned its place.

    ``rank`` decides corner order, not whether the icon is drawn: a day with
    a holiday, a milestone and two events shows all four.  Only the fifth and
    beyond are dropped, lowest rank first — there are four corners.
    """

    name: str
    rank: int = ICON_RANK_EVENT
    #: The event row or holiday name the icon marks, for the run details.
    event: dict | None = field(default=None, compare=False)
    holiday: str | None = field(default=None, compare=False)


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
    # None = take the stroke from the ec-day-box element style. Nothing
    # assigns box_color today, so a literal default here was the colour every
    # boxed day number actually got, with no way for a theme to reach it.
    box_color: str | None = None

    # Circle (milestone)
    circled: bool = False  # Draw circle around day number
    # None = take the stroke from the ec-milestone-marker line style; the
    # milestone branch below sets this explicitly whenever it circles a day.
    circle_color: str | None = None
    circle_fill: str | None = None  # Circle fill (None = no fill)

    # Icons drawn in the cell's corners. The day number / day glyph is always
    # drawn as well — an icon never stands in for it (it used to, which lost
    # the one thing every cell has to say). Ordered by rank when read; use
    # add_icon() to append rather than assigning, so no source silently drops
    # another's mark.
    icons: list[DayIcon] = field(default_factory=list)

    # Color bar (for duration events spanning week rows)
    color_bar: str | None = None  # Color for duration bar
    color_bar_label: str | None = None  # Label text for duration bar

    # Leading/trailing month indicator
    is_adjacent_month: bool = False

    # The day this style is for (YYYYMMDD), so what it drops can be reported.
    daykey: str = ""

    # SVG pattern decorations
    hash_decorations: list[HashDecoration] = field(default_factory=list)

    # Priority for stacking (higher = rendered last / on top)
    priority: int = 0

    # Fiscal period start label (e.g. "P1", "Q1 FY26 P1") — None if not a period start
    fiscal_period_label: str | None = None

    def trace_drawn(self, view: str) -> None:
        """Style trace: the shade and patterns the cell background draws."""
        if not style_trace.enabled():
            return
        subject = f"day {self.daykey} ({view})"
        if self.shade_color:
            style_trace.emit(subject, "DRAWN", f"fill={self.shade_color} opacity={self.shade_opacity}")
        else:
            style_trace.emit(
                subject, "DRAWN", "no rule or holiday shade on this cell (view-level base shading is drawn separately)"
            )
        if self.hash_decorations:
            for dec in self.hash_decorations:
                style_trace.emit(
                    subject, "PATTERN", f"{dec.pattern!r} color={dec.color} opacity={dec.opacity} (from style rule)"
                )
        elif self.hash_pattern > 0:
            style_trace.emit(subject, "PATTERN", f"legacy hash {self.hash_pattern}")
        else:
            style_trace.emit(subject, "PATTERN", "none")

    def add_icon(
        self,
        name: str | None,
        rank: int = ICON_RANK_EVENT,
        *,
        event: dict | None = None,
        holiday: str | None = None,
    ) -> None:
        """Record one icon for this day, ignoring blanks and duplicates.

        A day often draws the same glyph from two sources — a company
        holiday that is also a nonworking special day, say — and showing it
        twice would waste a corner on a mark the reader has already read.
        """
        if not name:
            return
        text = str(name).strip()
        if not text or any(icon.name == text for icon in self.icons):
            return
        self.icons.append(DayIcon(text, rank, event, holiday))

    def corner_icons(self, limit: int) -> list[DayIcon]:
        """The icons to draw, highest rank first, capped at ``limit``.

        Ties keep the order they were added, so a day carrying two events
        shows them in the order the resolver saw them rather than an order
        that shifts between runs.
        """
        ordered = sorted(self.icons, key=lambda i: -i.rank)
        return ordered[: max(0, limit)]

    def dropped_icons(self, limit: int) -> list[DayIcon]:
        """The icons :meth:`corner_icons` leaves out for want of a corner."""
        ordered = sorted(self.icons, key=lambda i: -i.rank)
        return ordered[max(0, limit) :]


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
        # The labels of the timescale's fiscal_period row, on the day each period opens.
        # An NRF period opens on a Sunday, which a workweek-only mini never draws, so
        # the label falls forward to the period's first visible day.
        from renderers.timescale import grid_period_labels

        self.period_labels = grid_period_labels(config)

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
        style = DayStyle(is_adjacent_month=is_adjacent, daykey=daykey)

        if is_adjacent:
            mini = self._config.theme_v3.mini_calendar
            style.text_color = mini.adjacent_month_color
            style.text_opacity = mini.adjacent_month_opacity
            return style

        holidays = self._db.get_holidays_for_date(daykey, self._config.country)
        special_days = self._db.get_special_days_for_date(daykey)

        # Layer 0: Fiscal period coloring and labels (holidays override color in Layer 1)
        if self._config.fiscal_lookup:
            fiscal_info = self._config.fiscal_lookup.get(daykey)
            if fiscal_info:
                if self._config.theme_v3.fiscal.use_period_colors:
                    style.shade_color = get_fiscal_period_color(fiscal_info, self._config)
                    style.shade_opacity = self._config.theme_v3.fiscal.period_opacity
                if self.period_labels is not None:
                    day = date(int(daykey[:4]), int(daykey[4:6]), int(daykey[6:8]))
                    label = " ".join(
                        p for p in (self.period_labels.start.get(day), self.period_labels.end.get(day)) if p
                    )
                    style.fiscal_period_label = label or None

        # Layer 1: Government holidays
        self._apply_holidays(style, holidays)

        # Layer 2: Company special days
        self._apply_special_days(style, special_days)

        # Layer 3: Events on this day
        self._apply_events(style, events)

        # Layer 3b: theme style_rules — applies fill, pattern, icon, and text
        # overrides driven by day classification + event criteria.
        self._apply_style_rules(
            style,
            holidays=holidays,
            special_days=special_days,
            events=events,
        )

        # Layer 4: Current day shading (applied last so it overlays other styles)
        highlight = self._config.theme_v3.today.highlight
        if highlight.show and daykey == date.today().strftime("%Y%m%d"):
            style.shade_color = highlight.color
            style.shade_opacity = highlight.opacity

        return style

    def _apply_holidays(self, style: DayStyle, holidays: list[dict]) -> None:
        """Apply baseline holiday styling — text color, fallback shade, icon.

        Cell shade for ``colors.federal_holiday`` is now driven by a
        synthesized ``box:day`` rule injected by ``ThemeEngine.apply()``
        (Open Issue §2 resolution).  This method sets a CalendarConfig-
        default baseline shade so themes that don't define
        ``colors.federal_holiday`` (or whose theme failed to parse) still
        get *some* visible nonworkday tint; the synthesized rule then
        overrides it via ``_apply_box_day_rules``.

        Every holiday on the day contributes its icon, not just the first:
        a day that is a holiday in several of the loaded countries shows each
        country's icon in its own corner.  ``add_icon`` drops repeats, so two
        holidays from one country still take a single corner.
        """
        if not holidays:
            return

        # Text color stays on the legacy chain — text:day_number is a
        # separate concern from box:day.
        theme_holidays = self._config.theme_v3.holidays
        style.text_color = theme_holidays.federal.color or "red"

        if any(h.get("nonworkday") for h in holidays):
            fill, opacity, _ = style_for(frozenset({"federal_holiday"}), theme_holidays)
            if fill:
                style.shade_color, style.shade_opacity = fill, opacity

        for holiday in holidays:
            style.add_icon(
                holiday.get("icon") or holiday.get("displayiconid"),
                ICON_RANK_HOLIDAY,
                holiday=holiday.get("displayname") or holiday.get("name"),
            )

    def _apply_special_days(self, style: DayStyle, special_days: list[dict]) -> None:
        """Apply baseline company-special-day styling — fallback shade,
        pattern, icon.

        Cell shade for ``colors.company_holiday`` is now driven by a
        synthesized ``box:day`` rule (Open Issue §2 resolution); this
        method only provides the CalendarConfig-default baseline that the
        synthesized rule overrides.
        """
        for sd in special_days:
            if sd.get("nonworkday"):
                fill, opacity, _ = style_for(frozenset({"company_holiday"}), self._config.theme_v3.holidays)
                if fill:
                    style.shade_color, style.shade_opacity = fill, opacity

            pattern = sd.get("pattern", 0)
            if pattern:
                with contextlib.suppress(ValueError, TypeError):
                    style.hash_pattern = int(pattern)

            style.add_icon(sd.get("icon"), ICON_RANK_SPECIAL_DAY, holiday=sd.get("name"))

    def _apply_events(self, style: DayStyle, events: list[dict]) -> None:
        """Apply event-driven styling."""
        engine = StyleEngine(_mini_style_rules(self._config))

        for event in events:
            # Milestones get circled
            if event.get("Milestone") and self._config.theme_v3.mini_calendar.circle_milestones:
                style.circled = True
                milestone_box = self._config.theme_v3.boxes.milestone
                style.circle_color = (
                    milestone_box.stroke
                    if milestone_box.stroke not in ("", "none")
                    else self._config.theme_v3.icons.milestone.color
                )
                style.bold = True
                style.priority = max(style.priority, 10)
                # A milestone outranks a plain event, so it takes the earlier
                # corner — but it no longer displaces the events sharing its
                # day, and two milestones no longer displace each other.
                style.add_icon(event.get("Icon"), ICON_RANK_MILESTONE, event=event)

            # The event's color from style_rules, as every view assigns it,
            # colors the day number.  A day_number text rule still wins.
            fill = engine.evaluate_event(self._dict_to_event(event)).fill_color
            if fill:
                style.text_color = fill

            # Icon from a non-milestone event. Every event that carries one
            # gets a corner now — a second event no longer overwrites the
            # first, and a milestone no longer suppresses them.
            if not event.get("Milestone"):
                style.add_icon(event.get("Icon"), ICON_RANK_EVENT, event=event)

            # Bold for high-priority events
            priority = event.get("Priority") or 0
            if priority and int(priority) <= 1:
                style.bold = True

    def _apply_style_rules(
        self,
        style: DayStyle,
        *,
        holidays: list[dict],
        special_days: list[dict],
        events: list[dict],
    ) -> None:
        """Layer theme ``style_rules`` overrides onto a mini day cell.

        Applies (in priority order over earlier layers):

        - ``fill_color`` / ``fill_opacity`` → cell shade
        - ``pattern`` / ``pattern_color`` / ``pattern_opacity`` → hash decoration
        - ``icon`` → a corner icon at ``ICON_RANK_STYLE_RULE``
        - ``text["day_number"]`` font / color → text style fields

        Pass 1 consumes the parsed UnifiedTheme's ``box:day`` rules — both
        the synthesized rules ``ThemeEngine.apply()`` injects from
        ``colors.federal_holiday`` / ``colors.company_holiday``, and any
        explicit ``apply_to: box:day`` rules the theme declares.  Pass 2
        consumes the legacy ``apply_to: day_box`` form via ``StyleEngine``
        for pre-migration themes that were never converted;
        ``_applicable_rules("day_box")`` ignores
        the new ``box:day`` form so the two passes don't double up.
        """
        federal_holiday = bool(holidays)
        company_holiday = any(bool(sd.get("nonworkday")) for sd in special_days)
        nonworkday = federal_holiday or company_holiday

        # Pass 2 — legacy StyleEngine (apply_to: day_box).  Sourced from the
        # same style_rules list; rules with the new ``box:day`` apply_to form
        # are ignored by _applicable_rules("day_box") so this only handles
        # any pre-migration themes that still ship the old form.
        style_rules = _mini_style_rules(self._config)
        if not style_rules:
            return

        ctx = DayContext(
            date=style.daykey,
            federal_holiday=federal_holiday,
            company_holiday=company_holiday,
            nonworkday=nonworkday,
            workday=not nonworkday,
        )
        event_objects = [self._dict_to_event(e) for e in events]
        style_result = StyleEngine(style_rules).evaluate_day(ctx, event_objects)

        if style_result.fill_color:
            style.shade_color = style_result.fill_color
            if style_result.fill_opacity is not None:
                style.shade_opacity = float(style_result.fill_opacity)

        if style_result.pattern:
            style.hash_decorations = [
                HashDecoration(
                    pattern=style_result.pattern,
                    color=style_result.pattern_color,
                    opacity=style_result.pattern_opacity,
                )
            ]

        style.add_icon(style_result.icon, ICON_RANK_STYLE_RULE)

        day_text = style_result.text.get("day_number")
        if day_text is not None:
            if day_text.font_color is not None:
                style.text_color = day_text.font_color
            if day_text.font_opacity is not None:
                style.text_opacity = float(day_text.font_opacity)
            if day_text.font is not None:
                style.font_name = day_text.font

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
