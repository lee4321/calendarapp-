"""
Gantt task-table column model.

Columns are *layout* configuration, not style: which fields appear, in
what order, how wide, how aligned, and how a value becomes text.  They
come from ``config.gantt_columns`` (themes write ``gantt.columns:``);
``style_rules`` govern only how the resulting cells look.

The model itself is shared with the run's details document and event
CSV -- see :mod:`renderers.table_columns`.  What lives here is the
chart's own use of it: the gantt column list, and cell geometry.

The value pipeline is one pass per cell:

    event field → :func:`cell_value` (format / date_format / icon)
                → :func:`renderers.text_utils.fit_lines`  (wrap to the
                                      column width, then truncate with
                                      an ellipsis; re-exported here)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from renderers.table_columns import (  # noqa: F401  (re-exported)
    FIELD_ALIASES,
    LINK_REF_FIELD,
    TableColumn,
    cell_icon_visible,
    cell_value,
    resolve_field,
    resolve_table_columns,
)
from renderers.text_utils import ELLIPSIS, fit_lines  # noqa: F401  (re-exported)

if TYPE_CHECKING:
    from config.config import CalendarConfig

#: The gantt's name for a resolved column.
GanttColumn = TableColumn


def resolve_columns(config: CalendarConfig) -> list[GanttColumn]:
    """Build the task-table column list from ``config.gantt_columns``."""
    return resolve_table_columns(getattr(config, "gantt_columns", None), config)


def column_x_positions(columns: list[GanttColumn], table_x: float, table_w: float) -> list[tuple[float, float]]:
    """Return ``(x, width)`` in page units for each column, left to right."""
    positions: list[tuple[float, float]] = []
    cursor = table_x
    for column in columns:
        width = table_w * column.width
        positions.append((cursor, width))
        cursor += width
    return positions
