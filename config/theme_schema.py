"""The theme schema: every key a version-3.0 theme may set, and its default.

This module is the single source of truth for what a theme can say.  The
dataclasses below are the *only* place defaults live: a theme may omit any key
and gets the value written here.  ``config.theme_loader`` parses a theme file
against them strictly (an unknown or misplaced key is an error that names its
path), ``config/themes/demonstration.yaml`` must contain every field, and the
user guide's key reference is generated from them.

Layout of a theme
-----------------
Decoration is declared once, at the top level, and every visualization honours
the same declaration::

    theme, fonts, text, boxes, icons, lines, palettes,
    timescale, today, holidays, shading, week_numbers, fiscal,
    events, durations, continuation, overflow, watermark, layout, details,
    style_rules

A view block (``weekly``, ``timeline`` ...) holds structure only: geometry,
columns, lanes, ratios and switches that mean something to one view alone.  No
view block may carry a key that a decoration block owns.

Conventions
-----------
* Colours are CSS names or ``#rrggbb``.
* A palette is the name of a database palette, or an inline list of colours.
* Lengths are points.  ``None`` means "derive it" (usually from a font size).
* Field order inside a dataclass is the order the demonstration theme shows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

#: The only theme version this program reads.
THEME_VERSION = "3.0"

Palette = str | list[str]
Align = Literal["start", "middle", "end"]
Orientation = Literal["horizontal", "vertical"]
Side = Literal["primary", "secondary", "both"]
Route = Literal["straight", "curve"]
Marker = str  # "none", or the name of a marker (arrow-head, circle, diamond, ...)


def font_field(default: str | None = None) -> Any:
    """A field naming a registered font; the loader checks it against the registry."""
    return field(default=default, metadata={"font": True})


# ─── Building blocks ─────────────────────────────────────────────────────────


@dataclass
class LineSpec:
    """A line: axis, tick, leader, dependency arrow, today line, border, grid.

    One type for every line the program draws.  ``start_stub`` and
    ``end_stub`` are straight segments kept square to the anchor at each end
    so a routed line leaves and meets its endpoints cleanly.
    """

    color: str = "grey"
    width: float = 0.5
    opacity: float = 1.0
    dasharray: str | None = None
    linecap: Literal["butt", "round", "square"] = "round"
    linejoin: Literal["miter", "round", "bevel"] = "round"
    marker_start: Marker = "none"
    marker_start_size: float = 4.0
    marker_end: Marker = "none"
    marker_end_size: float = 6.0
    start_stub: float = 0.0
    end_stub: float = 0.0
    route: Route = "straight"

    def __post_init__(self) -> None:
        if self.width < 0:
            raise ValueError("width must be >= 0")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError("opacity must be between 0 and 1")
        if self.start_stub < 0 or self.end_stub < 0:
            raise ValueError("stubs must be >= 0")


@dataclass
class LeaderSide:
    """What changes about a leader when its label sits on one side of the axis: its colour."""

    color: str | None = None


@dataclass
class TextRole:
    """A named text style.  ``font`` None means ``fonts.family``."""

    font: str | None = font_field()
    size: float = 8.0
    color: str = "#333333"
    opacity: float = 1.0
    align: Align = "start"
    #: Size overrides by paper name, e.g. ``{letter: 10, 3x5: 6}``.
    size_by_paper: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.size <= 0:
            raise ValueError("size must be > 0")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError("opacity must be between 0 and 1")


@dataclass
class BoxRole:
    """A named rectangle style."""

    fill: str = "none"
    fill_opacity: float = 1.0
    stroke: str = "none"
    stroke_width: float = 0.5
    stroke_opacity: float = 1.0
    stroke_dasharray: str | None = None
    corner_radius: float = 0.0
    #: Cycled per instance (month cells, band segments).  Beats ``fill``.
    fill_palette: Palette | None = None
    #: Pattern name from the database ``patterns`` table.
    pattern: str | None = None
    pattern_color: str | None = None
    pattern_opacity: float = 0.15

    def __post_init__(self) -> None:
        for name in ("fill_opacity", "stroke_opacity", "pattern_opacity"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")


@dataclass
class IconRole:
    """A named icon style.  ``name`` is the default icon when the data names none."""

    color: str = "#333333"
    size: float | None = None
    name: str | None = None
    stroke_width: float | None = None
    stroke_opacity: float | None = None


# ─── fonts, text, boxes, icons, lines ────────────────────────────────────────


@dataclass
class Fonts:
    """The default font family; any text role may name its own."""

    family: str = font_field("OfficinaSans-Book")


def _text(size: float, color: str, font: str | None = None, **kw: Any) -> Callable[[], TextRole]:
    return lambda: TextRole(font=font, size=size, color=color, **kw)


@dataclass
class TextRoles:
    """Every text style the renderers use, one field per role."""

    heading: TextRole = field(default_factory=_text(10, "grey"))
    body: TextRole = field(default_factory=_text(8, "navy"))
    body_secondary: TextRole = field(default_factory=_text(7, "darkgrey"))
    label: TextRole = field(default_factory=_text(7, "grey"))
    label_bold: TextRole = field(default_factory=_text(7, "grey"))
    caption: TextRole = field(default_factory=_text(6, "grey"))
    day_number: TextRole = field(default_factory=_text(18, "navy"))
    month_title: TextRole = field(default_factory=_text(18, "navy"))
    week_number: TextRole = field(default_factory=_text(9, "#888888"))
    band_label: TextRole = field(default_factory=_text(7, "black"))
    swimlane_label: TextRole = field(default_factory=_text(8, "black"))
    fiscal_label: TextRole = field(default_factory=_text(8, "#666666"))
    event_name: TextRole = field(default_factory=_text(10, "#333333"))
    event_notes: TextRole = field(default_factory=_text(9, "#666666"))
    event_date: TextRole = field(default_factory=_text(8, "#666666"))
    duration_date: TextRole = field(default_factory=_text(8, "#666666"))
    holiday_title: TextRole = field(default_factory=_text(8, "#333333"))
    today_label: TextRole = field(default_factory=_text(8, "#FF4444"))


def _box(**kw: Any) -> Callable[[], BoxRole]:
    return lambda: BoxRole(**kw)


@dataclass
class BoxRoles:
    """Every rectangle style the renderers use, one field per role."""

    default: BoxRole = field(default_factory=_box(fill="white"))
    cell: BoxRole = field(
        default_factory=_box(fill="grey", fill_opacity=0.25, stroke="grey", stroke_width=2, stroke_opacity=0.25)
    )
    day: BoxRole = field(default_factory=_box(fill="#F8F8FF", fill_opacity=0.25, stroke="#CCCCCC"))
    header: BoxRole = field(default_factory=_box())
    band: BoxRole = field(default_factory=_box())
    highlight: BoxRole = field(default_factory=_box(fill="lightblue", fill_opacity=0.3))
    callout: BoxRole = field(
        default_factory=_box(fill="white", fill_opacity=0.25, stroke="grey", stroke_width=1.0, corner_radius=2.0)
    )
    event: BoxRole = field(default_factory=_box())
    milestone: BoxRole = field(default_factory=_box())
    duration: BoxRole = field(default_factory=_box(fill="#888888", fill_opacity=0.75))


def _icon(**kw: Any) -> Callable[[], IconRole]:
    return lambda: IconRole(**kw)


@dataclass
class IconRoles:
    """Icon styles by kind, plus the stand-in drawn for an icon the data names but the table lacks."""

    event: IconRole = field(default_factory=_icon(color="navy", size=10))
    duration: IconRole = field(default_factory=_icon(color="navy"))
    milestone: IconRole = field(default_factory=_icon(color="#333333", size=10))
    #: Drawn where an event names an icon the ``icon`` table does not have.
    missing: IconRole = field(default_factory=_icon(color="red", name="exclamation-circle"))
    #: Marks a box that could not hold its contents (the glyph is ``overflow.icon``).
    overflow: IconRole = field(default_factory=_icon(color="red"))


def _line(**kw: Any) -> Callable[[], LineSpec]:
    return lambda: LineSpec(**kw)


@dataclass
class LineRoles:
    """Every line style the renderers use, one field per role."""

    axis: LineSpec = field(default_factory=_line(color="lightgrey", width=3, opacity=0.9))
    tick: LineSpec = field(default_factory=_line(color="grey", width=0.5))
    grid: LineSpec = field(default_factory=_line(color="grey", width=0.5, opacity=0.3))
    separator: LineSpec = field(default_factory=_line(color="grey", width=0.5, opacity=0.5))
    border: LineSpec = field(default_factory=_line(color="lightgrey", width=0.5))
    today: LineSpec = field(default_factory=_line(color="tomato", width=1.0, opacity=0.85, dasharray="4,2"))
    leader: LineSpec = field(
        default_factory=_line(
            color="grey",
            width=0.75,
            marker_end="arrow-head",
            marker_end_size=5.0,
            start_stub=4.0,
            end_stub=4.0,
            route="curve",
        )
    )
    #: Colour of the leaders of labels on the axis's primary / secondary side.
    leader_primary: LeaderSide = field(default_factory=lambda: LeaderSide(color="deepskyblue"))
    leader_secondary: LeaderSide = field(default_factory=lambda: LeaderSide(color="steelblue"))
    connector: LineSpec = field(default_factory=_line(color="grey", width=0.5, dasharray="4 2"))
    dependency: LineSpec = field(
        default_factory=_line(color="grey", width=0.75, marker_end="arrow-head", marker_end_size=6.0, route="curve")
    )
    duration_bar: LineSpec = field(default_factory=_line(color="grey", width=5.0))
    progress: LineSpec = field(default_factory=_line(color="black", width=1.5))


@dataclass
class Palettes:
    """Colour sequences shared by every view.  Band fills are ``boxes.band.fill_palette``."""

    month: Palette = "colorblind1"
    fiscal: Palette = "paired"
    group: Palette = "pastel1"
    #: Cycled over durations that carry no colour of their own.
    event: Palette = field(default_factory=lambda: ["lightskyblue", "gold", "tomato", "springgreen", "plum", "khaki"])
    #: Fills for timeline / pit callout labels.
    label: Palette = "Pastel1"
    #: Explicit month number ("01"-"12") to colour; beats ``month``.
    month_colors: dict[str, str] = field(default_factory=dict)
    #: Explicit fiscal period number to colour; beats ``fiscal``.
    fiscal_period_colors: dict[str, str] = field(default_factory=dict)
    group_colors: list[str] = field(default_factory=list)
    #: Ink for hash patterns drawn in day boxes.
    hash_lines: str = "black"


# ─── timescale: timebands, ticks and the axis ────────────────────────────────

Unit = Literal[
    "date",
    "dow",
    "week",
    "month",
    "quarter",
    "year",
    "fiscal_quarter",
    "fiscal_period",
    "interval",
    "countdown",
    "countup",
    "holiday",
    "icon",
]


@dataclass
class RowText:
    """Text of one timescale row; unset values come from ``text.band_label``."""

    font: str | None = font_field()
    size: float | None = None
    color: str | None = None
    opacity: float | None = None
    align: Align | None = None
    #: Degrees; ``None`` lets a vertical axis pick bottom-to-top.
    rotation: float | None = None


@dataclass
class RowTick:
    """How a row is drawn on an axis (timeline, pit): a mark at each segment start.

    The row's side of the axis is the list it sits in (``timescale.primary`` /
    ``timescale.secondary``); marks and labels extend to that side.
    """

    length: float = 4.0
    width: float | None = None
    color: str | None = None
    opacity: float | None = None
    show_labels: bool = True
    label_align: Literal["start", "middle", "end"] = "start"
    label_gap: float | None = None
    #: Skip the labels when a row would carry more than this many.
    max_label_count: int | None = None


@dataclass
class RowColumnFill:
    """Shade the column under every segment of a row, down the content area.

    A single ``fill`` or a ``fill_palette`` cycled segment by segment.
    """

    fill: str | None = None
    fill_palette: Palette | None = None
    fill_opacity: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 <= self.fill_opacity <= 1.0:
            raise ValueError("fill_opacity must be between 0 and 1")


@dataclass
class RowHolidays:
    """Options for ``unit: holiday`` rows."""

    #: True hides observances that do not close the office.
    nonworkdays_only: bool = True


@dataclass
class TimescaleRow:
    """One row of the timescale: a distance divided into day segments and grouped.

    A row serves every view.  A table view (blockplan, compactplan, gantt, excel)
    draws it as a band of cells; an axis view (timeline, pit) draws it as ticks
    and labels along the axis; a grid view (candybar, weekly) draws the rows its
    geometry can express.  A facet a view does not use is valid and ignored.
    """

    unit: Unit
    #: Show every Nth segment, merged into one cell.
    every: int = 1
    #: Heading text for the row (table views).
    label: str | None = None
    #: Segment label format: an Arrow format for date units, a template for
    #: week / fiscal units (``Week {n}``, ``Q{q}-FY{fy2}``, ``{start} - {end}``).
    format: str | None = None
    height: float = 12.0
    #: Cell background; unset, the row takes ``boxes.band`` (a single fill or a palette cycled per cell).
    fill: str | None = None
    fill_palette: Palette | None = None
    fill_opacity: float | None = None
    #: Cell border; unset, the row takes the stroke of ``boxes.band``.
    border: LineSpec | None = None
    text: RowText = field(default_factory=RowText)
    tick: RowTick | None = None
    #: A line drawn down the content area at every segment boundary of this row.
    vline: LineSpec | None = None
    #: A fill down the content area under every segment of this row.
    vfill: RowColumnFill | None = None
    holidays: RowHolidays = field(default_factory=RowHolidays)
    #: Explicit labels cycled over the segments.
    label_values: list[str] = field(default_factory=list)
    #: ``fiscal_period`` rows in a grid view (weekly): a second label, in this template, on the
    #: last day of each period.  Unset draws only the start label.
    end_format: str | None = None
    # unit-specific
    week_start: int | None = None
    fiscal_year_start_month: int | None = None
    interval_days: int = 14
    prefix: str = ""
    start_index: int = 1
    max_index: int | None = None
    anchor_date: str | None = None
    #: countdown / countup: the date counted to or from.
    reference_date: str | None = None
    skip_weekends: bool = False
    skip_nonworkdays: bool = False
    #: ``unit: icon`` rows: day-class to icon rules.
    icon_rules: list[dict[str, Any]] = field(default_factory=list)
    icon_height: float | None = None

    def __post_init__(self) -> None:
        if self.every < 1:
            raise ValueError("every must be >= 1")
        if self.height <= 0:
            raise ValueError("height must be > 0")
        if self.week_start is not None and not 0 <= self.week_start <= 6:
            raise ValueError("week_start must be 0 (Monday) to 6 (Sunday)")
        if self.fiscal_year_start_month is not None and not 1 <= self.fiscal_year_start_month <= 12:
            raise ValueError("fiscal_year_start_month must be 1 to 12")
        if self.interval_days < 1:
            raise ValueError("interval_days must be >= 1")


@dataclass
class AxisSpec:
    """The axis line that axis views (timeline, pit) draw, and its direction."""

    show: bool = True
    orientation: Orientation = "horizontal"
    #: Gap between the axis line and its nearest row.
    padding: float = 4.0
    #: Bounding size of the built-in event / milestone dot on the axis.
    marker_size: float = 7.0


@dataclass
class Timescale:
    """The one declaration of timebands, ticks and the axis, used by every view.

    ``primary`` and ``secondary`` are the two sides of the axis.  In a table view
    primary is above the content and secondary below; beside a horizontal axis
    primary is above the axis, beside a vertical axis it is the right.  Candybar
    draws primary on its right and secondary on its left.
    """

    axis: AxisSpec = field(default_factory=AxisSpec)
    primary: list[TimescaleRow] = field(default_factory=list)
    secondary: list[TimescaleRow] = field(default_factory=list)
    #: A row whose segments are narrower than this (points) is dropped.
    min_segment_width: float = 3.0
    #: Alignment of the row headings in the label column.
    heading_align: Align = "end"

    def __post_init__(self) -> None:
        if self.min_segment_width < 0:
            raise ValueError("min_segment_width must be >= 0")


# ─── today, holidays, shading, fiscal, week numbers ──────────────────────────


@dataclass
class TodayHighlight:
    """How the current day is marked inside a day box or calendar cell."""

    show: bool = False
    color: str = "lightblue"
    opacity: float = 1.0


@dataclass
class Today:
    """The "today" mark.  The line itself is styled by ``lines.today``."""

    show: bool = True
    #: YYYYMMDD to pretend it is that day; ``None`` uses the clock.
    date: str | None = None
    label: str = "Today"
    label_position: Literal["start", "middle", "end"] = "end"
    label_offset: float = 5.0
    #: Length of the line in points; 0 = the full height of the chart area.
    length: float = 0.0
    #: Which side(s) of an axis the line extends to.
    direction: Side = "both"
    highlight: TodayHighlight = field(default_factory=TodayHighlight)


@dataclass
class DayClass:
    """Treatment of one class of non-working day."""

    color: str | None = None
    opacity: float = 0.25
    #: Icon drawn for the day; a federal holiday's country flag wins when it has one.
    icon: str | None = None


@dataclass
class Holidays:
    """Holiday handling, common to every view."""

    federal: DayClass = field(default_factory=lambda: DayClass(color="red"))
    company: DayClass = field(default_factory=lambda: DayClass(color="green"))
    weekend: DayClass = field(default_factory=lambda: DayClass(opacity=0.15))
    show_icons: bool = True
    icon_size: float = 10.0
    #: ``None`` keeps each flag's own colours.
    icon_color: str | None = None
    icon_y_offset: float = 4.0
    show_dates: bool = True
    date_format: str = "M/D"
    date_font_size: float | None = None
    date_color: str | None = None


@dataclass
class Shading:
    """Background shading of calendar cells.  Weekend and holiday tints are ``holidays.*``."""

    #: Strength of the per-month alternate tint (candybar, weekly).
    month_opacity: float = 0.12


@dataclass
class WeekNumbers:
    label_format: str = "W{num}"


@dataclass
class Fiscal:
    label_format: str = "{prefix}{period_short}"
    year_offset: int | None = None
    use_period_colors: bool = False
    #: Month the fiscal year starts (1-12).
    year_start_month: int = 2
    #: First day of the week, 0 = Monday ... 6 = Sunday.
    week_start: int = 0
    period_opacity: float = 0.25

    def __post_init__(self) -> None:
        if not 1 <= self.year_start_month <= 12:
            raise ValueError("year_start_month must be 1 to 12")
        if not 0 <= self.week_start <= 6:
            raise ValueError("week_start must be 0 (Monday) to 6 (Sunday)")


# ─── events, durations and the rest of the shared blocks ─────────────────────


@dataclass
class EventDate:
    show: bool = False
    format: str = "M/D"
    font_size: float | None = None


@dataclass
class EventMarker:
    radius: float = 4.0
    stroke_color: str = ""
    stroke_width: float = 1.0


@dataclass
class Events:
    """Point events and milestones, in every view."""

    #: Order of items within a lane / list, e.g. ``[wbs, start_date]``.
    item_placement_order: list[str | dict[str, Any]] = field(default_factory=lambda: ["wbs", "start_date"])
    date: EventDate = field(default_factory=EventDate)
    marker: EventMarker = field(default_factory=EventMarker)

    def __post_init__(self) -> None:
        from shared.rule_engine import EVENT_CRITERIA_KEYS

        if not isinstance(self.item_placement_order, list) or not self.item_placement_order:
            raise ValueError("item_placement_order must be a non-empty list of placement tokens")
        for token in self.item_placement_order:
            if isinstance(token, dict):
                bad = [k for k in token if k not in EVENT_CRITERIA_KEYS]
                if bad:
                    raise ValueError(
                        f"item_placement_order criteria token has unrecognized keys {bad!r}; "
                        f"valid criteria keys are {sorted(EVENT_CRITERIA_KEYS)}"
                    )
            elif not isinstance(token, str) or not token.strip():
                raise ValueError(
                    f"item_placement_order tokens must be non-empty strings or criteria dicts, got {token!r}"
                )


@dataclass
class DurationDates:
    show_start: bool = False
    show_end: bool = False
    format: str = "M/D"
    font_size: float | None = None
    color: str | None = None


@dataclass
class Durations:
    """Durations, in every view."""

    #: Icon set (a key of the program's icon sets) used when numbering durations.
    number_duration_icons: str = "darksquare"
    #: True gives each duration one numbered icon from the set in place of the
    #: icon its event names; false uses the named icon and ignores the set.
    replace_icons_with_numbers: bool = True
    icon_size: float = 8.0
    icon_background_color: str | None = None
    icon_stroke_color: str | None = None
    stroke_dasharray: str | None = None
    #: Draw the duration's icon at all (timeline, blockplan).
    show_icons: bool = True
    #: Ink of a duration bar's name; unset picks black or white for contrast with the bar.
    name_color: str | None = None
    #: Leading WBS segments that share one colour; 0 = colour by the event's own colour / priority.
    wbs_group_depth: int = 2
    dates: DurationDates = field(default_factory=DurationDates)

    def __post_init__(self) -> None:
        if self.wbs_group_depth < 0:
            raise ValueError("wbs_group_depth must be >= 0")


@dataclass
class Continuation:
    """The mark on a duration that runs past the start or end of the range."""

    show: bool = True
    icon_before: str | list[str] = "arrow-left"
    icon_after: str | list[str] = "arrow-right"
    icon_height: float = 8.0
    icon_color: str | None = "black"


@dataclass
class Overflow:
    icon: str = "warningtriangle"


@dataclass
class Watermark:
    text: str | None = None
    image: str | None = None
    font_family: str | None = font_field()
    font_size: int | None = None
    resize_mode: Literal["fit", "fill", "none"] = "fit"
    opacity: float = 0.5
    rotation_angle: float = 45.0
    image_rotation_angle: float = 45.0


@dataclass
class Margin:
    top: float | str = 0
    bottom: float | str = 0
    left: float | str = 0
    right: float | str = 0


@dataclass
class Layout:
    margin: Margin = field(default_factory=Margin)


# ─── run details document ────────────────────────────────────────────────────


@dataclass
class DetailsMarkdown:
    enable: bool = True
    title_text: str = "Calendar Details"
    sections: list[str] = field(default_factory=lambda: ["events", "colors", "symbols", "exceptions", "holidays"])
    events_section_text: str = "Events"
    colors_section_text: str = "Color Key"
    symbols_section_text: str = "Icons & Symbols"
    exceptions_section_text: str = "Exceptions"
    holidays_section_text: str = "Holidays & Special Days"
    empty_exceptions_text: str = "Every item was drawn as scheduled."
    empty_cell_text: str = ""
    icon_mode: Literal["file", "inline", "none"] = "file"
    color_mode: Literal["swatch", "name", "hex"] = "swatch"
    group_by: str = "none"
    sort: list[str] = field(default_factory=lambda: ["start_date", "end_date", "name"])
    columns: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"field": "source_id", "header": "ID", "align": "right"},
            {"field": "marker", "header": "Key", "align": "center"},
            {"field": "original_icon", "header": "Event Icon"},
            {"field": "name", "header": "Task Name", "indent": True},
            {"field": "category", "header": "Type"},
            {"field": "status", "header": "Status"},
            {"field": "priority", "header": "Pri", "align": "right"},
            {"field": "wbs", "header": "WBS"},
            {"field": "percent_complete", "header": "%", "align": "right", "format": "{:.0%}"},
            {"field": "start_date", "header": "Start", "date_format": "YYYY-MM-DD"},
            {"field": "end_date", "header": "Finish", "date_format": "YYYY-MM-DD"},
            {"field": "resource_names", "header": "Resources"},
            {"field": "resource_group", "header": "Group"},
            {"field": "assigned_color", "header": "Color"},
            {"field": "notes", "header": "Notes", "max_lines": 3},
            {"field": "drawn", "header": "Drawn"},
        ]
    )
    exception_columns: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"field": "issue", "header": "Issue"},
            {"field": "task", "header": "Task"},
            {"field": "date", "header": "Date", "date_format": "YYYY-MM-DD"},
            {"field": "ref", "header": "Ref"},
            {"field": "detail", "header": "Detail"},
        ]
    )
    holiday_columns: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"field": "icons", "header": "Icon", "align": "center"},
            {"field": "date", "header": "Date"},
            {"field": "name", "header": "Name"},
            {"field": "kind", "header": "Kind"},
            {"field": "nonworkday", "header": "Non-work"},
            {"field": "notes", "header": "Notes"},
        ]
    )


@dataclass
class DetailsIcons:
    enable: bool = True
    size: float = 16.0


@dataclass
class DetailsCsv:
    enable: bool = True
    columns: str | list[dict[str, Any]] = "exportdata"
    render_columns: bool = True


@dataclass
class Details:
    markdown: DetailsMarkdown = field(default_factory=DetailsMarkdown)
    icons: DetailsIcons = field(default_factory=DetailsIcons)
    csv: DetailsCsv = field(default_factory=DetailsCsv)


# ─── conditional content rules ───────────────────────────────────────────────


@dataclass
class StyleRule:
    """Restyle matching content.  Rules define nothing: the roles above are the definitions.

    ``apply_to`` is a role reference (``box:duration``, ``text:event_name`` ...) or a
    list of them.  ``select`` picks the events or days; ``style`` holds the
    attributes of that role to override.
    """

    name: str
    apply_to: str | list[str]
    select: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)


#: Selector keys a rule may use.  Context selectors (visualizer, papersize) are
#: gone: styles are view-independent, and paper size scaling is ``size_by_paper``.
SELECTOR_KEYS: frozenset[str] = frozenset(
    {
        "event_type",
        "task_name",
        "notes",
        "resource_group",
        "resource_names",
        "wbs",
        "milestone",
        "rollup",
        "federal_holiday",
        "company_holiday",
        "nonworkday",
        "workday",
        "weekend",
        "priority",
        "priority_min",
        "priority_max",
        "percent_complete",
        "value",
        "date",
        "date_overlap",
        "color",
        "icon",
        "min_match",
        "any_event",
        "all_events",
    }
)


# ─── view structure blocks ───────────────────────────────────────────────────


@dataclass
class Labella:
    """Label placement tuning shared by timeline and pit."""

    layer_gap: float = 8.0
    node_height: float = 24.0
    density: float = 0.75
    min_pos: float | None = None
    max_pos: float | None = None


@dataclass
class WeeklyDayBox:
    hash_pattern: str | None = None
    hash_pattern_opacity: float = 0.15
    #: Pattern tiles larger than this are scaled down to it (0 = tile at native size).
    hash_pattern_target_size: float = 18.0
    #: Extra multiplier on the tile size.
    hash_pattern_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.hash_pattern_target_size < 0:
            raise ValueError("hash_pattern_target_size must be >= 0 (0 disables auto-normalization)")
        if self.hash_pattern_scale <= 0:
            raise ValueError("hash_pattern_scale must be > 0")


@dataclass
class Weekly:
    day_box: WeeklyDayBox = field(default_factory=WeeklyDayBox)


@dataclass
class MiniGlyphs:
    """Database glyph groups (``glyphs`` table).  ``None`` uses the font's own digits."""

    day_number: str | None = None
    day_number_digits: str | None = None


