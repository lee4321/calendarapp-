"""Excel workbook generator for the ``excelblockplan`` subcommand.

Writes a blockplan-style ``.xlsx`` sheet: timeband header rows, a column-header
row naming every events-table column, then one row per event and duration in
the date range.  With ``--empty`` (no events or durations) the sheet ends at
the column-header row, which gives a blank planning template.

Layout
------
The three column landmarks are derived from ``FIXED_COLUMNS``, so adding a
column there moves everything to its right.  With the current list the label
block is A-AS, the continuation column is AT and the days start at AU.

Label block      : project-tracking labels — one per ``events`` table column,
                   in the order ``events.sql`` declares them (see
                   ``FIXED_COLUMNS``)
CONTINUATION_COL : marker when a duration extends beyond the visible range
FIRST_DATE_COL+  : one column per visible calendar day (width = 3 chars)
Rows 1..N        : timeband rows — heading label placed in the last label
                   column, segment values starting at FIRST_DATE_COL
Row  N+1         : column-header row with the label names
Rows N+2..       : one row per event/duration after filtering, ordered by
                   start_date

For each data row:
    - The label columns hold the corresponding events-table field values.
    - CONTINUATION_COL holds a marker when a duration extends past the
      visible range (left ◀ / right ▶ / both ◀▶ glyph).
    - Single-day events place the resolved icon name in the start-date day
      column.  The icon cell font colour and fill come from ``style_rules``
      evaluated for the event.
    - Multi-day durations fill every day column between start and end with the
      style-resolved colour.
    - After all data is drawn, holiday/special-day shading is applied to the
      date columns.  Cells that already carry data are decorated with a
      ``lightUp`` pattern that visibly combines the holiday colour and the
      underlying data colour so both remain visible.

No freeze pane is set and the label columns are never frozen: rows are
independent records meant for full-sheet sort/filter, and the label block is
far wider than a screen.

The CLI mirrors ``blockplan`` (content filters, theme, weekends, country, etc.).
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import arrow
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import ImageColor

from renderers.timescale import Plan, ScaleContext, plan_rows
from shared.data_models import Event
from shared.day_classifier import classify_days
from shared.number_icons import number_duration_icons
from shared.rule_engine import DayContext, StyleEngine
from shared.span import Span
from visualizers.base import filter_events

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


def _resolve_excel_token(config: CalendarConfig, token: str) -> dict:
    """The theme's style dictionary for the role ``token`` (``{}`` when the theme has no such role)."""
    from config import role_styles

    return role_styles.token(config.theme_v3, token, config.papersize)


# ── Constants ─────────────────────────────────────────────────────────────────

# Fixed label columns — one per events-table column the user can plan around,
# in the order events.sql declares them.  The schedule data elements added
# after the original schema follow `tags`, matching both the DDL and the
# migration order so the sheet, the table and the importer all read alike.
#
# Everything downstream derives from this list's length, so adding a column
# here shifts the continuation marker and the whole date grid automatically.
FIXED_COLUMNS: list[tuple[str, float]] = [
    ("id", 6),
    ("status", 9),
    ("priority", 8),
    ("wbs", 10),
    ("rollup", 7),
    ("milestone", 10),
    ("percent_complete", 10),
    ("name", 30),
    ("effort", 8),
    ("duration", 10),
    ("start_date", 12),
    ("end_date", 12),
    ("earliest_start_date", 14),
    ("latest_start_date", 14),
    ("earliest_end_date", 14),
    ("latest_end_date", 14),
    ("predecessors", 16),
    ("resource_names", 18),
    ("resource_group", 14),
    ("notes", 24),
    ("icon", 10),
    ("color", 10),
    ("tags", 12),
    # Schedule data elements
    ("source_id", 10),
    ("critical", 8),
    ("start_time", 9),
    ("end_time", 9),
    ("duration_text", 12),
    ("effort_text", 12),
    ("actual_start_date", 15),
    ("actual_start_time", 12),
    ("actual_end_date", 15),
    ("actual_end_time", 12),
    ("deadline", 12),
    ("start_variance", 13),
    ("finish_variance", 13),
    ("fixed_cost", 11),
    ("cost", 10),
    ("percent_work_complete", 15),
    ("successors", 16),
    ("custom1", 14),
    ("custom2", 14),
    ("custom3", 14),
    ("custom4", 14),
    ("custom5", 14),
]
LABEL_COL_END = len(FIXED_COLUMNS)  # 45 = column AS
CONTINUATION_COL = LABEL_COL_END + 1  # 46 = column AT
FIRST_DATE_COL = LABEL_COL_END + 2  # 47 = column AU
DAY_COL_WIDTH = 3.0  # Excel character-width units

