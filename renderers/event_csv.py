"""
The run's event CSV: ``<stem>.csv`` beside the chart.

One row per event the visualization was given, in the order the details
document lists them.  By default the columns are the ``exportdata``
set -- so the file re-imports through ``importers/import_events.py`` --
followed by what the render assigned each event (its color, icons, lane,
whether it was drawn).  The importer ignores columns it does not know, so
the render columns ride along without breaking the round trip.

A theme can instead name its own columns, in the same schema as
``gantt.columns``.
"""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

from renderers.details_fields import ICON_FIELDS
from renderers.table_columns import TableColumn, cell_icon_visible, cell_value, resolve_table_columns

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from renderers.details_record import DetailsRecord
    from renderers.markdown_details import RowView

#: The export column set that re-imports as-is.
EXPORTDATA = "exportdata"

#: Render-derived columns appended when ``details.csv.render_columns`` is on.
RENDER_COLUMNS: tuple[str, ...] = (
    "assigned_color",
    "color_source",
    "icons",
    "category",
    "lane",
    "drawn",
    "page",
    "exceptions",
)


def _icon_names(value: Any) -> str:
    from renderers.markdown_details import _as_uses

    return ";".join(use.label for use in _as_uses(value, "icon"))


def _render_values(view: RowView) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in RENDER_COLUMNS:
        value = getattr(view, name)
        if name == "icons":
            values[name] = _icon_names(value)
        else:
            values[name] = "" if value is None else value
    return values


def csv_cell(column: TableColumn, view: RowView) -> str:
    """One CSV cell: names for icons, formatted text for everything else."""
    if column.attr in ICON_FIELDS:
        return _icon_names(getattr(view, column.attr))
    if column.attr == "assigned_color":
        return str(getattr(view, column.attr) or "")
    if column.render == "icon":
        return column.icon or "" if cell_icon_visible(column, view) else ""
    return cell_value(column, view)


def build_event_csv(record: DetailsRecord, config: CalendarConfig) -> str:
    """The event CSV for one run."""
    from renderers.markdown_details import ordered_event_views

    views = ordered_event_views(record, config)
    spec = getattr(config, "details_csv_columns", EXPORTDATA)
    with_render = bool(getattr(config, "details_csv_render_columns", True))
    buffer = io.StringIO()

    if not spec or isinstance(spec, str):
        from cli.exportdata import _EXPORTDATA_COLUMNS, _event_to_row

        fieldnames = list(_EXPORTDATA_COLUMNS) + (list(RENDER_COLUMNS) if with_render else [])
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for view in views:
            row = _event_to_row(view._raw)
            if with_render:
                row.update(_render_values(view))
            writer.writerow(row)
        return buffer.getvalue()

    columns = resolve_table_columns(spec, config)
    extra = [name for name in RENDER_COLUMNS if with_render and name not in {c.field for c in columns}]
    plain = csv.writer(buffer, lineterminator="\n")
    plain.writerow([column.header for column in columns] + extra)
    for view in views:
        rendered = _render_values(view) if extra else {}
        plain.writerow([csv_cell(column, view) for column in columns] + [rendered[name] for name in extra])
    return buffer.getvalue()
