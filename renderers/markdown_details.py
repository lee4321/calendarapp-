"""
The run's details document: ``<stem>.md`` beside the chart.

Everything a reader needs to use the chart, written from the render
record (:mod:`renderers.details_record`) rather than re-derived from the
data:

* **Events** -- the theme's ``details.markdown.columns``, in the same
  column schema as ``gantt.columns``, over every events-table field plus
  what the render assigned: the icons and marks each event was drawn
  with, its color, whether it was drawn at all;
* **Color Key** -- every color handed out, where it came from, and how
  many events carry it;
* **Icons & Symbols** -- every icon file in the run folder and what it
  means;
* **Exceptions** -- what the chart could not show faithfully;
* **Holidays & Special Days** -- the days the chart shows that carry one.

Icons are image links into the run folder's ``icons/``; every file there
is the same size, so the tables line up without per-image attributes.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from renderers.details_fields import ICON_FIELDS
from renderers.details_record import ROLE_MEANINGS, EventNote, IconUse, mark
from renderers.table_columns import TableColumn, cell_icon_visible, cell_value, resolve_field, resolve_table_columns
from shared.holiday_listing import format_datekey
from shared.wbs_filter import wbs_depth, wbs_sort_key

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from renderers.details_record import DetailsRecord
    from shared.run_paths import RunPaths

SECTION_EVENTS = "events"
SECTION_COLORS = "colors"
SECTION_SYMBOLS = "symbols"
SECTION_EXCEPTIONS = "exceptions"
SECTION_HOLIDAYS = "holidays"
DEFAULT_SECTIONS: tuple[str, ...] = (
    SECTION_EVENTS,
    SECTION_COLORS,
    SECTION_SYMBOLS,
    SECTION_EXCEPTIONS,
    SECTION_HOLIDAYS,
)

#: Prefix of the metadata line that changes on every run.
GENERATED_PREFIX = "- **Generated:**"

_ALIGN_MARKERS = {"left": ":---", "center": ":---:", "right": "---:"}
_ELLIPSIS = "…"


# ── Rows ─────────────────────────────────────────────────────────────────────


class RowView:
    """One table row: named fields first, then the event, then its raw row.

    Columns read values by attribute (see :func:`cell_value`), so a row
    that layers render-derived fields over an event reads exactly like
    the event on the chart does.
    """

    __slots__ = ("_event", "_fields", "_raw")

    def __init__(self, fields: dict[str, Any], event: Any = None, raw: dict | None = None):
        object.__setattr__(self, "_fields", fields)
        object.__setattr__(self, "_event", event)
        object.__setattr__(self, "_raw", raw or {})

    def __getattr__(self, name: str) -> Any:
        fields = object.__getattribute__(self, "_fields")
        if name in fields:
            return fields[name]
        event = object.__getattribute__(self, "_event")
        if event is not None and hasattr(event, name):
            return getattr(event, name)
        lowered = name.lower()
        for key, value in object.__getattribute__(self, "_raw").items():
            if str(key).lower() == lowered:
                return value
        return None


def event_view(record: DetailsRecord, note: EventNote, ranks: dict[str, int]) -> RowView:
    """*note* as a row: its event, with what the render assigned it."""
    color = note.assigned_color
    refs = ", ".join(note.refs)
    return RowView(
        {
            "icons": list(note.icons),
            "icon": next((use for use in note.icons if not use.is_mark), None),
            "marker": record.marker_for(note),
            "event_icon": note.event.icon,
            "assigned_color": color,
            "color_source": note.color_source,
            "category": note.category,
            "lane": note.lane,
            "drawn": note.drawn,
            "page": note.page,
            "ref": refs,
            "link_ref": refs,
            "exceptions": record.exception_count(note) or None,
            "continues_before": note.continues_before,
            "continues_after": note.continues_after,
            "color_rank": ranks.get(color.strip().lower()) if color else None,
            "_order": note.order,
        },
        note.event,
        note.raw,
    )


def _scalar_key(value: Any) -> tuple[int, Any]:
    """Comparable key for one field, keeping mixed types sortable."""
    if value is None or value == "":
        return (2, "")
    if isinstance(value, (bool, int, float)):
        return (0, float(value))
    return (1, str(value).lower())


def sort_views(views: list[RowView], sort_fields: Sequence[str]) -> list[RowView]:
    """Order rows by *sort_fields*, in the vocabulary ``gantt.sort`` uses."""

    def key(view: RowView) -> tuple:
        parts: list[Any] = []
        for name in sort_fields:
            name = str(name).strip()
            if name == "wbs":
                wbs = view.wbs
                parts.append((0 if (wbs or "").strip() else 1, wbs_sort_key(wbs)))
            else:
                parts.append(_scalar_key(getattr(view, resolve_field(name))))
        parts.append(view._order)
        return tuple(parts)

    return sorted(views, key=key)


def ordered_event_views(record: DetailsRecord, config: CalendarConfig) -> list[RowView]:
    """Every event row, in the order the Events table lists them."""
    ranks = record.color_ranks()
    views = [event_view(record, note, ranks) for note in record.events]
    sort_fields = list(getattr(config, "details_md_sort", None) or ["start_date", "end_date", "name"])
    return sort_views(views, sort_fields)


# ── Cells ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class IconLinks:
    """How an icon appears in a cell: an image link, its name, or nothing."""

    paths: dict[IconUse, str]
    mode: str = "file"

    def ref(self, use: IconUse) -> str:
        if self.mode == "none":
            return ""
        alt = _alt_text(use)
        path = self.paths.get(use)
        if self.mode == "file" and path:
            return f"![{alt}]({path})"
        return f"`{alt}`"


def _alt_text(use: IconUse) -> str:
    text = f"{use.label} {use.color}" if use.is_mark and use.color else use.label
    return text.replace("[", "(").replace("]", ")").replace("|", "/").replace("`", "'")


def escape_text(text: Any) -> str:
    """*text* safe as a heading or list item: one line, no raw tags."""
    return " ".join(str(text).split()).replace("<", "&lt;").replace(">", "&gt;")


def escape_cell(text: str, max_lines: int = 1) -> str:
    """*text* made safe inside a GFM table cell."""
    text = html.escape(str(text), quote=False).replace("|", "\\|")
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    joiner = "<br>" if max_lines > 1 else " "
    return joiner.join(line.strip() for line in lines if line.strip() or max_lines > 1).strip()


def _truncate(text: str, max_chars: int | None) -> str:
    if max_chars and len(text) > max_chars:
        return text[: max(0, max_chars - 1)].rstrip() + _ELLIPSIS
    return text


def _as_uses(value: Any, role: str) -> list[IconUse]:
    """An icon field's value as icon uses: a list, one use, or a bare name."""
    if not value:
        return []
    if isinstance(value, IconUse):
        return [value]
    if isinstance(value, str):
        return [IconUse(value.strip().lower(), None, role)]
    return [use if isinstance(use, IconUse) else IconUse(str(use).strip().lower(), None, role) for use in value]