# ISO 3166-1 alpha-2 → flag emoji
_COUNTRY_FLAGS: dict[str, str] = {
    "ad": "🇦🇩",
    "ae": "🇦🇪",
    "af": "🇦🇫",
    "ag": "🇦🇬",
    "ai": "🇦🇮",
    "al": "🇦🇱",
    "am": "🇦🇲",
    "ao": "🇦🇴",
    "ar": "🇦🇷",
    "as": "🇦🇸",
    "at": "🇦🇹",
    "au": "🇦🇺",
    "aw": "🇦🇼",
    "az": "🇦🇿",
    "ba": "🇧🇦",
    "bb": "🇧🇧",
    "bd": "🇧🇩",
    "be": "🇧🇪",
    "bf": "🇧🇫",
    "bg": "🇧🇬",
    "bh": "🇧🇭",
    "bi": "🇧🇮",
    "bj": "🇧🇯",
    "bl": "🇧🇱",
    "bm": "🇧🇲",
    "bn": "🇧🇳",
    "bo": "🇧🇴",
    "br": "🇧🇷",
    "bs": "🇧🇸",
    "bt": "🇧🇹",
    "bw": "🇧🇼",
    "by": "🇧🇾",
    "bz": "🇧🇿",
    "ca": "🇨🇦",
    "cc": "🇨🇨",
    "cd": "🇨🇩",
    "cf": "🇨🇫",
    "cg": "🇨🇬",
    "ch": "🇨🇭",
    "ci": "🇨🇮",
    "ck": "🇨🇰",
    "cl": "🇨🇱",
    "cm": "🇨🇲",
    "cn": "🇨🇳",
    "co": "🇨🇴",
    "cr": "🇨🇷",
    "cu": "🇨🇺",
    "cv": "🇨🇻",
    "cy": "🇨🇾",
    "cz": "🇨🇿",
    "de": "🇩🇪",
    "dj": "🇩🇯",
    "dk": "🇩🇰",
    "dm": "🇩🇲",
    "do": "🇩🇴",
    "dz": "🇩🇿",
    "ec": "🇪🇨",
    "ee": "🇪🇪",
    "eg": "🇪🇬",
    "es": "🇪🇸",
    "et": "🇪🇹",
    "fi": "🇫🇮",
    "fj": "🇫🇯",
    "fr": "🇫🇷",
    "ga": "🇬🇦",
    "gb": "🇬🇧",
    "gd": "🇬🇩",
    "ge": "🇬🇪",
    "gh": "🇬🇭",
    "gm": "🇬🇲",
    "gn": "🇬🇳",
    "gq": "🇬🇶",
    "gr": "🇬🇷",
    "gt": "🇬🇹",
    "gu": "🇬🇺",
    "gw": "🇬🇼",
    "gy": "🇬🇾",
    "hk": "🇭🇰",
    "hn": "🇭🇳",
    "hr": "🇭🇷",
    "ht": "🇭🇹",
    "hu": "🇭🇺",
    "id": "🇮🇩",
    "ie": "🇮🇪",
    "il": "🇮🇱",
    "in": "🇮🇳",
    "iq": "🇮🇶",
    "ir": "🇮🇷",
    "is": "🇮🇸",
    "it": "🇮🇹",
    "jm": "🇯🇲",
    "jo": "🇯🇴",
    "jp": "🇯🇵",
    "ke": "🇰🇪",
    "kg": "🇰🇬",
    "kh": "🇰🇭",
    "ki": "🇰🇮",
    "km": "🇰🇲",
    "kn": "🇰🇳",
    "kp": "🇰🇵",
    "kr": "🇰🇷",
    "kw": "🇰🇼",
    "ky": "🇰🇾",
    "kz": "🇰🇿",
    "la": "🇱🇦",
    "lb": "🇱🇧",
    "lc": "🇱🇨",
    "li": "🇱🇮",
    "lk": "🇱🇰",
    "lr": "🇱🇷",
    "ls": "🇱🇸",
    "lt": "🇱🇹",
    "lu": "🇱🇺",
    "lv": "🇱🇻",
    "ly": "🇱🇾",
    "ma": "🇲🇦",
    "mc": "🇲🇨",
    "md": "🇲🇩",
    "me": "🇲🇪",
    "mg": "🇲🇬",
    "mh": "🇲🇭",
    "mk": "🇲🇰",
    "ml": "🇲🇱",
    "mm": "🇲🇲",
    "mn": "🇲🇳",
    "mo": "🇲🇴",
    "mp": "🇲🇵",
    "mr": "🇲🇷",
    "ms": "🇲🇸",
    "mt": "🇲🇹",
    "mu": "🇲🇺",
    "mv": "🇲🇻",
    "mw": "🇲🇼",
    "mx": "🇲🇽",
    "my": "🇲🇾",
    "mz": "🇲🇿",
    "na": "🇳🇦",
    "ne": "🇳🇪",
    "ng": "🇳🇬",
    "ni": "🇳🇮",
    "nl": "🇳🇱",
    "no": "🇳🇴",
    "np": "🇳🇵",
    "nr": "🇳🇷",
    "nu": "🇳🇺",
    "nz": "🇳🇿",
    "om": "🇴🇲",
    "pa": "🇵🇦",
    "pe": "🇵🇪",
    "pf": "🇵🇫",
    "pg": "🇵🇬",
    "ph": "🇵🇭",
    "pk": "🇵🇰",
    "pl": "🇵🇱",
    "pr": "🇵🇷",
    "ps": "🇵🇸",
    "pt": "🇵🇹",
    "pw": "🇵🇼",
    "py": "🇵🇾",
    "qa": "🇶🇦",
    "ro": "🇷🇴",
    "rs": "🇷🇸",
    "ru": "🇷🇺",
    "rw": "🇷🇼",
    "sa": "🇸🇦",
    "sb": "🇸🇧",
    "sc": "🇸🇨",
    "sd": "🇸🇩",
    "se": "🇸🇪",
    "sg": "🇸🇬",
    "sh": "🇸🇭",
    "si": "🇸🇮",
    "sk": "🇸🇰",
    "sl": "🇸🇱",
    "sm": "🇸🇲",
    "sn": "🇸🇳",
    "so": "🇸🇴",
    "sr": "🇸🇷",
    "ss": "🇸🇸",
    "st": "🇸🇹",
    "sv": "🇸🇻",
    "sy": "🇸🇾",
    "sz": "🇸🇿",
    "tc": "🇹🇨",
    "td": "🇹🇩",
    "tg": "🇹🇬",
    "th": "🇹🇭",
    "tj": "🇹🇯",
    "tk": "🇹🇰",
    "tl": "🇹🇱",
    "tm": "🇹🇲",
    "tn": "🇹🇳",
    "to": "🇹🇴",
    "tr": "🇹🇷",
    "tt": "🇹🇹",
    "tv": "🇹🇻",
    "tz": "🇹🇿",
    "ua": "🇺🇦",
    "ug": "🇺🇬",
    "us": "🇺🇸",
    "uy": "🇺🇾",
    "uz": "🇺🇿",
    "va": "🇻🇦",
    "vc": "🇻🇨",
    "ve": "🇻🇪",
    "vg": "🇻🇬",
    "vi": "🇻🇮",
    "vn": "🇻🇳",
    "vu": "🇻🇺",
    "ws": "🇼🇸",
    "ye": "🇾🇪",
    "za": "🇿🇦",
    "zm": "🇿🇲",
    "zw": "🇿🇼",
}

