"""Excel workbook generator — timeband header.

Produces an .xlsx file whose top rows contain merged-cell timeband segments
(driven by ``excelheader_top_time_bands`` config), followed by a fixed
column-header row and 100 empty data rows.

Layout
------
Columns A-E  : fixed project-tracking labels (Activity, Effort, Duration,
               Scheduled Start, Scheduled End)
Columns F+   : one column per visible calendar day (width = 3 chars)
Rows 1..N    : one row per band in excelheader_top_time_bands
Row  N+1     : column header row ("Activity" … date columns)
Rows N+2..   : 100 empty data rows (holiday shading + vertical-line borders)

Freeze panes are set at F / header-row so the label columns and timeband
rows stay visible while scrolling.
"""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import arrow
from PIL import ImageColor
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from shared.data_models import Event
from shared.icon_band import compute_icon_band_days
from visualizers.blockplan.renderer import BlockPlanRenderer, _BandSegment

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

# ── Constants ─────────────────────────────────────────────────────────────────

FIXED_COLUMNS: list[tuple[str, float]] = [
    ("Activity", 20),
    ("Effort", 8),
    ("Duration", 10),
    ("Scheduled Start", 16),
    ("Scheduled End", 16),
]
DATA_ROWS = 100
DAY_COL_WIDTH = 3.0  # Excel character-width units
FIRST_DATE_COL = len(FIXED_COLUMNS) + 1  # Column F = 6

