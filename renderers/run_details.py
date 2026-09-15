"""
Write a run's details into its folder: icon files, details document, CSV.

Called once a visualization has drawn -- by
:meth:`renderers.svg_base.BaseSVGRenderer.render` for the SVG views and
by the text-mini visualizer -- with the render record the drawing filled
in.  Each output has its own switch (``details.markdown.enable``,
``details.icons.enable``, ``details.csv.enable``); the icon files are
written first so the document can link exactly the files that exist.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from renderers.event_csv import build_event_csv
from renderers.icon_export import export_icons
from renderers.markdown_details import build_markdown, document_icon_uses
from shared.holiday_listing import holiday_special_rows

if TYPE_CHECKING:
    from pathlib import Path

    from config.config import CalendarConfig
    from renderers.details_record import DetailsRecord, IconUse
    from shared.db_access import CalendarDB
    from shared.run_paths import RunPaths

logger = logging.getLogger(__name__)

#: Icon size when the theme names none, in SVG user units.
DEFAULT_ICON_SIZE = 16.0


def visible_daykeys(record: DetailsRecord, config: CalendarConfig) -> list[str]:
    """The days whose holidays the document lists.

    What the renderer said it showed; failing that, every day of the
    configured range.
    """
    if record.visible_daykeys:
        return sorted(set(record.visible_daykeys))
    try:
        start = datetime.strptime(str(config.adjustedstart), "%Y%m%d").date()
        end = datetime.strptime(str(config.adjustedend), "%Y%m%d").date()
    except (TypeError, ValueError):
        return []
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return [day.strftime("%Y%m%d") for day in days]


def write_run_details(
    record: DetailsRecord,
    config: CalendarConfig,
    db: CalendarDB | None,
    run_paths: RunPaths,
    resolve_markup: Callable[[str], str | None] | None = None,
    generated: datetime | None = None,
) -> list[Path]:
    """Write every enabled output for one run; returns the files written."""
    want_markdown = bool(getattr(config, "include_details_markdown", True))
    want_icons = bool(getattr(config, "include_details_icons", True))
    want_csv = bool(getattr(config, "include_details_csv", True))
    written: list[Path] = []

    holiday_rows: list[dict] = []
    if db is not None and (want_markdown or want_icons):
        holiday_rows = holiday_special_rows(visible_daykeys(record, config), config, db)

    run_paths.folder.mkdir(parents=True, exist_ok=True)

    icon_paths: dict[IconUse, str] = {}
    if want_icons:
        size = float(getattr(config, "details_icons_size", None) or DEFAULT_ICON_SIZE)
        icon_paths = export_icons(document_icon_uses(record, config, holiday_rows), run_paths, size, resolve_markup)
        written.extend(run_paths.folder / path for path in sorted(set(icon_paths.values())))

    if want_markdown:
        text = build_markdown(record, config, run_paths, holiday_rows, icon_paths, generated)
        run_paths.markdown.write_text(text, encoding="utf-8")
        written.append(run_paths.markdown)

    if want_csv:
        run_paths.csv.write_text(build_event_csv(record, config), encoding="utf-8", newline="")
        written.append(run_paths.csv)

    logger.info("Run details written to %s (%d files)", run_paths.folder, len(written))
    return written