# ── Colour helpers ────────────────────────────────────────────────────────────


def _to_argb(color: str | None) -> str | None:
    """Convert any CSS color string → openpyxl ARGB hex (e.g. ``'FF4472C4'``).

    Returns ``None`` for ``None``, ``"none"``, or ``"transparent"`` so callers
    can skip applying a fill when there is nothing to render.
    """
    if not color:
        return None
    c = color.strip().lower()
    if c in {"", "none", "transparent"}:
        return None
    try:
        rgb = ImageColor.getrgb(color)
        r, g, b = rgb[0], rgb[1], rgb[2]
        return f"FF{r:02X}{g:02X}{b:02X}"
    except (ValueError, KeyError, AttributeError):
        return None


def _solid_fill(color: str | None) -> PatternFill | None:
    argb = _to_argb(color)
    if argb is None:
        return None
    return PatternFill(start_color=argb, end_color=argb, fill_type="solid")


def _apply_fill(cell: Any, color: str | None) -> None:
    fill = _solid_fill(color)
    if fill is not None:
        cell.fill = fill


def _font_color_argb(color: str | None) -> str:
    """Return ARGB for a font color, defaulting to opaque black."""
    return _to_argb(color) or "FF000000"


# ── Segment helpers ───────────────────────────────────────────────────────────


def _col_for_day(day: date, visible_days: list[date], *, end: bool = False) -> int:
    """Return the 1-based Excel column index for *day*.

    When ``end=True`` the column corresponds to the *end_exclusive* boundary
    (i.e. the last column of a segment, inclusive).
    """
    idx = bisect_left(visible_days, day)
    if end:
        idx -= 1
    return FIRST_DATE_COL + max(0, idx)


# ── Visible-day helper ────────────────────────────────────────────────────────


def compute_visible_days(config: CalendarConfig) -> list[date]:
    """Return the ordered list of calendar dates that get a day column.

    Honors ``config.weekend_style`` (0 = weekdays only, 1+ = full week).
    Uses ``userstart``/``userend`` if present, otherwise the adjusted range.
    """
    range_start = str(config.userstart or config.adjustedstart)
    range_end = str(config.userend or config.adjustedend)
    start = arrow.get(range_start, "YYYYMMDD").date()
    end = arrow.get(range_end, "YYYYMMDD").date()
    if end < start:
        start, end = end, start
    weekend_style = int(getattr(config, "weekend_style", 0))
    visible: list[date] = []
    cursor = start
    while cursor <= end:
        if weekend_style == 0:
            if cursor.weekday() < 5:
                visible.append(cursor)
        else:
            visible.append(cursor)
        cursor += timedelta(days=1)
    return visible