# ISO 3166-1 alpha-2 → flag emoji
_COUNTRY_FLAGS: dict[str, str] = {
    "ad": "🇦🇩", "ae": "🇦🇪", "af": "🇦🇫", "ag": "🇦🇬", "ai": "🇦🇮",
    "al": "🇦🇱", "am": "🇦🇲", "ao": "🇦🇴", "ar": "🇦🇷", "as": "🇦🇸",
    "at": "🇦🇹", "au": "🇦🇺", "aw": "🇦🇼", "az": "🇦🇿", "ba": "🇧🇦",
    "bb": "🇧🇧", "bd": "🇧🇩", "be": "🇧🇪", "bf": "🇧🇫", "bg": "🇧🇬",
    "bh": "🇧🇭", "bi": "🇧🇮", "bj": "🇧🇯", "bl": "🇧🇱", "bm": "🇧🇲",
    "bn": "🇧🇳", "bo": "🇧🇴", "br": "🇧🇷", "bs": "🇧🇸", "bt": "🇧🇹",
    "bw": "🇧🇼", "by": "🇧🇾", "bz": "🇧🇿", "ca": "🇨🇦", "cc": "🇨🇨",
    "cd": "🇨🇩", "cf": "🇨🇫", "cg": "🇨🇬", "ch": "🇨🇭", "ci": "🇨🇮",
    "ck": "🇨🇰", "cl": "🇨🇱", "cm": "🇨🇲", "cn": "🇨🇳", "co": "🇨🇴",
    "cr": "🇨🇷", "cu": "🇨🇺", "cv": "🇨🇻", "cy": "🇨🇾", "cz": "🇨🇿",
    "de": "🇩🇪", "dj": "🇩🇯", "dk": "🇩🇰", "dm": "🇩🇲", "do": "🇩🇴",
    "dz": "🇩🇿", "ec": "🇪🇨", "ee": "🇪🇪", "eg": "🇪🇬", "es": "🇪🇸",
    "et": "🇪🇹", "fi": "🇫🇮", "fj": "🇫🇯", "fr": "🇫🇷", "ga": "🇬🇦",
    "gb": "🇬🇧", "gd": "🇬🇩", "ge": "🇬🇪", "gh": "🇬🇭", "gm": "🇬🇲",
    "gn": "🇬🇳", "gq": "🇬🇶", "gr": "🇬🇷", "gt": "🇬🇹", "gu": "🇬🇺",
    "gw": "🇬🇼", "gy": "🇬🇾", "hk": "🇭🇰", "hn": "🇭🇳", "hr": "🇭🇷",
    "ht": "🇭🇹", "hu": "🇭🇺", "id": "🇮🇩", "ie": "🇮🇪", "il": "🇮🇱",
    "in": "🇮🇳", "iq": "🇮🇶", "ir": "🇮🇷", "is": "🇮🇸", "it": "🇮🇹",
    "jm": "🇯🇲", "jo": "🇯🇴", "jp": "🇯🇵", "ke": "🇰🇪", "kg": "🇰🇬",
    "kh": "🇰🇭", "ki": "🇰🇮", "km": "🇰🇲", "kn": "🇰🇳", "kp": "🇰🇵",
    "kr": "🇰🇷", "kw": "🇰🇼", "ky": "🇰🇾", "kz": "🇰🇿", "la": "🇱🇦",
    "lb": "🇱🇧", "lc": "🇱🇨", "li": "🇱🇮", "lk": "🇱🇰", "lr": "🇱🇷",
    "ls": "🇱🇸", "lt": "🇱🇹", "lu": "🇱🇺", "lv": "🇱🇻", "ly": "🇱🇾",
    "ma": "🇲🇦", "mc": "🇲🇨", "md": "🇲🇩", "me": "🇲🇪", "mg": "🇲🇬",
    "mh": "🇲🇭", "mk": "🇲🇰", "ml": "🇲🇱", "mm": "🇲🇲", "mn": "🇲🇳",
    "mo": "🇲🇴", "mp": "🇲🇵", "mr": "🇲🇷", "ms": "🇲🇸", "mt": "🇲🇹",
    "mu": "🇲🇺", "mv": "🇲🇻", "mw": "🇲🇼", "mx": "🇲🇽", "my": "🇲🇾",
    "mz": "🇲🇿", "na": "🇳🇦", "ne": "🇳🇪", "ng": "🇳🇬", "ni": "🇳🇮",
    "nl": "🇳🇱", "no": "🇳🇴", "np": "🇳🇵", "nr": "🇳🇷", "nu": "🇳🇺",
    "nz": "🇳🇿", "om": "🇴🇲", "pa": "🇵🇦", "pe": "🇵🇪", "pf": "🇵🇫",
    "pg": "🇵🇬", "ph": "🇵🇭", "pk": "🇵🇰", "pl": "🇵🇱", "pr": "🇵🇷",
    "ps": "🇵🇸", "pt": "🇵🇹", "pw": "🇵🇼", "py": "🇵🇾", "qa": "🇶🇦",
    "ro": "🇷🇴", "rs": "🇷🇸", "ru": "🇷🇺", "rw": "🇷🇼", "sa": "🇸🇦",
    "sb": "🇸🇧", "sc": "🇸🇨", "sd": "🇸🇩", "se": "🇸🇪", "sg": "🇸🇬",
    "sh": "🇸🇭", "si": "🇸🇮", "sk": "🇸🇰", "sl": "🇸🇱", "sm": "🇸🇲",
    "sn": "🇸🇳", "so": "🇸🇴", "sr": "🇸🇷", "ss": "🇸🇸", "st": "🇸🇹",
    "sv": "🇸🇻", "sy": "🇸🇾", "sz": "🇸🇿", "tc": "🇹🇨", "td": "🇹🇩",
    "tg": "🇹🇬", "th": "🇹🇭", "tj": "🇹🇯", "tk": "🇹🇰", "tl": "🇹🇱",
    "tm": "🇹🇲", "tn": "🇹🇳", "to": "🇹🇴", "tr": "🇹🇷", "tt": "🇹🇹",
    "tv": "🇹🇻", "tz": "🇹🇿", "ua": "🇺🇦", "ug": "🇺🇬", "us": "🇺🇸",
    "uy": "🇺🇾", "uz": "🇺🇿", "va": "🇻🇦", "vc": "🇻🇨", "ve": "🇻🇪",
    "vg": "🇻🇬", "vi": "🇻🇮", "vn": "🇻🇳", "vu": "🇻🇺", "ws": "🇼🇸",
    "ye": "🇾🇪", "za": "🇿🇦", "zm": "🇿🇲", "zw": "🇿🇼",
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

def _group_segments(
    segments: list[_BandSegment], show_every: int
) -> list[list[_BandSegment]]:
    """Partition *segments* into consecutive groups of size *show_every*."""
    n = max(1, show_every)
    groups: list[list[_BandSegment]] = []
    buf: list[_BandSegment] = []
    for seg in segments:
        buf.append(seg)
        if len(buf) >= n:
            groups.append(buf)
            buf = []
    if buf:
        groups.append(buf)
    return groups


def _col_for_day(
    day: date, visible_days: list[date], *, end: bool = False
) -> int:
    """Return the 1-based Excel column index for *day*.

    When ``end=True`` the column corresponds to the *end_exclusive* boundary
    (i.e. the last column of a segment, inclusive).
    """
    idx = bisect_left(visible_days, day)
    if end:
        idx -= 1
    return FIRST_DATE_COL + max(0, idx)


# ── Holiday pre-fetch ─────────────────────────────────────────────────────────

def _build_holiday_map(
    visible_days: list[date],
    db: "CalendarDB",
    country: str | None,
    federal_color: str,
    company_color: str,
) -> dict[date, dict]:
    """Return a dict mapping each holiday/nonworkday date to display info."""
    hmap: dict[date, dict] = {}
    for d in visible_days:
        daykey = d.strftime("%Y%m%d")
        # Government / federal holidays (nonworkday=1 only)
        gov = [
            h for h in db.get_holidays_for_date(daykey, country)
            if h.get("nonworkday")
        ]
        if gov:
            icon_key = str(gov[0].get("icon") or "").lower()
            emoji = _COUNTRY_FLAGS.get(icon_key, "🏛")
            hmap[d] = {
                "color": federal_color,
                "emoji": emoji,
                "name": str(gov[0].get("displayname") or ""),
                "is_nonwork": True,
            }
            continue
        # Company / special days (nonworkday=1 only)
        special = [
            s for s in db.get_special_days_for_date(daykey)
            if s.get("nonworkday")
        ]
        if special:
            day_color = str(special[0].get("daycolor") or "").strip() or company_color
            icon_key = str(special[0].get("icon") or "").lower()
            emoji = _COUNTRY_FLAGS.get(icon_key, "🏢")
            hmap[d] = {
                "color": day_color,
                "emoji": emoji,
                "name": str(special[0].get("name") or ""),
                "is_nonwork": True,
            }
    return hmap


# ── Vertical-line → right-border mapping ─────────────────────────────────────

def _build_right_border_cols(
    vertical_lines: list[dict],
    band_segments: dict[str, list[_BandSegment]],
    visible_days: list[date],
    config: "CalendarConfig",
) -> dict[int, dict]:
    """Return {excel_col: {color, style}} for each configured vertical line."""
    result: dict[int, dict] = {}
    for line in vertical_lines:
        if not isinstance(line, dict):
            continue
        band_name = str(line.get("band") or line.get("band_label") or "").strip().lower()
        value = str(line.get("value") or "").strip()
        repeat = bool(line.get("repeat", False))
        align = str(line.get("align", "end")).strip().lower()
        line_color = str(
            line.get("color")
            or getattr(config, "excelheader_vertical_line_color", "red")
            or "red"
        )
        line_width = float(
            line.get("width")
            or getattr(config, "excelheader_vertical_line_width", 1.5)
            or 1.5
        )
        if not band_name:
            continue
        segs = band_segments.get(band_name, [])
        for seg in segs:
            if not repeat and seg.label != value:
                continue
            if align == "end":
                idx = bisect_left(visible_days, seg.end_exclusive) - 1
            elif align == "center":
                s_idx = bisect_left(visible_days, seg.start)
                e_idx = bisect_left(visible_days, seg.end_exclusive)
                idx = (s_idx + e_idx) // 2
            else:  # "start"
                idx = bisect_left(visible_days, seg.start)
            if 0 <= idx < len(visible_days):
                excel_col = FIRST_DATE_COL + idx
                result[excel_col] = {
                    "color": line_color,
                    "style": "medium" if line_width > 1.5 else "thin",
                }
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


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_excel_header(
    config: "CalendarConfig",
    db: "CalendarDB",
    out_path: Path,
) -> None:
    """Generate an Excel workbook with timeband header rows.

    Args:
        config: Fully populated CalendarConfig (date range + theme already applied).
        db:     Open CalendarDB instance.
        out_path: Destination .xlsx path (parent directory must exist).
    """
    # ── Date range & visible days ─────────────────────────────────────────────
    range_start = str(config.userstart or config.adjustedstart)
    range_end = str(config.userend or config.adjustedend)
    start = arrow.get(range_start, "YYYYMMDD").date()
    end = arrow.get(range_end, "YYYYMMDD").date()
    if end < start:
        start, end = end, start

    weekend_style = int(getattr(config, "weekend_style", 0))
    visible_days: list[date] = []
    cursor = start
    while cursor <= end:
        if weekend_style == 0:
            if cursor.weekday() < 5:
                visible_days.append(cursor)
        else:
            visible_days.append(cursor)
        cursor += timedelta(days=1)

    if not visible_days:
        return

    # ── Configuration ─────────────────────────────────────────────────────────
    top_bands: list[dict] = list(getattr(config, "excelheader_top_time_bands", []) or [])
    vertical_lines: list[dict] = list(getattr(config, "excelheader_vertical_lines", []) or [])
    country: str | None = getattr(config, "country", None)

    font_name: str = str(getattr(config, "excelheader_font_name", None) or "Calibri")
    font_size: int = int(getattr(config, "excelheader_font_size", None) or 9)

    federal_color: str = str(
        getattr(config, "theme_federal_holiday_color", None) or "#FFE4E1"
    )
    company_color: str = str(
        getattr(config, "theme_company_holiday_color", None) or "#FFFACD"
    )

    # ── Pre-fetch holiday info ────────────────────────────────────────────────
    holiday_map = _build_holiday_map(
        visible_days, db, country, federal_color, company_color
    )

    # ── Pre-fetch events for icon bands ───────────────────────────────────────
    has_icon_bands = any(
        str(b.get("unit", "")).strip().lower() == "icon" for b in top_bands
    )
    band_events: list[Event] = []
    if has_icon_bands:
        range_start_str = str(config.userstart or config.adjustedstart)
        range_end_str = str(config.userend or config.adjustedend)
        raw_events = db.get_all_events_in_range(range_start_str, range_end_str)
        band_events = [
            Event.from_dict(e) if isinstance(e, dict) else e for e in raw_events
        ]

    # ── Segment builder (reuse BlockPlanRenderer static helpers) ──────────────
    _renderer = BlockPlanRenderer()
    band_segments: dict[str, list[_BandSegment]] = {}
    for band in top_bands:
        bname = str(band.get("label", "")).strip().lower()
        if bname and str(band.get("unit", "")).strip().lower() != "icon":
            band_segments[bname] = _renderer._build_segments(
                band, start, end, config, visible_days=visible_days, db=db
            )

    # Vertical-line → right-border column mapping
    right_border_cols = _build_right_border_cols(
        vertical_lines, band_segments, visible_days, config
    )

    # ── Build workbook ────────────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planner"

    # Fixed label columns A-E
    for col_idx, (_, width) in enumerate(FIXED_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Date columns F+
    for i in range(len(visible_days)):
        ws.column_dimensions[get_column_letter(FIRST_DATE_COL + i)].width = DAY_COL_WIDTH

    # ── Timeband rows ─────────────────────────────────────────────────────────
    current_row = 1

    for band in top_bands:
        band_font_name: str = str(band.get("excel_font_name") or font_name)
        band_font_size: int = int(band.get("excel_font_size") or font_size)

        # Row height: band row_height (pts) × 0.75 → Excel height units
        row_h_pts = float(
            band.get("row_height")
            or getattr(config, "excelheader_band_row_height", 18)
            or 18
        )
        ws.row_dimensions[current_row].height = max(12.0, row_h_pts * 0.75)

        # ── Heading cell (A:E merged) ─────────────────────────────────────────
        label_text = str(band.get("label", ""))
        heading_fill_color = str(
            band.get("label_fill_color")
            or getattr(config, "excelheader_header_heading_fill_color", None)
            or ""
        )
        heading_label_color = str(
            band.get("label_color")
            or getattr(config, "excelheader_header_label_color", None)
            or "black"
        )
        heading_align_h = str(
            band.get("label_align_h")
            or getattr(config, "excelheader_header_label_align_h", None)
            or "left"
        ).lower()
        excel_h_align = (
            "right" if heading_align_h == "right"
            else "center" if heading_align_h == "center"
            else "left"
        )

        ws.merge_cells(
            start_row=current_row, start_column=1,
            end_row=current_row, end_column=len(FIXED_COLUMNS),
        )
        heading_cell = ws.cell(row=current_row, column=1, value=label_text)
        heading_cell.font = Font(
            name=band_font_name,
            size=band_font_size,
            bold=True,
            color=_font_color_argb(heading_label_color),
        )
        heading_cell.alignment = Alignment(
            horizontal=excel_h_align, vertical="center", wrap_text=False
        )
        _apply_fill(heading_cell, heading_fill_color)

        # ── Segment cells ─────────────────────────────────────────────────────
        # Icon bands — compute per-day icons and render as colored symbols.
        if str(band.get("unit", "")).strip().lower() == "icon":
            icon_rules = list(band.get("icon_rules") or [])
            day_icon_map = compute_icon_band_days(band_events, icon_rules, visible_days)
            icon_fill = str(band.get("fill_color") or "none")
            for i, d in enumerate(visible_days):
                col = FIRST_DATE_COL + i
                icons = day_icon_map.get(d, [])
                # Holiday overlay
                if d in holiday_map:
                    _apply_fill(ws.cell(row=current_row, column=col), holiday_map[d]["color"])
                elif icon_fill and icon_fill.lower() not in {"none", "transparent"}:
                    _apply_fill(ws.cell(row=current_row, column=col), icon_fill)
                if not icons:
                    continue
                # Render first icon as a colored bullet symbol in the cell.
                icon_name, icon_color = icons[0]
                symbol = "\u25cf"  # ● filled circle
                cell = ws.cell(row=current_row, column=col, value=symbol)
                cell.font = Font(
                    name=band_font_name,
                    size=band_font_size,
                    color=_font_color_argb(icon_color),
                )
                cell.alignment = Alignment(horizontal="center", vertical="center")
            current_row += 1
            continue

        segs = band_segments.get(str(band.get("label", "")).strip().lower(), [])

        band_fill_raw = band.get("fill_color", getattr(config, "excelheader_timeband_fill_color", "none"))
        band_palette_raw = band.get("fill_palette", getattr(config, "excelheader_timeband_fill_palette", []))
        color_list = BlockPlanRenderer._resolve_color_list(band_fill_raw, band_palette_raw, db)

        seg_label_color = str(
            band.get("font_color")
            or getattr(config, "excelheader_timeband_label_color", None)
            or "black"
        )
        show_every = max(1, int(band.get("show_every", 1)))
        label_values: list | None = band.get("label_values")
        groups = _group_segments(segs, show_every)

        for gidx, group in enumerate(groups):
            seg_start = group[0].start
            seg_end_excl = group[-1].end_exclusive

            col_s = _col_for_day(seg_start, visible_days)
            col_e = _col_for_day(seg_end_excl, visible_days, end=True)

            # Clamp to valid date range
            col_s = max(FIRST_DATE_COL, min(col_s, FIRST_DATE_COL + len(visible_days) - 1))
            col_e = max(col_s, min(col_e, FIRST_DATE_COL + len(visible_days) - 1))

            # Determine label text
            if label_values and gidx < len(label_values):
                cell_text: str = str(label_values[gidx] or group[0].label)
            else:
                cell_text = group[0].label

            # For single-day segments (date/dow/countdown units): check holiday
            is_single_day = (col_s == col_e)
            cell_fill_color: str | None = color_list[gidx % len(color_list)] if color_list else None
            if is_single_day:
                day_idx = col_s - FIRST_DATE_COL
                if 0 <= day_idx < len(visible_days):
                    d = visible_days[day_idx]
                    if d in holiday_map:
                        cell_fill_color = holiday_map[d]["color"]
                        cell_text = holiday_map[d]["emoji"]

            # Write cell
            if col_e > col_s:
                ws.merge_cells(
                    start_row=current_row, start_column=col_s,
                    end_row=current_row, end_column=col_e,
                )
            seg_cell = ws.cell(row=current_row, column=col_s, value=cell_text)
            seg_cell.font = Font(
                name=band_font_name,
                size=band_font_size,
                color=_font_color_argb(seg_label_color),
            )
            seg_cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
            _apply_fill(seg_cell, cell_fill_color)

        current_row += 1

    # ── Column header row ─────────────────────────────────────────────────────
    header_row = current_row
    header_font = Font(name=font_name, size=font_size, bold=True)
    header_align_center = Alignment(horizontal="center", vertical="center")

    ws.row_dimensions[header_row].height = 18

    for col_idx, (label, _) in enumerate(FIXED_COLUMNS, start=1):
        hcell = ws.cell(row=header_row, column=col_idx, value=label)
        hcell.font = header_font
        hcell.alignment = header_align_center

    for i, d in enumerate(visible_days):
        col = FIRST_DATE_COL + i
        hcell = ws.cell(row=header_row, column=col)
        hcell.font = Font(name=font_name, size=font_size)
        hcell.alignment = header_align_center
        if d in holiday_map:
            _apply_fill(hcell, holiday_map[d]["color"])
        # Apply any right border that falls on this column
        if col in right_border_cols:
            rbs = right_border_cols[col]
            _apply_right_border(hcell, rbs["style"], rbs["color"])

    current_row += 1

    # ── Data rows (100 rows) ──────────────────────────────────────────────────
    data_start = current_row

    for row in range(data_start, data_start + DATA_ROWS):
        ws.row_dimensions[row].height = 14
        # Anchor the row so openpyxl tracks it in max_row even when no
        # holiday or border cells are written.
        ws.cell(row=row, column=1).value = ""
        # Holiday shading on date columns
        for i, d in enumerate(visible_days):
            col = FIRST_DATE_COL + i
            if d in holiday_map:
                dcell = ws.cell(row=row, column=col)
                _apply_fill(dcell, holiday_map[d]["color"])
        # Right borders for vertical lines
        for col, rbs in right_border_cols.items():
            dcell = ws.cell(row=row, column=col)
            _apply_right_border(dcell, rbs["style"], rbs["color"])

    # ── Freeze panes ──────────────────────────────────────────────────────────
    # Freeze everything above the column-header row and left of the date columns
    freeze_cell = f"{get_column_letter(FIRST_DATE_COL)}{header_row}"
    # ws.freeze_panes = freeze_cell

    # ── Save ──────────────────────────────────────────────────────────────────
    wb.save(str(out_path))