def color_cell(color: str, links: IconLinks, mode: str) -> str:
    code = f"`{escape_cell(color)}`"
    if mode == "hex":
        return code
    if mode == "name":
        return escape_cell(color)
    return f"{links.ref(mark('swatch', color))} {code}".strip()


def render_cell(column: TableColumn, row: RowView, links: IconLinks, color_mode: str, empty: str) -> str:
    """One Markdown cell."""
    attr = column.attr
    if attr in ICON_FIELDS:
        refs = [links.ref(use) for use in _as_uses(getattr(row, attr), column.field)]
        return " ".join(ref for ref in refs if ref) or empty
    if attr == "assigned_color":
        color = getattr(row, attr)
        return color_cell(str(color), links, color_mode) if color else empty
    if column.render == "icon":
        if column.icon and cell_icon_visible(column, row):
            return links.ref(IconUse(column.icon.strip().lower(), None, column.field)) or "Yes"
        return empty
    text = escape_cell(_truncate(cell_value(column, row), column.max_chars), column.max_lines)
    if not text:
        return empty
    if column.indent:
        text = "&nbsp;&nbsp;" * wbs_depth(getattr(row, "wbs", None)) + text
    return text


def table(columns: Sequence[TableColumn], rows: Iterable[list[str]]) -> list[str]:
    """A GFM table: header, alignment row, then *rows*."""
    lines = [
        "| " + " | ".join(escape_cell(column.header) for column in columns) + " |",
        "| " + " | ".join(_ALIGN_MARKERS.get(column.align, ":---") for column in columns) + " |",
    ]
    lines.extend("| " + " | ".join(cells) + " |" for cells in rows)
    return lines