# ── Holiday pre-fetch ─────────────────────────────────────────────────────────


def _build_holiday_map(
    visible_days: list[date],
    db: CalendarDB,
    config: CalendarConfig,
    federal_color: str,
    company_color: str,
    weekend_color: str | None,
) -> dict[date, dict]:
    """Return a dict mapping each non-workday to display info.

    Classification uses :func:`shared.day_classifier.classify_days` so
    blockplan and excelblockplan share one source of truth.
    Precedence when multiple classes match a single date:
    federal > company > weekend.
    """
    hmap: dict[date, dict] = {}
    classes_by_day = classify_days(visible_days, db, config)
    country = getattr(config, "country", None)
    for d in visible_days:
        classes = classes_by_day.get(d, frozenset())
        if not classes:
            continue
        daykey = d.strftime("%Y%m%d")
        if "federal_holiday" in classes:
            gov = [h for h in db.get_holidays_for_date(daykey, country) if h.get("nonworkday")]
            icon_key = str((gov[0].get("icon") if gov else "") or "").lower()
            emoji = _COUNTRY_FLAGS.get(icon_key, "🏛")
            hmap[d] = {
                "color": federal_color,
                "emoji": emoji,
                "name": str((gov[0].get("displayname") if gov else "") or ""),
                "is_nonwork": True,
                "class": "federal_holiday",
            }
            continue
        if "company_holiday" in classes:
            special = [s for s in db.get_special_days_for_date(daykey) if s.get("nonworkday")]
            day_color = str((special[0].get("daycolor") if special else "") or "").strip() or company_color
            icon_key = str((special[0].get("icon") if special else "") or "").lower()
            emoji = _COUNTRY_FLAGS.get(icon_key, "🏢")
            hmap[d] = {
                "color": day_color,
                "emoji": emoji,
                "name": str((special[0].get("name") if special else "") or ""),
                "is_nonwork": True,
                "class": "company_holiday",
            }
            continue
        if "weekend" in classes and weekend_color:
            hmap[d] = {
                "color": weekend_color,
                "emoji": "",
                "name": "",
                "is_nonwork": True,
                "class": "weekend",
            }
    return hmap


# ── Vertical-line → right-border mapping ─────────────────────────────────────


def _build_right_border_cols(plan: Plan) -> dict[int, dict]:
    """Return {excel_col: {color, style}}: a right border at the end of every cell of a row that has a ``vline``."""
    result: dict[int, dict] = {}
    for rp in plan.rows:
        line = rp.row.vline
        if line is None:
            continue
        for cell in rp.cells:
            col = FIRST_DATE_COL + round(cell.b) - 1
            result[col] = {"color": line.color, "style": "medium" if line.width > 1.5 else "thin"}
    return result


def _apply_right_border(cell: Any, style: str, color: str) -> None:
    """Add (or replace) just the right border on *cell* without disturbing others."""
    argb = _to_argb(color) or "FFFF0000"
    existing = cell.border
    cell.border = Border(
        left=existing.left,
        top=existing.top,
        bottom=existing.bottom,
        right=Side(border_style=style, color=argb),
    )


def _apply_overlay_fill(cell: Any, base_argb: str, overlay_color: str | None) -> None:
    """Decorate *cell* with both an existing base fill and a holiday/special-day
    overlay color.

    When the cell already carries event/duration data (``base_argb`` non-None)
    and a non-workday colour applies (``overlay_color`` non-None), use an
    Excel pattern fill that visibly combines the two — the holiday colour
    becomes the foreground stripes, the data colour stays as the background.
    Otherwise apply a plain solid fill.  Mirrors the “show both” rule from
    the spec for blockplan-style data sheets.
    """
    overlay_argb = _to_argb(overlay_color)
    if base_argb and overlay_argb:
        cell.fill = PatternFill(
            start_color=overlay_argb,
            end_color=base_argb,
            fill_type="lightUp",
        )
        return
    if overlay_argb is not None:
        cell.fill = PatternFill(start_color=overlay_argb, end_color=overlay_argb, fill_type="solid")


# ── Shared sheet-builder helpers ──────────────────────────────────────────────


_ALIGN_TO_EXCEL = {"start": "left", "middle": "center", "end": "right"}