@dataclass
class MiniCalendar:
    icon_set: str = "squares"
    title_format: str = "MMMM YYYY"
    show_adjacent: bool = True
    adjacent_month_color: str = "lightgrey"
    adjacent_month_opacity: float = 1.0
    circle_milestones: bool = False
    #: Event / holiday icons in a day cell's corners: share of the shorter cell side.
    event_icon_scale: float = 0.25
    event_icon_opacity: float = 0.6
    grid_lines: bool = False
    month_outline: LineSpec | None = None
    glyphs: MiniGlyphs = field(default_factory=MiniGlyphs)


@dataclass
class TextMiniGlyphs:
    """Glyph groups from the database ``glyphs`` table, one per role.

    The symbol roles default to the seeded groups; an unset digit role uses the font's own digits.
    """

    event: str | None = "text-mini-event"
    milestone: str | None = "text-mini-milestone"
    duration: str | None = "text-mini-duration"
    holiday: str | None = "text-mini-holiday"
    nonworkday: str | None = "text-mini-nonworkday"
    day_number_digits: str | None = None
    week_number_digits: str | None = None
    #: Group holding the single glyph that fills the days of a duration.
    duration_fill: str | None = "duration-fill"


@dataclass
class TextMini:
    cell_width: int = 2
    month_gap: int = 4
    glyphs: TextMiniGlyphs = field(default_factory=TextMiniGlyphs)

    def __post_init__(self) -> None:
        if self.cell_width < 1:
            raise ValueError("cell_width must be >= 1")


