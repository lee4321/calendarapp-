"""
Render record: what a visualization actually drew, kept for its run details.

A renderer writes into a :class:`DetailsRecord` while it draws -- which
events it placed, the icons and marks it gave each one, the colors it
assigned, and everything it could not show faithfully.  The run's
details document, event CSV and icon files are written from the record
afterwards (see :mod:`renderers.run_details`), so nothing is re-derived
from the data: the document says what the chart shows because the chart
told it.

Every exception kind any visualizer reports is registered here, so the
vocabulary is one list however many views use it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from shared.data_models import Event

# ── Exception vocabulary ─────────────────────────────────────────────────────

#: A duration bar reaching past the chart's last day.
KIND_CLIPPED_END = "clipped_end"
#: A duration bar beginning before the chart's first day.
KIND_CLIPPED_START = "clipped_start"
#: A single-day event drawn on the next working day because its own day is
#: not on the axis.
KIND_SNAPPED_EVENT = "snapped_event"
#: A holiday that cannot be shaded because it falls on a hidden weekend.
KIND_HIDDEN_HOLIDAY = "hidden_holiday"
#: An item whose whole span is hidden, so nothing is drawn for it.
KIND_UNDRAWN = "undrawn"
#: A dependency whose predecessor is not on the chart.
KIND_OFFCHART_DEPENDENCY = "offchart_dependency"
#: A predecessor token that could not be parsed at all.
KIND_UNPARSEABLE_PREDECESSOR = "unparseable_predecessor"
#: A predecessor referencing a source_id no task carries.
KIND_UNRESOLVED_PREDECESSOR = "unresolved_predecessor"
#: An item that did not fit in its day box.
KIND_OVERFLOW = "overflow"
#: An icon a day cell had no room for.
KIND_ICON_DROPPED = "icon_dropped"
#: A label shortened to fit its space.
KIND_NAME_TRUNCATED = "name_truncated"
#: A date label left out for want of room.
KIND_DATE_OMITTED = "date_omitted"
#: A callout whose label box found no room on the page.
KIND_LABEL_UNPLACED = "label_unplaced"
#: An item in a lane past the page's last drawable lane.
KIND_LANE_CLIPPED = "lane_clipped"
#: An item no swimlane matched.
KIND_UNASSIGNED_LANE = "unassigned_lane"
#: A multi-day item a point-in-time view does not draw.
KIND_MULTI_DAY_SKIPPED = "multi_day_skipped"

#: Human-readable summaries, keyed by kind.
KIND_LABELS: dict[str, str] = {
    KIND_CLIPPED_END: "Bar continues past the end of the range",
    KIND_CLIPPED_START: "Bar begins before the start of the range",
    KIND_SNAPPED_EVENT: "Moved to the next working day",
    KIND_HIDDEN_HOLIDAY: "Holiday hidden with its weekend",
    KIND_UNDRAWN: "Not drawn — every day of the span is hidden",
    KIND_OFFCHART_DEPENDENCY: "Predecessor is not on the chart",
    KIND_UNPARSEABLE_PREDECESSOR: "Predecessor could not be parsed",
    KIND_UNRESOLVED_PREDECESSOR: "Predecessor does not match any task",
    KIND_OVERFLOW: "Did not fit in its day",
    KIND_ICON_DROPPED: "Icon left out for want of room",
    KIND_NAME_TRUNCATED: "Name shortened to fit",
    KIND_DATE_OMITTED: "Date left out for want of room",
    KIND_LABEL_UNPLACED: "Label could not be placed",
    KIND_LANE_CLIPPED: "Lane runs past the page",
    KIND_UNASSIGNED_LANE: "Matched no swimlane",
    KIND_MULTI_DAY_SKIPPED: "Multi-day item not shown on a point-in-time view",
}


def split_reference(detail: str) -> tuple[str, str]:
    """Pull a leading ``"<icon>: "`` tag out of an exception's detail.

    Cross-page dependency entries are recorded as ``"circle-7: depends on
    …"`` so the number and the prose can be shown in their own columns
    without a second field on every exception.
    """
    text = str(detail or "")
    icon, separator, rest = text.partition(": ")
    if separator and " " not in icon:
        return icon, rest
    return "", text


# ── Events ───────────────────────────────────────────────────────────────────

CATEGORY_EVENT = "event"
CATEGORY_MILESTONE = "milestone"
CATEGORY_DURATION = "duration"

DRAWN_YES = "yes"
DRAWN_PARTIAL = "partial"
DRAWN_NO = "no"

#: Prefix of a mark: something drawn as geometry rather than a DB icon.
MARK_PREFIX = "mark-"

#: Mark kinds the icon exporter knows how to draw.
MARK_KINDS: frozenset[str] = frozenset({"swatch", "bar", "flag", "diamond", "bracket", "dot", "fill"})


@dataclass(frozen=True)
class IconUse:
    """One icon (or mark) as it was drawn.

    Attributes:
        icon: The icon name actually drawn -- the fallback's when the
            requested one was missing -- or ``mark-<kind>`` for geometry.
        color: The color it was painted, or None for its own colors.
        role: What it was drawn for: ``milestone``, ``duration``,
            ``continuation``, ``holiday``, ``swatch`` ...
    """

    icon: str
    color: str | None
    role: str

    @property
    def is_mark(self) -> bool:
        return self.icon.startswith(MARK_PREFIX)

    @property
    def label(self) -> str:
        """The name a reader sees: the icon name, or the mark kind."""
        return self.icon[len(MARK_PREFIX) :] if self.is_mark else self.icon


def mark(kind: str, color: str | None, role: str | None = None) -> IconUse:
    """An :class:`IconUse` for a mark of *kind* drawn in *color*."""
    return IconUse(f"{MARK_PREFIX}{kind}", color, role or kind)


#: css_class → role, where the class name does not say it plainly.
_ROLE_BY_CLASS: dict[str, str] = {
    "ec-milestone-marker": "milestone",
    "ec-duration-marker": "duration",
    "ec-duration-icon": "duration",
    "ec-event-icon": "event",
    "ec-continuation-icon": "continuation",
    "ec-overflow-icon": "overflow",
    "ec-legend-icon": "holiday",
    "ec-holiday-icon": "holiday",
}


def role_for_class(css_class: str | None) -> str:
    """The role an icon drawn with *css_class* plays."""
    if not css_class:
        return "icon"
    name = str(css_class).split()[0]
    if name in _ROLE_BY_CLASS:
        return _ROLE_BY_CLASS[name]
    name = name.removeprefix("ec-")
    for suffix in ("-icon", "-marker", "-glyph", "-mark"):
        name = name.removesuffix(suffix)
    return name.replace("-", "_") or "icon"


#: What each role means, for the Icons & Symbols table.
ROLE_MEANINGS: dict[str, str] = {
    "milestone": "Milestone",
    "duration": "Duration",
    "event": "Event",
    "start": "Start of a duration",
    "continuation": "Continues beyond the visible range",
    "continuation_before": "Began before the visible range",
    "continuation_after": "Continues past the visible range",
    "overflow": "Day had more items than fit",
    "holiday": "Holiday or special day",
    "nonworkday": "Non-working day",
    "day_number": "Day number",
    "bar": "Duration bar in its assigned color",
    "swatch": "Assigned color",
    "flag": "Milestone flag",
    "diamond": "Milestone",
    "bracket": "Rollup span",
    "fill": "Day fill",
    "rollup": "Rollup",
    "deadline": "Deadline",
    "link_ref": "Dependency on another page",
    "offchart": "Predecessor is not on the chart",
    "axis": "Timeline axis",
    "dot": "Event marker",
    "snapped": "Moved to the next working day",
    "symbol": "Symbol",
}


def event_key(event: Any) -> tuple:
    """The key an event is known by across the record.

    The database id when there is one; otherwise name and span, which is
    what distinguishes two rows a test builds by hand.
    """
    if isinstance(event, dict):
        event = Event.from_dict(event)
    db_id = getattr(event, "db_id", None)
    if db_id is not None:
        return ("id", db_id)
    return ("span", event.task_name or "", str(event.start or "")[:8], str(event.end or "")[:8])


def event_category(event: Event) -> str:
    if event.milestone:
        return CATEGORY_MILESTONE
    if str(event.start or "")[:8] != str(event.end or "")[:8]:
        return CATEGORY_DURATION
    return CATEGORY_EVENT


def raw_row_for(event: Event) -> dict:
    """*event* as the database row dict the CSV export reads."""
    return {
        "ID": event.db_id,
        "User_ID": event.user_id,
        "Import_ID": event.import_id,
        "Task_Name": event.task_name,
        "Status": event.status,
        "Start": event.start,
        "End": event.end,
        "Earliest_Start_Date": event.earliest_start_date,
        "Latest_Start_Date": event.latest_start_date,
        "Earliest_End_Date": event.earliest_end_date,
        "Latest_End_Date": event.latest_end_date,
        "Priority": event.priority,
        "WBS": event.wbs,
        "Rollup": event.rollup,
        "Milestone": event.milestone,
        "Percent_Complete": event.percent_complete,
        "Effort": event.effort,
        "Effort_Text": event.effort_text,
        "Duration": event.duration,
        "Duration_Text": event.duration_text,
        "Predecessors": event.predecessors,
        "Resource_Names": event.resource_names,
        "Resource_Group": event.resource_group,
        "Notes": event.notes,
        "Icon": event.icon,
        "Color": event.color,
        "Tags": event.tags,
        "Source_ID": event.source_id,
        "Critical": event.critical,
        "Start_Time": event.start_time,
        "End_Time": event.end_time,
        "Actual_Start_Date": event.actual_start_date,
        "Actual_Start_Time": event.actual_start_time,
        "Actual_End_Date": event.actual_end_date,
        "Actual_End_Time": event.actual_end_time,
        "Deadline": event.deadline,
        "Start_Variance": event.start_variance,
        "Finish_Variance": event.finish_variance,
        "Cost": event.cost,
        "Fixed_Cost": event.fixed_cost,
        "Percent_Work_Complete": event.percent_work_complete,
        "Successors": event.successors,
        "Custom1": event.custom1,
        "Custom2": event.custom2,
        "Custom3": event.custom3,
        "Custom4": event.custom4,
        "Custom5": event.custom5,
    }


@dataclass
class EventNote:
    """One event the render was given, and what became of it."""

    event: Event
    raw: dict
    order: int
    icons: list[IconUse] = field(default_factory=list)
    assigned_color: str | None = None
    color_source: str | None = None
    category: str = CATEGORY_EVENT
    lane: str | None = None
    drawn: str = DRAWN_NO
    page: int | None = None
    refs: list[str] = field(default_factory=list)
    continues_before: bool = False
    continues_after: bool = False

    def add_icon(self, use: IconUse) -> None:
        """Keep *use* once, in the order the chart first drew it."""
        if use not in self.icons:
            self.icons.append(use)

    def mark_drawn(self, drawn: str = DRAWN_YES) -> None:
        """Record that the chart drew this event.

        ``partial`` and ``no`` set by an exception are not overwritten by
        a later ``yes``: one clipped segment is enough to make it partial.
        """
        if drawn == DRAWN_YES:
            if self.drawn == DRAWN_NO:
                self.drawn = DRAWN_YES
        else:
            self.drawn = drawn


# ── Colors, symbols, exceptions ──────────────────────────────────────────────


@dataclass(frozen=True)
class ColorEntry:
    """One color the visualization handed out."""

    color: str
    label: str
    source: str


@dataclass(frozen=True)
class SymbolEntry:
    """A symbol the chart uses, with what it means."""

    icon: IconUse
    meaning: str


@dataclass(frozen=True)
class DetailsException:
    """One thing the render could not show faithfully."""

    visualizer: str
    kind: str
    task: str = ""
    datekey: str = ""
    start: str = ""
    end: str = ""
    ref: str = ""
    detail: str = ""
    key: tuple | None = field(default=None, compare=False)

    @property
    def issue(self) -> str:
        """The human-readable summary for this entry's kind."""
        return KIND_LABELS.get(self.kind, self.kind.replace("_", " ").capitalize())