def _tint(color: str | None, opacity: float) -> str | None:
    """*color* blended with white by *opacity*, as ``#rrggbb`` (Excel has no fill opacity)."""
    argb = _to_argb(color)
    if not argb:
        return None
    r, g, b = (int(argb[i : i + 2], 16) for i in (2, 4, 6))
    mix = lambda c: round(255 - (255 - c) * opacity)  # noqa: E731
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def _read_band_settings(config: CalendarConfig) -> dict:
    """Return the workbook font and the colours the sheet writers share, from the theme.

    Holiday colours are the theme's ``holidays`` fills blended with white by
    their opacity, since a cell fill cannot be translucent.
    """
    theme = config.theme_v3
    h = theme.holidays
    return {
        "font_name": theme.excelblockplan.font_name,
        "font_size": theme.excelblockplan.font_size,
        "header_heading_fill": theme.boxes.header.fill,
        "header_label_color": theme.text.band_label.color,
        "header_label_align_h": _ALIGN_TO_EXCEL[theme.timescale.heading_align],
        "federal_color": _tint(h.federal.color, h.federal.opacity) or "#FFE4E1",
        "company_color": _tint(h.company.color, h.company.opacity) or "#FFFACD",
        "weekend_color": _tint(h.weekend.color, h.weekend.opacity),
    }


def _setup_column_widths(ws: Any, visible_days: list[date], day_width: float = DAY_COL_WIDTH) -> None:
    """Set widths for the label columns, the continuation column and the days (``day_width``, Excel units)."""
    for col_idx, (_, width) in enumerate(FIXED_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    ws.column_dimensions[get_column_letter(CONTINUATION_COL)].width = day_width
    for i in range(len(visible_days)):
        ws.column_dimensions[get_column_letter(FIRST_DATE_COL + i)].width = day_width


def _write_timebands(
    ws: Any,
    *,
    plan: Plan,
    holiday_map: dict[date, dict],
    visible_days: list[date],
    settings: dict,
    start_row: int = 1,
) -> int:
    """Write the planned timescale rows and return the next free row index.

    The row heading is placed in the label columns (A to the last label column)
    by merging them.  Cells start at FIRST_DATE_COL, so the continuation column
    stays clear.  The plan is made with one unit of span per day column, so a
    cell's ``a`` and ``b`` are its first column offset and one past its last.
    """
    current_row = start_row
    for rp in plan.rows:
        font_name = settings["font_name"]
        font_size = rp.row.text.size if rp.row.text.size is not None else settings["font_size"]
        ws.row_dimensions[current_row].height = max(12.0, rp.height * 0.75)

        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=LABEL_COL_END)
        heading_cell = ws.cell(row=current_row, column=1, value=rp.heading or "")
        heading_cell.font = Font(
            name=font_name, size=int(font_size), bold=True, color=_font_color_argb(settings["header_label_color"])
        )
        heading_cell.alignment = Alignment(
            horizontal=settings["header_label_align_h"], vertical="center", wrap_text=False
        )
        _apply_fill(heading_cell, settings["header_heading_fill"])

        for cell in rp.cells:
            col_s = FIRST_DATE_COL + round(cell.a)
            col_e = FIRST_DATE_COL + round(cell.b) - 1
            if col_e < col_s:
                continue
            text = cell.label
            if cell.icons:
                text = "".join(_COUNTRY_FLAGS.get(i.name.lower(), "●") for i in cell.icons)
            elif col_s == col_e and 0 <= col_s - FIRST_DATE_COL < len(visible_days):
                held = holiday_map.get(visible_days[col_s - FIRST_DATE_COL])
                if held and held["emoji"]:
                    text = held["emoji"]

            if col_e > col_s:
                ws.merge_cells(start_row=current_row, start_column=col_s, end_row=current_row, end_column=col_e)
            seg_cell = ws.cell(row=current_row, column=col_s, value=text)
            seg_cell.font = Font(name=font_name, size=int(font_size), color=_font_color_argb(rp.text.color))
            seg_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            _apply_fill(seg_cell, cell.fill)

        current_row += 1
    return current_row


def _write_column_header_row(
    ws: Any,
    *,
    header_row: int,
    config: CalendarConfig,
    visible_days: list[date],
    holiday_map: dict[date, dict],
    right_border_cols: dict[int, dict],
    settings: dict,
) -> None:
    """Write the label row, then apply holiday shading / vertical-line borders."""
    header_font = Font(name=settings["font_name"], size=settings["font_size"], bold=True)
    header_align_center = Alignment(horizontal="center", vertical="center")

    ws.row_dimensions[header_row].height = 18

    for col_idx, (label, _) in enumerate(FIXED_COLUMNS, start=1):
        hcell = ws.cell(row=header_row, column=col_idx, value=label)
        hcell.font = header_font
        hcell.alignment = header_align_center

    # X column header — blank but anchored so column dimensions track.
    _x_cell = ws.cell(row=header_row, column=CONTINUATION_COL, value="")
    _x_cell.alignment = header_align_center

    for i, d in enumerate(visible_days):
        col = FIRST_DATE_COL + i
        hcell = ws.cell(row=header_row, column=col)
        hcell.font = Font(name=settings["font_name"], size=settings["font_size"])
        hcell.alignment = header_align_center
        if d in holiday_map:
            _apply_fill(hcell, holiday_map[d]["color"])
        if col in right_border_cols:
            rbs = right_border_cols[col]
            _apply_right_border(hcell, rbs["style"], rbs["color"])