@dataclass
class Candybar:
    #: 0 = derive from the page.
    row_height: float = 0.0
    cell_width: float = 0.0
    weeknum_col_ratio: float = 0.6
    month_col_ratio: float = 1.6
    #: -1 = follow ``fiscal.week_start``.
    week_start: int = -1
    suppress_weekends: bool | None = None
    show_week_numbers: bool = True
    max_rows_per_page: int = 0
    grid_lines: bool = True
    month_shading: bool = False


@dataclass
class TimelineEvents:
    box_width: float | None = None
    box_height: float | None = None
    #: ``packed`` stacks boxes from their start date; ``labella`` force-solves their placement.
    placement: Literal["packed", "labella"] = "packed"
    row_gap: float | None = None
    box_gap: float = 2.0
    inner_pad: float = 2.0
    icon_column_ratio: float = 0.15


@dataclass
class TimelineDurations:
    box_width: float | None = None
    box_height: float | None = None
    icon_column_ratio: float | None = None


@dataclass
class Timeline:
    label_side: Side = "primary"
    duration_side: Literal["primary", "secondary", "opposite"] = "opposite"
    duration_offset_y: float = 20.0
    duration_lane_gap_y: float = 8.0
    labella: Labella = field(default_factory=Labella)
    events: TimelineEvents = field(default_factory=TimelineEvents)
    durations: TimelineDurations = field(default_factory=TimelineDurations)