#: Owner of an icon: an event, a holiday (by name), or nothing.
IconOwner = EventNote | str | None


class DetailsRecord:
    """Everything one render drew, for its run details."""

    def __init__(self, visualizer: str, events: Iterable[Any] = ()):
        self.visualizer = visualizer
        self.events: list[EventNote] = []
        self._by_key: dict[tuple, EventNote] = {}
        self.colors: list[ColorEntry] = []
        self.symbols: list[SymbolEntry] = []
        self.unowned_icons: list[IconUse] = []
        self.holiday_icons: dict[str, list[IconUse]] = {}
        self.exceptions: list[DetailsException] = []
        self.visible_daykeys: list[str] = []
        for event in events:
            self.add_event(event)

    # ── Events ───────────────────────────────────────────────────────────

    def add_event(self, event: Any) -> EventNote:
        """Register an event the render was given; returns its note."""
        parsed = event if isinstance(event, Event) else Event.from_dict(event)
        key = event_key(parsed)
        note = self._by_key.get(key)
        if note is not None:
            return note
        raw = dict(event) if isinstance(event, dict) else raw_row_for(parsed)
        note = EventNote(event=parsed, raw=raw, order=len(self.events), category=event_category(parsed))
        self.events.append(note)
        self._by_key[key] = note
        return note

    def note_for(self, event: Any) -> EventNote:
        """The note for *event*, registering it if the render made it up."""
        return self._by_key.get(event_key(event)) or self.add_event(event)

    def find(self, task: str, start: str = "", end: str = "") -> EventNote | None:
        """The first event with this name (and span, when given)."""
        for note in self.events:
            if (note.event.task_name or "") != (task or ""):
                continue
            if start and str(note.event.start)[:8] != str(start)[:8]:
                continue
            if end and str(note.event.end)[:8] != str(end)[:8]:
                continue
            return note
        return None

    # ── Icons ────────────────────────────────────────────────────────────

    def record_icon(self, use: IconUse, owner: IconOwner = None) -> None:
        """Attach *use* to its owner, or keep it as the chart's own."""
        if isinstance(owner, EventNote):
            owner.add_icon(use)
        elif isinstance(owner, str):
            uses = self.holiday_icons.setdefault(owner, [])
            if use not in uses:
                uses.append(use)
        elif use not in self.unowned_icons:
            self.unowned_icons.append(use)

    def marker_for(self, note: EventNote) -> list[IconUse]:
        """The event's key mark: its geometry marks, then its icons.

        An event with an assigned color but no mark of its own leads with
        a swatch in that color, so every colored row keys its color.
        """
        marks = [use for use in note.icons if use.is_mark]
        icons = [use for use in note.icons if not use.is_mark]
        if not marks and note.assigned_color:
            marks = [mark("swatch", note.assigned_color)]
        return marks + icons

    def all_icon_uses(self) -> list[IconUse]:
        """Every icon and mark the record holds, once each, in first-use order."""
        seen: dict[IconUse, None] = {}
        for note in self.events:
            for use in self.marker_for(note):
                seen.setdefault(use, None)
        for note in self.events:
            # The Color column and the Color Key show every assigned
            # color as a swatch, marked or not.
            if note.assigned_color:
                seen.setdefault(mark("swatch", note.assigned_color), None)
        for uses in self.holiday_icons.values():
            for use in uses:
                seen.setdefault(use, None)
        for symbol in self.symbols:
            seen.setdefault(symbol.icon, None)
        for use in self.unowned_icons:
            seen.setdefault(use, None)
        for entry in self.colors:
            seen.setdefault(mark("swatch", entry.color), None)
        return list(seen)

    # ── Colors and symbols ───────────────────────────────────────────────

    def add_color(self, color: str | None, label: str, source: str) -> None:
        if not color:
            return
        entry = ColorEntry(str(color), str(label), str(source))
        if not any(c.color.lower() == entry.color.lower() and c.label == entry.label for c in self.colors):
            self.colors.append(entry)

    def add_symbol(self, use: IconUse, meaning: str) -> None:
        if not any(s.icon == use for s in self.symbols):
            self.symbols.append(SymbolEntry(use, meaning))

    def color_ranks(self) -> dict[str, int]:
        """Rank of each color by assignment order.

        The colors the assignment handed out come first, in its order;
        any other color an event was drawn in follows, in order of first
        appearance by start date.
        """
        ranks: dict[str, int] = {}
        for entry in self.colors:
            ranks.setdefault(entry.color.strip().lower(), len(ranks))
        for note in sorted(self.events, key=lambda n: (n.event.start, n.event.end, n.order)):
            if note.assigned_color:
                ranks.setdefault(note.assigned_color.strip().lower(), len(ranks))
        return ranks

    # ── Exceptions ───────────────────────────────────────────────────────

    def add_exception(
        self,
        kind: str,
        task: str = "",
        datekey: str = "",
        *,
        start: str = "",
        end: str = "",
        ref: str = "",
        detail: str = "",
        event: Any = None,
    ) -> DetailsException:
        entry = DetailsException(
            visualizer=self.visualizer,
            kind=kind,
            task=str(task or ""),
            datekey=str(datekey or ""),
            start=str(start or ""),
            end=str(end or ""),
            ref=str(ref or ""),
            detail=str(detail or ""),
            key=event_key(event) if event is not None else None,
        )
        self.exceptions.append(entry)
        return entry

    def exception_count(self, note: EventNote) -> int:
        """How many exceptions concern *note*'s event."""
        key = event_key(note.event)
        name = note.event.task_name or ""
        return sum(1 for e in self.exceptions if (e.key == key) if e.key is not None) + sum(
            1 for e in self.exceptions if e.key is None and name and e.task == name
        )