def _prepare_sheet(
    config: CalendarConfig,
    db: CalendarDB,
) -> tuple[Any, Any, int, list[date], dict[date, dict], dict[int, dict], list[Event], dict, Plan]:
    """Build a workbook, write timeband + column-header rows, return shared state.

    Returns (workbook, worksheet, data_start_row, visible_days, holiday_map,
    right_border_cols, all_events_objects, settings, footer_plan).  The footer plan
    holds the secondary timescale rows, which the caller writes after the last
    data row.
    The data_start_row is the first row available for callers to write data
    (one row past the column-header row).  ``all_events_objects`` are the
    Event dataclasses sourced for icon-band evaluation; callers can reuse
    them for downstream rendering.

    No freeze pane is set: the rows are independent records ordered by start
    date, so sort/filter workflows want the whole sheet to scroll.  It must
    never be set and cleared later — clearing ``freeze_panes`` after the
    fact leaves orphaned ``<selection pane>`` elements in the XML and
    corrupts the file.
    """
    visible_days = compute_visible_days(config)
    settings = _read_band_settings(config)
    theme = config.theme_v3

    holiday_map = _build_holiday_map(
        visible_days,
        db,
        config,
        settings["federal_color"],
        settings["company_color"],
        settings["weekend_color"],
    )

    # Always source events — icon rows need them, and so do the data rows.
    # When no events exist this is a cheap call.
    range_start_str = str(config.userstart or config.adjustedstart)
    range_end_str = str(config.userend or config.adjustedend)
    raw_events = db.get_all_events_in_range(range_start_str, range_end_str)
    band_events: list[Event] = [Event.from_dict(e) if isinstance(e, dict) else e for e in raw_events]

    # One unit of span per day column; text always fits a cell and no row is too narrow,
    # since the sheet's column widths are fixed.
    span = Span(visible_days, 0.0, float(len(visible_days))) if visible_days else None
    scale_ctx = ScaleContext(theme, config, db, band_events, measure=lambda *_: 0.0)
    empty = Plan((), (), 0.0)

    def _plan(rows: list) -> Plan:
        if span is None:
            return empty
        return plan_rows(rows, span, scale_ctx, full_days=visible_days, min_segment_width=0.0)

    plan = _plan(theme.timescale.primary)
    footer_plan = _plan(theme.timescale.secondary)
    right_border_cols = _build_right_border_cols(plan)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planner"

    _setup_column_widths(ws, visible_days, config.theme_v3.excelblockplan.column_width or DAY_COL_WIDTH)

    header_row = _write_timebands(
        ws,
        plan=plan,
        holiday_map=holiday_map,
        visible_days=visible_days,
        settings=settings,
        start_row=1,
    )

    _write_column_header_row(
        ws,
        header_row=header_row,
        config=config,
        visible_days=visible_days,
        holiday_map=holiday_map,
        right_border_cols=right_border_cols,
        settings=settings,
    )

    data_start_row = header_row + 1

    return wb, ws, data_start_row, visible_days, holiday_map, right_border_cols, band_events, settings, footer_plan


# Map FIXED_COLUMNS field-name → events-table dict key (as returned by
# ``CalendarDB.get_all_events_in_range``).  Keys missing from a row yield "".
_EVENT_FIELD_MAP: dict[str, str] = {
    "id": "ID",
    "status": "Status",
    "priority": "Priority",
    "wbs": "WBS",
    "rollup": "Rollup",
    "milestone": "Milestone",
    "percent_complete": "Percent_Complete",
    "name": "Task_Name",
    "effort": "Effort",
    "duration": "Duration",
    "start_date": "Start_Date",
    "end_date": "Finish_Date",
    "earliest_start_date": "Earliest_Start_Date",
    "latest_start_date": "Latest_Start_Date",
    "earliest_end_date": "Earliest_End_Date",
    "latest_end_date": "Latest_End_Date",
    "predecessors": "Predecessors",
    "resource_names": "Resource_Names",
    "resource_group": "Resource_Group",
    "notes": "Notes",
    "icon": "Icon",
    "color": "Color",
    "tags": "Tags",
    # Schedule data elements.  "id" above is the events primary key;
    # "source_id" is the identifier from the originating scheduling tool.
    "source_id": "Source_ID",
    "critical": "Critical",
    "start_time": "Start_Time",
    "end_time": "End_Time",
    "duration_text": "Duration_Text",
    "effort_text": "Effort_Text",
    "actual_start_date": "Actual_Start_Date",
    "actual_start_time": "Actual_Start_Time",
    "actual_end_date": "Actual_End_Date",
    "actual_end_time": "Actual_End_Time",
    "deadline": "Deadline",
    "start_variance": "Start_Variance",
    "finish_variance": "Finish_Variance",
    "fixed_cost": "Fixed_Cost",
    "cost": "Cost",
    "percent_work_complete": "Percent_Work_Complete",
    "successors": "Successors",
    "custom1": "Custom1",
    "custom2": "Custom2",
    "custom3": "Custom3",
    "custom4": "Custom4",
    "custom5": "Custom5",
}