@dataclass
class PitLabel:
    padding_x: float = 6.0
    padding_y: float = 3.0
    icon_size: float | None = None
    icon_gap: float = 4.0


@dataclass
class Pit:
    label_side: Side = "both"
    leader_label_anchor: Literal["start", "center", "end"] = "center"
    #: Distance of the date text from its label, and where it sits.
    date_offset: float = 6.0
    date_placement: str = "inline"
    labella: Labella = field(default_factory=lambda: Labella(layer_gap=50.0, node_height=24.0, density=0.5))
    label: PitLabel = field(default_factory=PitLabel)


@dataclass
class CompactPlan:
    duration_line_width: float = 5.0
    #: Share of a bar's width each date column takes.
    duration_date_column_ratio: float = 0.04
    lane_spacing: float = 6.0
    milestone_flag_width: float = 7.0
    milestone_flag_height: float = 9.0
    show_milestone_labels: bool = True
    header_bottom_y: float | None = None
    show_axis_legend: bool = True
    legend_axis_text: str = "timeline"
    continuation_legend_text: str = "activity continues"
    continuation_before_legend_text: str = "activity began earlier"


@dataclass
class Blockplan:
    label_column_ratio: float = 0.16
    band_label_column_ratio: float | None = None
    show_unmatched_lane: bool = True
    unmatched_lane_name: str = "Unmatched"
    lane_match_mode: Literal["first", "all"] = "first"
    #: Lane definitions: name, match criteria, split_ratio, fill_color, label_color ...
    swimlanes: list[dict[str, Any]] = field(default_factory=list)
    lane_label_align_h: Align = "start"
    lane_label_align_v: Literal["top", "middle", "bottom"] = "middle"
    lane_label_rotation: float = 0.0
    lane_split_ratio: float = 0.5
    duration_bar_height: float = 8.0
    duration_row_gap: float | None = None