# ── Document ─────────────────────────────────────────────────────────────────


def document_icon_uses(record: DetailsRecord, config: CalendarConfig, holiday_rows: list[dict]) -> list[IconUse]:
    """Every icon the document shows, once each: what the export writes."""
    seen: dict[IconUse, None] = dict.fromkeys(record.all_icon_uses())
    for column in resolve_table_columns(getattr(config, "details_md_columns", None), config):
        if column.render == "icon" and column.icon and column.attr not in ICON_FIELDS:
            use = IconUse(column.icon.strip().lower(), None, column.field)
            if any(cell_icon_visible(column, note.event) for note in record.events):
                seen.setdefault(use, None)
    for row in holiday_rows:
        for use in holiday_icons(record, row):
            seen.setdefault(use, None)
    return list(seen)


def holiday_icons(record: DetailsRecord, row: dict) -> list[IconUse]:
    """The icons the chart drew for a holiday row, or the one it names."""
    drawn = record.holiday_icons.get(row.get("raw_name") or row.get("name") or "")
    if drawn:
        return list(drawn)
    icon = str(row.get("icon") or "").strip().lower()
    return [IconUse(icon, None, "holiday")] if icon else []


def build_markdown(
    record: DetailsRecord,
    config: CalendarConfig,
    run_paths: RunPaths,
    holiday_rows: list[dict],
    icon_paths: dict[IconUse, str],
    generated: datetime | None = None,
) -> str:
    """The details document for one run."""
    links = IconLinks(icon_paths, str(getattr(config, "details_md_icon_mode", "file") or "file").lower())
    color_mode = str(getattr(config, "details_md_color_mode", "swatch") or "swatch").lower()
    empty = escape_cell(getattr(config, "details_md_empty_cell_text", "") or "")

    lines = _metadata(record, config, run_paths, generated)
    sections = list(getattr(config, "details_md_sections", None) or DEFAULT_SECTIONS)
    for section in sections:
        name = str(section).strip().lower()
        if name == SECTION_EVENTS:
            lines += _events_section(record, config, links, color_mode, empty)
        elif name == SECTION_COLORS:
            lines += _colors_section(record, config, links)
        elif name == SECTION_SYMBOLS:
            lines += _symbols_section(record, config, links, holiday_rows)
        elif name == SECTION_EXCEPTIONS:
            lines += _exceptions_section(record, config, links, color_mode, empty)
        elif name == SECTION_HOLIDAYS:
            lines += _holidays_section(record, config, links, color_mode, empty, holiday_rows)
    return "\n".join(lines).rstrip() + "\n"