#: Fields written as Excel numbers rather than passed through as-is.
_NUMERIC_FIELDS: frozenset[str] = frozenset({"percent_complete", "percent_work_complete", "cost", "fixed_cost"})


def _format_cell_value(field_name: str, raw: Any) -> Any:
    """Coerce a raw events-table value into something readable in Excel.

    Numerics pass through as numbers; bools render as 1/0 so Excel formula
    bars stay friendly; ``None`` → ``""`` so cells appear blank rather than
    "None".  Date strings stay as ``YYYYMMDD`` text on purpose — adding Excel
    date-type coercion is out of scope and would prevent custom formatting on
    rows that mix populated and blank dates.

    Times (``start_time`` and friends) are ``HHMM`` text for the same reason:
    coercing them to Excel time values would turn "0800" into 0.333.
    """
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return 1 if raw else 0
    if field_name in _NUMERIC_FIELDS and isinstance(raw, (int, float)):
        return float(raw)
    return raw


def _event_day_context(event: Event) -> DayContext:
    """Build a DayContext for *event* using only event-known state.

    Day-classification keys (federal_holiday, weekend, etc.) are left at their
    defaults — style rules that key off non-workday context will still
    evaluate, but typically excelblockplan rules drive off event fields
    (resource_group, milestone, priority, …) so this is sufficient.
    """
    return DayContext(date=event.start or "")


def _resolve_event_style(engine: StyleEngine | None, event: Event) -> tuple[str | None, str | None]:
    """Return ``(fill_color, icon_color)`` from style_rules for *event*.

    Falls back to the event's own ``color`` field when no rule supplies a fill.
    """
    fill_color: str | None = event.color or None
    icon_color: str | None = None
    if engine is not None:
        sr = engine.evaluate_event(event, ctx=_event_day_context(event))
        if sr.fill_color:
            fill_color = str(sr.fill_color)
        if sr.icon_color:
            icon_color = str(sr.icon_color)
    if icon_color is None:
        icon_color = fill_color
    return fill_color, icon_color


def _resolve_event_icon(engine: StyleEngine | None, event: Event) -> str:
    """Return the icon glyph/name to draw for *event*.

    Priority: style_rule ``icon`` → events-table ``icon`` → ``"●"``.
    The value is rendered into the Excel cell verbatim — Unicode characters
    work naturally; named icons would need a font that ships with the user's
    Excel install, so we just write the string.
    """
    if engine is not None:
        sr = engine.evaluate_event(event, ctx=_event_day_context(event))
        if sr.icon:
            return str(sr.icon)
    if event.icon:
        return str(event.icon)
    return "●"


def _column_for_day(visible_days: list[date], d: date) -> int | None:
    """Return the 1-based Excel column for *d*, or ``None`` if not visible."""
    idx = bisect_left(visible_days, d)
    if 0 <= idx < len(visible_days) and visible_days[idx] == d:
        return FIRST_DATE_COL + idx
    return None


def _continuation_glyph(*, continues_left: bool, continues_right: bool) -> str:
    if continues_left and continues_right:
        return "◀▶"
    if continues_left:
        return "◀"
    if continues_right:
        return "▶"
    return ""


def _parse_event_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return arrow.get(str(s), "YYYYMMDD").date()
    except Exception:
        return None


def _blockplan_style_rules(config: CalendarConfig) -> list:
    """The theme's conditional style rules, for the StyleEngine."""
    from config import role_styles

    return role_styles.style_rules(config.theme_v3)