@dataclass
class GanttMarks:
    """Icon names (from the ``icon`` table) for the marks on a gantt chart."""

    milestone: str = "diamond-fill"
    deadline: str = "square-fill"
    rollup: str = "check"
    milestone_flag: str = "check"
    snapped_event: str = "arrow-left-circle"
    offchart_dependency: str = "crosssquare"
    link_ref_icon_families: list[str] = field(default_factory=lambda: ["circle-", "darkcircle-", "square-"])
    link_ref_family_size: int = 100
    link_ref_max_icons: int = 2


@dataclass
class GanttColumn:
    field: str
    header: str | None = None
    #: Share of the table width; unset takes the average of the columns that set one.
    width: float | None = None
    align: Align | None = None
    max_lines: int | None = None
    wrap: bool = False
    truncate: bool = True
    render: Literal["text", "icon"] = "text"
    icon: str | None = None
    format: str | None = None
    date_format: str | None = None
    indent: bool = False


@dataclass
class Gantt:
    #: Share of the content width given to the task table.
    table_width_ratio: float = 0.38
    row_height: float = 14.0
    header_row_height: float = 18.0
    indent_per_level: float = 8.0
    bar_height: float = 8.0
    #: Split the range across pages below this many points per day; 0 = never.
    min_day_width: float = 4.0
    float_opacity_scale: float = 0.4
    show_dependencies: bool = True
    marks: GanttMarks = field(default_factory=GanttMarks)
    columns: list[GanttColumn] = field(
        default_factory=lambda: [
            GanttColumn(field="link_ref", header="Ref", width=0.03, render="icon", align="middle"),
            GanttColumn(field="source_id", header="ID", width=0.035, align="end"),
            GanttColumn(field="name", header="Task Name", width=0.215, max_lines=2, indent=True),
            GanttColumn(field="status", header="Status", width=0.045),
            GanttColumn(field="priority", header="Pri", width=0.025, align="end"),
            GanttColumn(field="wbs", header="WBS", width=0.05),
            GanttColumn(field="rollup", header="Roll", width=0.02, render="icon", align="middle"),
            GanttColumn(field="milestone", header="MS", width=0.02, render="icon", align="middle"),
            GanttColumn(field="percent_complete", header="%", width=0.035, align="end", format="{:.0%}"),
            GanttColumn(field="effort_text", header="Effort", width=0.045, align="end"),
            GanttColumn(field="duration_text", header="Duration", width=0.045, align="end"),
            GanttColumn(field="start_date", header="Start", width=0.08, date_format="dd MM/DD/YY"),
            GanttColumn(field="end_date", header="Finish", width=0.08, date_format="dd MM/DD/YY"),
            GanttColumn(field="resource_names", header="Resources", width=0.065, max_lines=1),
            GanttColumn(field="resource_group", header="Group", width=0.055),
            GanttColumn(field="notes", header="Notes", width=0.075, max_lines=2),
            GanttColumn(field="deadline", header="Deadline", width=0.08, date_format="dd MM/DD/YY"),
        ]
    )