def _metadata(
    record: DetailsRecord,
    config: CalendarConfig,
    run_paths: RunPaths,
    generated: datetime | None,
) -> list[str]:
    title = getattr(config, "details_md_title_text", None) or "Calendar Details"
    start = format_datekey(getattr(config, "adjustedstart", ""))
    end = format_datekey(getattr(config, "adjustedend", ""))
    lines = [f"# {escape_text(title)}", "", f"- **Visualization:** {escape_text(record.visualizer)}"]
    if start or end:
        lines.append(f"- **Date range:** {start} – {end}")
    theme_name = _theme_name(config)
    if theme_name:
        lines.append(f"- **Theme:** {escape_text(theme_name)}")
    stamp = (generated or datetime.now()).strftime("%Y-%m-%d %H:%M")
    lines.append(f"{GENERATED_PREFIX} {stamp}")
    command = getattr(config, "command_line", "")
    if command:
        lines.append(f"- **Command:** `{str(command).replace('`', "'")}`")
    files = [f"[{run_paths.main.name}]({run_paths.main.name})"]
    if getattr(config, "include_details_csv", False):
        files.append(f"[{run_paths.csv.name}]({run_paths.csv.name})")
    lines += [f"- **Files:** {' · '.join(files)}", ""]
    return lines


def _theme_name(config: CalendarConfig) -> str:
    """The applied theme's ``theme.name``, or ``""``."""
    theme = getattr(config, "theme", None)
    section = getattr(theme, "section", None)
    if not callable(section):
        return ""
    try:
        name = (section("theme") or {}).get("name")
    except (AttributeError, KeyError, TypeError):
        return ""
    return str(name) if name else ""


def _heading(config: CalendarConfig, attr: str, default: str) -> list[str]:
    return [f"## {escape_text(getattr(config, attr, None) or default)}", ""]


def _plain_columns(entries: Any, config: CalendarConfig) -> list[TableColumn]:
    """Columns over a table's own fields, where the events-table aliases do not apply.

    ``name`` on a holiday row is the holiday's name and ``task`` on an
    exception is its task -- not ``Event.task_name``.
    """
    return [replace(column, attr=column.field.strip().lower()) for column in resolve_table_columns(entries, config)]


def _events_section(
    record: DetailsRecord,
    config: CalendarConfig,
    links: IconLinks,
    color_mode: str,
    empty: str,
) -> list[str]:
    lines = _heading(config, "details_md_events_section_text", "Events")
    columns = resolve_table_columns(getattr(config, "details_md_columns", None), config)
    views = ordered_event_views(record, config)
    if not views or not columns:
        return [*lines, "No events in the range.", ""]

    group_by = str(getattr(config, "details_md_group_by", "none") or "none").strip()
    if group_by.lower() in ("", "none"):
        rows = [[render_cell(c, v, links, color_mode, empty) for c in columns] for v in views]
        return [*lines, *table(columns, rows), ""]

    attr = resolve_field(group_by)
    groups: dict[str, list[RowView]] = {}
    for view in views:
        value = getattr(view, attr)
        groups.setdefault("" if value is None else str(value), []).append(view)
    for value, members in groups.items():
        lines += [f"### {escape_text(value) or '(none)'}", ""]
        rows = [[render_cell(c, v, links, color_mode, empty) for c in columns] for v in members]
        lines += [*table(columns, rows), ""]
    return lines


def _colors_section(record: DetailsRecord, config: CalendarConfig, links: IconLinks) -> list[str]:
    lines = _heading(config, "details_md_colors_section_text", "Color Key")
    entries: dict[str, tuple[str, list[str], list[str]]] = {}
    for entry in record.colors:
        _color, labels, sources = entries.setdefault(entry.color.strip().lower(), (entry.color, [], []))
        if entry.label and entry.label not in labels:
            labels.append(entry.label)
        if entry.source and entry.source not in sources:
            sources.append(entry.source)
    counts: dict[str, int] = {}
    for note in record.events:
        if not note.assigned_color:
            continue
        key = note.assigned_color.strip().lower()
        counts[key] = counts.get(key, 0) + 1
        _color, _labels, sources = entries.setdefault(key, (note.assigned_color, [], []))
        if note.color_source and note.color_source not in sources:
            sources.append(note.color_source)
    if not entries:
        return [*lines, "No colors were assigned.", ""]

    columns = _fixed_columns(("Swatch", "center"), ("Color", "left"), ("Assigned to", "left"), ("Source", "left"))
    columns.append(_fixed_columns(("Events", "right"))[0])
    rows = [
        [
            links.ref(mark("swatch", color)),
            f"`{escape_cell(color)}`",
            escape_cell(", ".join(labels)),
            escape_cell(", ".join(sources)),
            str(counts.get(key, 0)),
        ]
        for key, (color, labels, sources) in entries.items()
    ]
    return [*lines, *table(columns, rows), ""]


def _symbols_section(
    record: DetailsRecord,
    config: CalendarConfig,
    links: IconLinks,
    holiday_rows: list[dict],
) -> list[str]:
    lines = _heading(config, "details_md_symbols_section_text", "Icons & Symbols")
    uses = document_icon_uses(record, config, holiday_rows)
    if not uses:
        return [*lines, "No icons were drawn.", ""]
    meanings = {symbol.icon: symbol.meaning for symbol in record.symbols}
    used_by: dict[IconUse, int] = {}
    for note in record.events:
        for use in record.marker_for(note):
            used_by[use] = used_by.get(use, 0) + 1
    for row in holiday_rows:
        for use in holiday_icons(record, row):
            used_by[use] = used_by.get(use, 0) + 1

    columns = _fixed_columns(("Icon", "center"), ("Name", "left"), ("Role", "left"), ("Meaning", "left"))
    columns.append(_fixed_columns(("Used by", "right"))[0])
    rows = [
        [
            links.ref(use),
            f"`{escape_cell(use.label)}`" + (f" `{escape_cell(use.color)}`" if use.color else ""),
            escape_cell(use.role),
            escape_cell(meanings.get(use) or ROLE_MEANINGS.get(use.role) or use.role.replace("_", " ").capitalize()),
            str(used_by.get(use, 0) or ""),
        ]
        for use in uses
    ]
    return [*lines, *table(columns, rows), ""]


def _exceptions_section(
    record: DetailsRecord,
    config: CalendarConfig,
    links: IconLinks,
    color_mode: str,
    empty: str,
) -> list[str]:
    lines = _heading(config, "details_md_exceptions_section_text", "Exceptions")
    columns = _plain_columns(getattr(config, "details_md_exception_columns", None), config)
    if not record.exceptions or not columns:
        text = getattr(config, "details_md_empty_exceptions_text", None) or "Every item was drawn as scheduled."
        return [*lines, escape_cell(text), ""]
    views = [
        RowView(
            {
                "visualizer": e.visualizer,
                "kind": e.kind,
                "issue": e.issue,
                "task": e.task,
                "date": e.datekey,
                "start": e.start,
                "end": e.end,
                "ref": e.ref,
                "detail": e.detail,
            }
        )
        for e in sorted(record.exceptions, key=lambda e: (e.datekey or e.start, e.task, e.kind))
    ]
    rows = [[render_cell(c, v, links, color_mode, empty) for c in columns] for v in views]
    return [*lines, *table(columns, rows), ""]


def _holidays_section(
    record: DetailsRecord,
    config: CalendarConfig,
    links: IconLinks,
    color_mode: str,
    empty: str,
    holiday_rows: list[dict],
) -> list[str]:
    lines = _heading(config, "details_md_holidays_section_text", "Holidays & Special Days")
    columns = _plain_columns(getattr(config, "details_md_holiday_columns", None), config)
    if not holiday_rows or not columns:
        return [*lines, "No holidays or special days in the range.", ""]
    views = [RowView({**row, "icons": holiday_icons(record, row)}) for row in holiday_rows]
    rows = [[render_cell(c, v, links, color_mode, empty) for c in columns] for v in views]
    return [*lines, *table(columns, rows), ""]


def _fixed_columns(*specs: tuple[str, str]) -> list[TableColumn]:
    """Columns for the document's own fixed tables."""
    return [TableColumn(field=header, attr=header, header=header, width=0.0, align=align) for header, align in specs]