def generate_excel_blockplan(
    config: CalendarConfig,
    db: CalendarDB,
    out_path: Path,
) -> None:
    """Generate the Excel workbook for the ``excelblockplan`` subcommand.

    Args:
        config: Fully populated CalendarConfig.
        db:     Open CalendarDB instance.
        out_path: Destination .xlsx path (parent directory must exist).
    """
    visible_days = compute_visible_days(config)
    if not visible_days:
        return

    wb, ws, data_start_row, visible_days, holiday_map, right_border_cols, _all_events, settings, footer_plan = (
        _prepare_sheet(config, db)
    )

    # Filter events / durations using the same predicate the other
    # visualizers use so the data sheet stays consistent with the SVG views.
    raw_dicts = db.get_all_events_in_range(
        str(config.userstart or config.adjustedstart),
        str(config.userend or config.adjustedend),
    )
    filtered_raw = number_duration_icons(filter_events(raw_dicts, config), config, "excelblockplan")
    # Sort the (dict, Event) pairs together so the row index used to look up
    # field values stays aligned with the sort order.
    paired: list[tuple[dict, Event]] = [(d, Event.from_dict(d)) for d in filtered_raw]
    paired.sort(key=lambda p: (p[1].start or "", p[1].task_name or ""))
    filtered = [p[0] for p in paired]
    events = [p[1] for p in paired]

    style_engine = StyleEngine(_blockplan_style_rules(config))

    visible_start = visible_days[0]
    visible_end = visible_days[-1]
    base_font = Font(name=settings["font_name"], size=settings["font_size"])
    center = Alignment(horizontal="center", vertical="center")

    # Track which day-column cells already carry data so we can overlay (not
    # replace) holiday shading at the end.
    data_cell_argb: dict[tuple[int, int], str] = {}

    for row_offset, event in enumerate(events):
        row = data_start_row + row_offset
        ws.row_dimensions[row].height = 14

        # ── Label columns : events-table fields ──────────────────────────
        for col_idx, (field_name, _w) in enumerate(FIXED_COLUMNS, start=1):
            db_key = _EVENT_FIELD_MAP.get(field_name)
            raw = filtered[row_offset].get(db_key) if db_key else None
            value = _format_cell_value(field_name, raw)
            cell = ws.cell(row=row, column=col_idx, value=value)
            cell.font = base_font

        fill_color, icon_color = _resolve_event_style(style_engine, event)
        ev_start = _parse_event_date(event.start)
        ev_end = _parse_event_date(event.end) or ev_start
        if ev_start is None:
            continue

        # Single-day event → icon glyph in the start-date column.
        # Multi-day duration → fill every visible day between start and end.
        if event.is_duration and ev_end and ev_end > ev_start:
            draw_start = max(ev_start, visible_start)
            draw_end = min(ev_end, visible_end)
            if draw_end < visible_start or draw_start > visible_end:
                # Entirely outside the visible range — still record the row
                # but no day-column decoration to apply.
                continues_left = ev_start < visible_start
                continues_right = ev_end > visible_end
                glyph = _continuation_glyph(
                    continues_left=continues_left,
                    continues_right=continues_right,
                )
                if glyph:
                    cont_cell = ws.cell(row=row, column=CONTINUATION_COL, value=glyph)
                    cont_cell.font = Font(
                        name=settings["font_name"],
                        size=settings["font_size"],
                        color=_font_color_argb(icon_color or fill_color),
                    )
                    cont_cell.alignment = center
                continue

            for i, d in enumerate(visible_days):
                if d < draw_start or d > draw_end:
                    continue
                col = FIRST_DATE_COL + i
                cell = ws.cell(row=row, column=col)
                cell.font = base_font
                argb = _to_argb(fill_color) if fill_color else None
                if argb is not None:
                    _apply_fill(cell, fill_color)
                    data_cell_argb[(row, col)] = argb
                if col in right_border_cols:
                    rbs = right_border_cols[col]
                    _apply_right_border(cell, rbs["style"], rbs["color"])

            continues_left = ev_start < visible_start
            continues_right = ev_end > visible_end
            glyph = _continuation_glyph(
                continues_left=continues_left,
                continues_right=continues_right,
            )
            if glyph:
                cont_cell = ws.cell(row=row, column=CONTINUATION_COL, value=glyph)
                cont_cell.font = Font(
                    name=settings["font_name"],
                    size=settings["font_size"],
                    color=_font_color_argb(icon_color or fill_color),
                )
                cont_cell.alignment = center
        else:
            # Single-day event — icon in the start column.
            col = _column_for_day(visible_days, ev_start)
            if col is None:
                continue
            glyph = _resolve_event_icon(style_engine, event)
            cell = ws.cell(row=row, column=col, value=glyph)
            cell.font = Font(
                name=settings["font_name"],
                size=settings["font_size"],
                color=_font_color_argb(icon_color or fill_color),
            )
            cell.alignment = center
            if fill_color:
                _apply_fill(cell, fill_color)
                argb = _to_argb(fill_color)
                if argb is not None:
                    data_cell_argb[(row, col)] = argb
            if col in right_border_cols:
                rbs = right_border_cols[col]
                _apply_right_border(cell, rbs["style"], rbs["color"])

    # ── Holiday / special-day overlay (drawn AFTER data rows) ─────────────
    last_row = data_start_row + len(events) - 1 if events else data_start_row - 1
    if last_row >= data_start_row:
        for row in range(data_start_row, last_row + 1):
            for i, d in enumerate(visible_days):
                if d not in holiday_map:
                    continue
                col = FIRST_DATE_COL + i
                base = data_cell_argb.get((row, col))
                cell = ws.cell(row=row, column=col)
                _apply_overlay_fill(cell, base or "", holiday_map[d]["color"])
                if col in right_border_cols:
                    rbs = right_border_cols[col]
                    _apply_right_border(cell, rbs["style"], rbs["color"])

    # ── Secondary timescale rows, after the last data row ──────────────────
    if footer_plan.rows:
        _write_timebands(
            ws,
            plan=footer_plan,
            holiday_map=holiday_map,
            visible_days=visible_days,
            settings=settings,
            start_row=max(last_row, data_start_row - 1) + 1,
        )

    wb.save(str(out_path))