@dataclass
class ExcelBlockplan:
    """Excel-only formatting, in Excel units and Excel-installed font names."""

    font_name: str = "Calibri"
    font_size: int = 9
    column_width: float | None = None


# ─── the theme ───────────────────────────────────────────────────────────────


@dataclass
class ThemeMeta:
    name: str
    version: str = THEME_VERSION
    description: str = ""


@dataclass
class Theme:
    """A parsed version-3.0 theme."""

    theme: ThemeMeta
    fonts: Fonts = field(default_factory=Fonts)
    text: TextRoles = field(default_factory=TextRoles)
    boxes: BoxRoles = field(default_factory=BoxRoles)
    icons: IconRoles = field(default_factory=IconRoles)
    lines: LineRoles = field(default_factory=LineRoles)
    palettes: Palettes = field(default_factory=Palettes)
    timescale: Timescale = field(default_factory=Timescale)
    today: Today = field(default_factory=Today)
    holidays: Holidays = field(default_factory=Holidays)
    shading: Shading = field(default_factory=Shading)
    week_numbers: WeekNumbers = field(default_factory=WeekNumbers)
    fiscal: Fiscal = field(default_factory=Fiscal)
    events: Events = field(default_factory=Events)
    durations: Durations = field(default_factory=Durations)
    continuation: Continuation = field(default_factory=Continuation)
    overflow: Overflow = field(default_factory=Overflow)
    watermark: Watermark = field(default_factory=Watermark)
    layout: Layout = field(default_factory=Layout)
    details: Details = field(default_factory=Details)
    style_rules: list[StyleRule] = field(default_factory=list)
    # view structure
    weekly: Weekly = field(default_factory=Weekly)
    mini_calendar: MiniCalendar = field(default_factory=MiniCalendar)
    text_mini: TextMini = field(default_factory=TextMini)
    candybar: Candybar = field(default_factory=Candybar)
    timeline: Timeline = field(default_factory=Timeline)
    pit: Pit = field(default_factory=Pit)
    compact_plan: CompactPlan = field(default_factory=CompactPlan)
    blockplan: Blockplan = field(default_factory=Blockplan)
    gantt: Gantt = field(default_factory=Gantt)
    excelblockplan: ExcelBlockplan = field(default_factory=ExcelBlockplan)
