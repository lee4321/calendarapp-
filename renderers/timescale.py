"""The timescale engine: one set of rows, drawn by every view.

A *row* (:class:`config.theme_schema.TimescaleRow`) divides a distance into day
segments and groups them.  This module turns rows plus a :class:`~shared.span.Span`
into a :class:`Plan` of cells, ticks and lines with positions and resolved
styles, and draws a plan onto a renderer.  Planning is pure (no drawing, no
SVG), so what a row will look like can be tested without a renderer.

A table view (blockplan, compactplan, gantt) draws each row as a band of cells.
An axis view (timeline, pit) draws a row that has a ``tick:`` facet as ticks
and labels along the axis, and any other row as cells.  Facets a view does not
use are ignored.

Segments are built over the whole date range (``full_days``) and then clipped
to the page being drawn, so ``every`` grouping and fiscal labels run
continuously across the pages of a long chart.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Literal

import arrow

from config.theme_schema import BoxRole, LineSpec, RowTick, TextRole, Theme, TimescaleRow
from renderers.lines import draw_line, stroke_attrs
from shared.date_utils import format_arrow_date
from shared.holidays import DayStyle, resolve_day_styles
from shared.icon_band import compute_icon_band_days
from shared.orientation import Side
from shared.span import Frame, Span, clip_segments
from shared.timeband import BandSegment, build_segments, group_segments

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.data_models import Event
    from shared.db_access import CalendarDB

Mode = Literal["cells", "axis"]

#: Units whose cells are single days, so the holiday fills apply to them.
_DAY_UNITS = frozenset({"date", "dow", "countdown", "countup", "holiday", "icon"})


# ─── Plan ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextStyle:
    font: str
    size: float
    color: str
    opacity: float = 1.0
    align: str = "middle"
    rotation: float | None = None


@dataclass(frozen=True)
class CellIcon:
    name: str
    color: str | None = None


@dataclass(frozen=True)
class Cell:
    """One drawn cell of a row: ``[a, b]`` along the span."""

    start: date
    end_exclusive: date
    a: float
    b: float
    label: str
    show_label: bool
    fill: str | None = None
    fill_opacity: float = 1.0
    icons: tuple[CellIcon, ...] = ()
    continues_before: bool = False
    continues_after: bool = False


@dataclass(frozen=True)
class Tick:
    """A mark at the start of a segment, and its label."""

    day: date
    along: float
    label: str
    label_along: float
    show_label: bool
    #: False for a segment cut by the page start: it is labelled but has no mark of its own.
    mark: bool = True


@dataclass(frozen=True)
class Mark:
    """An icon (and its date) beside an axis: one holiday on one day."""

    along: float
    icon: str
    label: str


@dataclass(frozen=True)
class RowPlan:
    index: int
    row: TimescaleRow
    #: Distance of the row's near edge from the start of the stack, and its thickness.
    offset: float
    height: float
    kind: Literal["cells", "ticks", "marks"]
    heading: str | None
    text: TextStyle
    border: LineSpec
    cells: tuple[Cell, ...] = ()
    ticks: tuple[Tick, ...] = ()
    #: Holiday marks of a ``marks`` row (axis views).
    marks: tuple[Mark, ...] = ()
    #: Along-span positions where this row's ``vline`` is drawn.
    vlines: tuple[float, ...] = ()
    #: ``(a, b, fill, opacity)`` of each column its ``vfill`` shades.
    vfills: tuple[tuple[float, float, str, float], ...] = ()


@dataclass(frozen=True)
class Plan:
    rows: tuple[RowPlan, ...]
    #: Indexes (into the rows given) of rows dropped because their segments were too narrow.
    dropped: tuple[int, ...]
    #: Thickness of the whole stack.
    height: float


@dataclass
class ScaleContext:
    """What planning needs besides the rows and the span."""

    theme: Theme
    config: CalendarConfig
    db: CalendarDB | None = None
    events: Sequence[Event] = field(default_factory=list)
    #: ``name -> colours``; defaults to the database's palette table.
    palette: Callable[[str], list[str] | None] | None = None
    #: ``(text, font name, size) -> width``; defaults to measuring with the font file.
    measure: Callable[[str, str, float], float] | None = None

    def colors(self, palette: str | list[str] | None) -> list[str]:
        if palette is None:
            return []
        if isinstance(palette, list):
            return palette
        lookup = self.palette or (self.db.get_palette if self.db is not None else None)
        found = lookup(palette) if lookup else None
        if not found:
            raise ValueError(f"palette '{palette}' not found")
        return found

    def text_width(self, text: str, font: str, size: float) -> float:
        if self.measure is not None:
            return self.measure(text, font, size)
        from config.config import get_font_path
        from renderers.text_utils import string_width

        return string_width(text, get_font_path(font), size)


# ─── Planning ────────────────────────────────────────────────────────────────


def plan_rows(
    rows: Sequence[TimescaleRow],
    span: Span,
    ctx: ScaleContext,
    *,
    mode: Mode = "cells",
    full_days: Sequence[date] | None = None,
    max_height: float | None = None,
    min_segment_width: float | None = None,
) -> Plan:
    """Plan *rows* over *span* (one page), segmenting across *full_days*.

    Rows whose cells are narrower than ``timescale.min_segment_width`` (or
    *min_segment_width*, for a medium whose units are not points) are
    dropped.  When the kept rows are together thicker than *max_height* every
    row is scaled down in proportion; none is dropped for height.
    """
    all_days = list(full_days) if full_days is not None else list(span.days)
    classes = _day_styles(rows, all_days, ctx)
    planned: list[RowPlan] = []
    dropped: list[int] = []
    for i, row in enumerate(rows):
        plan = _plan_row(i, row, span, all_days, ctx, mode, classes)
        if row.unit == "fiscal_period" and not plan.cells and not plan.ticks:
            dropped.append(i)  # no fiscal calendar in play: nothing to show
            continue
        minimum = ctx.theme.timescale.min_segment_width if min_segment_width is None else min_segment_width
        if _too_narrow(plan, minimum):
            dropped.append(i)
        else:
            planned.append(plan)
    return _stack(planned, dropped, max_height)


def _stack(planned: list[RowPlan], dropped: list[int], max_height: float | None) -> Plan:
    total = sum(p.height for p in planned)
    scale = max_height / total if max_height is not None and total > max_height > 0 else 1.0
    out: list[RowPlan] = []
    offset = 0.0
    for p in planned:
        h = p.height * scale
        out.append(replace(p, offset=offset, height=h))
        offset += h
    return Plan(tuple(out), tuple(dropped), offset)


def _too_narrow(plan: RowPlan, minimum: float) -> bool:
    if minimum <= 0 or plan.kind == "marks":
        return False
    if plan.kind == "ticks":
        widths = [b.along - a.along for a, b in zip(plan.ticks, plan.ticks[1:], strict=False)]
    else:
        whole = [c for c in plan.cells if not (c.continues_before or c.continues_after)]
        widths = [c.b - c.a for c in (whole or plan.cells)]
    return bool(widths) and min(widths) < minimum


def _day_styles(rows: Sequence[TimescaleRow], days: list[date], ctx: ScaleContext) -> dict[date, DayStyle]:
    """Holiday treatment of every day, computed once if any row has single-day cells."""
    if not any(r.unit in _DAY_UNITS for r in rows):
        return {}
    observances = any(r.unit == "holiday" and not r.holidays.nonworkdays_only for r in rows)
    return resolve_day_styles(days, ctx.db, ctx.config, ctx.theme.holidays, nonworkdays_only=not observances)


def _plan_row(
    index: int,
    row: TimescaleRow,
    span: Span,
    all_days: list[date],
    ctx: ScaleContext,
    mode: Mode,
    day_styles: dict[date, DayStyle],
) -> RowPlan:
    theme = ctx.theme
    text = row_text_style(row, theme)
    border = row.border or band_border(theme)
    groups = _groups(row, all_days, ctx)
    cells = _cells(row, groups, span, ctx, text, day_styles, all_days)
    if mode == "axis" and row.unit == "holiday":
        return RowPlan(
            index=index,
            row=row,
            offset=0.0,
            height=_marks_extent(theme),
            kind="marks",
            heading=row.label,
            text=text,
            border=border,
            marks=_marks(span, day_styles, theme),
        )
    use_ticks = mode == "axis" and row.tick is not None
    ticks: tuple[Tick, ...] = ()
    if use_ticks and row.tick is not None:
        ticks = _ticks(row.tick, cells, span)
    vlines = tuple(c.a for c in cells if row.vline is not None and not c.continues_before)
    vfills = _vfills(row, cells, ctx)
    return RowPlan(
        index=index,
        row=row,
        offset=0.0,
        height=row.height,
        kind="ticks" if use_ticks else "cells",
        heading=row.label,
        text=text,
        border=border,
        cells=() if use_ticks else tuple(cells),
        ticks=ticks,
        vlines=vlines,
        vfills=vfills,
    )


def _marks_extent(theme: Theme) -> float:
    """Thickness a holiday-marks row claims beside an axis: the gap, the icon, and two rows of dates."""
    h = theme.holidays
    if not h.show_icons:
        return 0.0
    extent = h.icon_y_offset + h.icon_size
    if h.show_dates:
        date_size = h.date_font_size or max(6.0, h.icon_size * 0.68)
        # Two rows are the most the date placement uses; the last row's descenders hang below its baseline.
        extent += date_size * (0.95 + 1.15 + 0.3)
    return extent


def _marks(span: Span, day_styles: dict[date, DayStyle], theme: Theme) -> tuple[Mark, ...]:
    """One mark per day that closes the office and has a flag; the first flag stands for the day."""
    h = theme.holidays
    if not h.show_icons:
        return ()
    out: list[Mark] = []
    for day in span.days:
        style = day_styles.get(day)
        flag = next((m for m in (style.flags if style else ()) if m.nonworkday), None)
        if flag is None:
            continue
        label = format_arrow_date(arrow.get(day), h.date_format) if h.show_dates else ""
        out.append(Mark(span.center(day), flag.icon, label))
    return tuple(out)


def _vfills(row: TimescaleRow, cells: list[Cell], ctx: ScaleContext) -> tuple[tuple[float, float, str, float], ...]:
    spec = row.vfill
    if spec is None:
        return ()
    colors = ctx.colors(spec.fill_palette)
    out: list[tuple[float, float, str, float]] = []
    for i, c in enumerate(cells):
        color = colors[i % len(colors)] if colors else spec.fill
        if color:
            out.append((c.a, c.b, color, spec.fill_opacity))
    return tuple(out)


def row_text_style(row: TimescaleRow, theme: Theme, base_role: TextRole | None = None) -> TextStyle:
    """The row's text: its own ``text`` over *base_role* (default ``text.band_label``)."""
    base = base_role or theme.text.band_label
    t = row.text
    return TextStyle(
        font=t.font or base.font or theme.fonts.family,
        size=t.size if t.size is not None else base.size,
        color=t.color or base.color,
        opacity=t.opacity if t.opacity is not None else base.opacity,
        align=t.align or base.align or "middle",
        rotation=t.rotation,
    )


def band_border(theme: Theme) -> LineSpec:
    box = theme.boxes.band
    return LineSpec(
        color=box.stroke,
        width=box.stroke_width,
        opacity=box.stroke_opacity,
        dasharray=box.stroke_dasharray,
        linecap="butt",
    )


# ─── Segments to cells ───────────────────────────────────────────────────────


def _band_dict(row: TimescaleRow) -> dict[str, Any]:
    """*row* in the key vocabulary of :mod:`shared.timeband`.

    The segment builder predates the schema and reads dictionaries; this is the
    only place the two meet.  It goes when ``shared.timeband`` takes rows.
    """
    band: dict[str, Any] = {"unit": row.unit, "show_every": row.every}
    if row.format is not None:
        key = "date_format" if row.unit in {"date", "dow", "month", "year"} else "label_format"
        band[key] = row.format
    if row.week_start is not None:
        band["week_start"] = row.week_start
    if row.fiscal_year_start_month is not None:
        band["fiscal_year_start_month"] = row.fiscal_year_start_month
    if row.unit == "interval":
        band.update(
            interval_days=row.interval_days, prefix=row.prefix, start_index=row.start_index, max_index=row.max_index
        )
        if row.anchor_date:
            band["anchor_date"] = row.anchor_date
    if row.unit in {"countdown", "countup"}:
        band["target_date" if row.unit == "countdown" else "start_date"] = row.reference_date
        band.update(skip_weekends=row.skip_weekends, skip_nonworkdays=row.skip_nonworkdays)
    return band


def _groups(row: TimescaleRow, days: list[date], ctx: ScaleContext) -> list[list[BandSegment]]:
    if not days:
        return []
    fiscal = ctx.theme.fiscal
    if row.unit in {"holiday", "icon"}:
        segments = [BandSegment(d, d + timedelta(days=1), "") for d in days]
        return group_segments(segments, _band_dict(row) | {"unit": "date"}, week_start_default=fiscal.week_start)
    band = _band_dict(row)
    segments = build_segments(
        band,
        days[0],
        days[-1],
        ctx.config,
        visible_days=days,
        db=ctx.db,
        week_start_default=fiscal.week_start,
        fiscal_year_start_month_default=fiscal.year_start_month,
    )
    return group_segments(segments, band, week_start_default=fiscal.week_start)


def _cells(
    row: TimescaleRow,
    groups: list[list[BandSegment]],
    span: Span,
    ctx: ScaleContext,
    text: TextStyle,
    day_styles: dict[date, DayStyle],
    all_days: list[date],
) -> list[Cell]:
    box = ctx.theme.boxes.band
    colors = ctx.colors(row.fill_palette if row.fill_palette is not None else box.fill_palette)
    flat_fill = row.fill if row.fill is not None else (box.fill if box.fill not in ("none", "") else None)
    opacity = row.fill_opacity if row.fill_opacity is not None else box.fill_opacity
    icons_by_day = _icon_rule_days(row, all_days, ctx)

    whole = [
        (
            g[0].start,
            g[-1].end_exclusive,
            row.label_values[i % len(row.label_values)] if row.label_values else g[0].label,
        )
        for i, g in enumerate(groups)
    ]
    out: list[Cell] = []
    for piece in clip_segments(whole, span.days):
        extent = span.extent(piece.start, piece.end_exclusive)
        if extent is None:
            continue
        a, b = extent
        i = _origin_index(piece.start, whole)
        fill, fill_opacity = (colors[i % len(colors)], opacity) if colors else (flat_fill, opacity)
        icons: tuple[CellIcon, ...] = ()
        single_day = row.unit in _DAY_UNITS and (piece.end_exclusive - piece.start).days >= 1
        if single_day:
            style = day_styles.get(piece.start)
            if style is not None:
                if style.is_nonworkday and style.fill is not None:
                    fill, fill_opacity = style.fill, style.fill_opacity
                icons = _holiday_icons(row, style, ctx)
            icons += tuple(CellIcon(n, c) for n, c in icons_by_day.get(piece.start, ()))
        label = piece.label if row.unit not in {"holiday", "icon"} else ""
        # A label wider than its cell is compressed when drawn, never dropped; rows too narrow to read go via min_segment_width.
        fits = bool(label)
        out.append(
            Cell(
                piece.start,
                piece.end_exclusive,
                a,
                b,
                label,
                fits,
                fill,
                fill_opacity,
                icons,
                piece.continues_before,
                piece.continues_after,
            )
        )
    return out


def _origin_index(day: date, whole: list[tuple[date, date, str]]) -> int:
    """Index of the full-range cell holding *day*, so colours cycle continuously across pages."""
    return next((i for i, (s, e, _) in enumerate(whole) if s <= day < e), 0)


def _holiday_icons(row: TimescaleRow, style: DayStyle, ctx: ScaleContext) -> tuple[CellIcon, ...]:
    """Icons a nonworking day carries: its country flags, else the theme's static icon.

    ``unit: holiday`` rows show the flags.  Other single-day rows show an icon
    only where the theme asks for one: the flags when ``holidays.federal.icon``
    is set, otherwise the static icon of the day's class.
    """
    if not ctx.theme.holidays.show_icons:
        return ()
    flags = [m for m in style.flags if m.nonworkday or (row.unit == "holiday" and not row.holidays.nonworkdays_only)]
    if row.unit == "holiday" or (flags and ctx.theme.holidays.federal.icon):
        return tuple(CellIcon(m.icon) for m in flags)
    return (CellIcon(style.icon),) if style.icon else ()


def _icon_rule_days(row: TimescaleRow, days: list[date], ctx: ScaleContext) -> dict[date, list[tuple[str, str]]]:
    if row.unit != "icon" or not row.icon_rules:
        return {}
    from shared.day_classifier import classify_day

    return compute_icon_band_days(
        list(ctx.events),
        row.icon_rules,
        days,
        classify_fn=lambda d: classify_day(d, ctx.db, ctx.config),
    )


# ─── Ticks ───────────────────────────────────────────────────────────────────


def _ticks(tick: RowTick, cells: list[Cell], span: Span) -> tuple[Tick, ...]:
    """A tick at the start of every whole segment; a label for every segment."""
    show = tick.show_labels and not (tick.max_label_count is not None and len(cells) > tick.max_label_count)
    out: list[Tick] = []
    for c in cells:
        anchor = {"start": c.a, "middle": (c.a + c.b) / 2, "end": c.b}[tick.label_align]
        out.append(
            Tick(c.start, c.a, c.label, max(anchor, span.along0), show and bool(c.label), not c.continues_before)
        )
    return tuple(out)


# ─── Drawing ─────────────────────────────────────────────────────────────────


def draw_cells(renderer: Any, plan: Plan, frame: Frame, cross0: float, sign: float = 1.0) -> None:
    """Draw every cell row of *plan*, stacked from *cross0* in the *sign* direction across the span."""
    for rp in plan.rows:
        if rp.kind != "cells":
            continue
        lo = cross0 + (rp.offset if sign > 0 else -(rp.offset + rp.height))
        for cell in rp.cells:
            x, y, w, h = frame.rect(cell.a, cell.b - cell.a, lo, rp.height)
            renderer._draw_rect(
                x,
                y,
                w,
                h,
                fill=cell.fill or "none",
                fill_opacity=cell.fill_opacity,
                **stroke_attrs(rp.border),
                css_class="ec-band-cell",
            )
            if cell.icons and not frame.vertical:
                renderer._draw_cell_icons(
                    [(i.name, i.color) for i in cell.icons],
                    cell.a,
                    cell.b - cell.a,
                    lo,
                    rp.height,
                    rp.height * 0.65,
                    css_class="ec-holiday-icon" if rp.row.unit == "holiday" else "ec-nwd-icon",
                )
            elif cell.show_label:
                _draw_label(
                    renderer,
                    frame,
                    rp.text,
                    cell.label,
                    (cell.a + cell.b) / 2,
                    lo + rp.height / 2,
                    max_width=_label_room(frame, rp.text, cell.b - cell.a, rp.height),
                )


def draw_headings(
    renderer: Any,
    plan: Plan,
    x: float,
    width: float,
    cross0: float,
    align: str = "end",
    box: BoxRole | None = None,
    pad: float = 6.0,
) -> None:
    """Row headings in a label column ``[x, x + width]`` beside a horizontal stack growing downward from *cross0*.

    With a *box* (the theme's ``boxes.header``) each heading also gets a cell
    behind it, bordered like the row's own cells.
    """
    from config.config import get_font_path
    from renderers.text_utils import text_center_baseline

    anchor = align if align in ("start", "middle", "end") else "end"
    ax = {"start": x + pad, "middle": x + width / 2, "end": x + width - pad}[anchor]
    for rp in plan.rows:
        y = cross0 + rp.offset
        if box is not None:
            renderer._draw_rect(
                x,
                y,
                width,
                rp.height,
                fill=box.fill,
                fill_opacity=box.fill_opacity,
                **stroke_attrs(rp.border),
                css_class="ec-heading-cell",
            )
        if not rp.heading:
            continue
        baseline = text_center_baseline(y + rp.height / 2, get_font_path(rp.text.font), rp.text.size)
        renderer._draw_text(
            ax,
            baseline,
            rp.heading,
            rp.text.font,
            rp.text.size,
            fill=rp.text.color,
            fill_opacity=rp.text.opacity,
            anchor=anchor,
            max_width=max(8.0, width - 2 * pad),
            css_class="ec-heading",
        )


def draw_ticks(renderer: Any, plan: Plan, frame: Frame, lines: Any, sign: float) -> None:
    """Draw tick rows away from the axis in the *sign* direction.

    Each row's ticks start at the axis line (``frame.cross``) and run
    ``row.tick.length`` outward; its labels sit past the tick end, after
    ``label_gap``.  *lines* is the theme's :class:`LineRoles`.
    """
    for rp in plan.rows:
        if rp.kind != "ticks" or rp.row.tick is None:
            continue
        tick = rp.row.tick
        spec = _tick_line(lines.tick, tick)
        near = frame.cross + sign * rp.offset
        far = near + sign * tick.length
        for t in rp.ticks:
            if t.mark:
                draw_line(renderer, spec, frame.xy(t.along, near), frame.xy(t.along, far), css_class="ec-axis-tick")
        gap = tick.label_gap if tick.label_gap is not None else 2.0
        label_across = far + sign * (gap + rp.text.size / 2)
        for t in rp.ticks:
            if t.show_label:
                _draw_label(renderer, frame, rp.text, t.label, t.label_along, label_across, css_class="ec-tick-label")


def draw_vfills(renderer: Any, plan: Plan, frame: Frame, cross_lo: float, cross_hi: float) -> None:
    """Shade each row's ``vfill`` columns across the content area; draw before the content."""
    for rp in plan.rows:
        for a, b, color, opacity in rp.vfills:
            x, y, w, h = frame.rect(a, b - a, cross_lo, cross_hi - cross_lo)
            renderer._draw_rect(x, y, w, h, fill=color, fill_opacity=opacity, css_class="ec-vline-fill")


def row_segments(
    rows: Sequence[TimescaleRow], days: Sequence[date], ctx: ScaleContext
) -> list[list[tuple[date, date]]]:
    """The cells ``(start, end_exclusive)`` of each row over the whole range, finest row first.

    This is what :func:`shared.span.paginate` needs to keep a page break from
    cutting a segment that fits a page.
    """
    out: list[list[tuple[date, date]]] = []
    for row in rows:
        groups = _groups(row, list(days), ctx)
        out.append([(g[0].start, g[-1].end_exclusive) for g in groups])
    out.sort(key=lambda segs: sum((e - s).days for s, e in segs) / max(1, len(segs)))
    return out


def draw_vlines(renderer: Any, plan: Plan, frame: Frame, cross_lo: float, cross_hi: float) -> None:
    """Draw each row's ``vline`` at its segment boundaries across the content area."""
    for rp in plan.rows:
        if rp.row.vline is None:
            continue
        for along in rp.vlines:
            draw_line(
                renderer, rp.row.vline, frame.xy(along, cross_lo), frame.xy(along, cross_hi), css_class="ec-vline"
            )


def _tick_line(base: LineSpec, tick: RowTick) -> LineSpec:
    changes = {
        k: v for k, v in (("width", tick.width), ("color", tick.color), ("opacity", tick.opacity)) if v is not None
    }
    return replace(base, **changes) if changes else base


def _label_room(frame: Frame, text: TextStyle, along: float, across: float) -> float:
    """Room for a cell's label: its length along the axis when the text runs that way, else across it."""
    rotation = text.rotation if text.rotation is not None else (-90.0 if frame.vertical else 0.0)
    runs_along = (abs(rotation) % 180 == 90) == frame.vertical
    return (along if runs_along else across) - 2.0


def _draw_label(
    renderer: Any,
    frame: Frame,
    text: TextStyle,
    label: str,
    along: float,
    across_center: float,
    *,
    css_class: str = "ec-label",
    max_width: float | None = None,
) -> None:
    from config.config import get_font_path
    from renderers.text_utils import text_center_baseline

    x, y = frame.xy(along, across_center)
    rotation = text.rotation if text.rotation is not None else (-90.0 if frame.vertical else 0.0)
    baseline = text_center_baseline(y, get_font_path(text.font), text.size)
    transform = f"rotate({rotation:g} {x:g} {y:g})" if rotation else None
    renderer._draw_text(
        x,
        baseline,
        label,
        text.font,
        text.size,
        fill=text.color,
        fill_opacity=text.opacity,
        anchor="middle",
        transform=transform,
        max_width=max_width if max_width is None or max_width > 0 else None,
        css_class=css_class,
    )


# ─── Axis views ──────────────────────────────────────────────────────────────


def split_axis_rows(rows: Sequence[TimescaleRow]) -> tuple[list[TimescaleRow], list[TimescaleRow]]:
    """``(beside, edge)``: the rows an axis view draws along the axis, and those it draws as bands at the page edge.

    A row with a ``tick`` facet draws as ticks and labels, and a ``holiday`` row as
    icons with their dates, both beside the axis, nearest row first.  Every other
    row is a band of cells at the outer edge of its side.
    """
    beside = [r for r in rows if r.tick is not None or r.unit == "holiday"]
    edge = [r for r in rows if r.tick is None and r.unit != "holiday"]
    return beside, edge


def draw_beside(renderer: Any, theme: Theme, plan: Plan, frame: Frame, side: Side) -> None:
    """Draw the rows beside the axis on *side*: tick rows, then holiday marks."""
    sign = frame.sign(side)
    draw_ticks(renderer, plan, frame, theme.lines, sign)
    for rp in plan.rows:
        if rp.kind == "marks":
            draw_marks(renderer, theme, rp, frame, sign, frame.cross + sign * rp.offset)


def draw_marks(renderer: Any, theme: Theme, rp: RowPlan, frame: Frame, sign: float, near: float) -> None:
    """Holiday icons just off the axis at *near*, and below each its date, on further rows where dates would touch."""
    h = theme.holidays
    if not rp.marks:
        return
    size = h.icon_size
    gap = h.icon_y_offset
    icon_across = near + sign * (gap + size * 0.5)
    for m in rp.marks:
        _draw_mark_icon(renderer, h, frame, m, icon_across, size)
    if not h.show_dates:
        return
    _draw_mark_dates(renderer, theme, rp, frame, sign, near, size, gap)


def _draw_mark_icon(renderer: Any, h: Any, frame: Frame, m: Mark, icon_across: float, size: float) -> None:
    if frame.vertical:
        x, y = icon_across, renderer._icon_baseline(m.along, size)
    else:
        x, y = m.along, renderer._icon_baseline(icon_across, size)
    renderer._draw_icon_svg(m.icon, x, y, size, anchor="middle", color=h.icon_color, css_class="ec-holiday-icon")


def _assign_date_rows(labels: list[tuple[float, float]], max_rows: int = 2) -> list[int]:
    """Give each date label a row where it clears its neighbours; -1 when it fits on none.

    ``labels`` is ``(centre, width)`` in axis order.  Holidays cluster (Christmas Eve and
    Day), so one row would print dates on top of each other; a date with no room is left
    off, since the icon still marks the day.
    """
    gap = 3.0
    row_right: list[float] = []
    rows: list[int] = []
    for centre, width in labels:
        left = centre - width / 2.0
        for row in range(max_rows):
            if row == len(row_right):
                row_right.append(left + width + gap)
                rows.append(row)
                break
            if left >= row_right[row]:
                row_right[row] = left + width + gap
                rows.append(row)
                break
        else:
            rows.append(-1)
    return rows


def _draw_mark_dates(
    renderer: Any, theme: Theme, rp: RowPlan, frame: Frame, sign: float, near: float, size: float, gap: float
) -> None:
    from config.config import get_font_path
    from renderers.text_utils import string_width

    h = theme.holidays
    role = theme.text.event_date
    font = role.font or theme.fonts.family
    date_size = h.date_font_size or max(6.0, size * 0.68)
    font_path = get_font_path(font)
    color = h.date_color or role.color
    labelled = [m for m in rp.marks if m.label]
    if not labelled:
        return
    if frame.vertical:
        # A date claims its own line height along the axis; rows step away by the widest date.
        rows = _assign_date_rows([(m.along, date_size * 1.2) for m in labelled])
        first = near + sign * (gap + size + 2.0)
        stride = sign * (max(string_width(m.label, font_path, date_size) for m in labelled) + 3.0)
    else:
        rows = _assign_date_rows([(m.along, string_width(m.label, font_path, date_size)) for m in labelled])
        stride = date_size * 1.15
    for m, row in zip(labelled, rows, strict=True):
        if row < 0:
            continue
        if frame.vertical:
            x, y, anchor = first + row * stride, m.along + date_size * 0.35, "start" if sign > 0 else "end"
        elif sign > 0:
            x, y, anchor = m.along, near + gap + size + date_size * 0.95 + row * stride, "middle"
        else:
            x, y, anchor = m.along, near - gap - size - date_size * 0.15 - row * stride, "middle"
        renderer._draw_text(
            x,
            y,
            m.label,
            font,
            date_size,
            fill=color,
            fill_opacity=role.opacity,
            anchor=anchor,
            css_class="ec-holiday-date",
        )


@dataclass(frozen=True)
class AxisScale:
    """What an axis view draws from the timescale: rows beside the axis and bands at the page edges, per side."""

    beside: dict[Side, Plan]
    edge: dict[Side, Plan]

    def beside_height(self, *sides: Side) -> float:
        """The room the rows beside the axis take on the tallest of *sides*."""
        return max((self.beside[s].height for s in sides), default=0.0)

    def edge_low(self, frame: Frame) -> float:
        """Thickness of the edge stack at the low-coordinate end (top / left) of the content area."""
        return self.edge[Side.SECONDARY if frame.vertical else Side.PRIMARY].height

    def edge_high(self, frame: Frame) -> float:
        """Thickness of the edge stack at the high-coordinate end (bottom / right)."""
        return self.edge[Side.PRIMARY if frame.vertical else Side.SECONDARY].height


def plan_axis_scale(theme: Theme, span: Span, ctx: ScaleContext) -> AxisScale:
    """Plan both sides of the theme's timescale for an axis view over *span*."""
    beside: dict[Side, Plan] = {}
    edge: dict[Side, Plan] = {}
    for side, rows in ((Side.PRIMARY, theme.timescale.primary), (Side.SECONDARY, theme.timescale.secondary)):
        beside_rows, edge_rows = split_axis_rows(rows)
        beside[side] = plan_rows(beside_rows, span, ctx, mode="axis")
        edge[side] = plan_rows(edge_rows, span, ctx, mode="axis")
    return AxisScale(beside, edge)


def draw_axis_beside(renderer: Any, theme: Theme, scale: AxisScale, frame: Frame) -> None:
    """Draw the rows beside the axis (ticks, holiday marks) on both sides of it."""
    for side in (Side.PRIMARY, Side.SECONDARY):
        draw_beside(renderer, theme, scale.beside[side], frame, side)


def draw_axis_edges(renderer: Any, scale: AxisScale, frame: Frame, area_lo: float, area_hi: float) -> None:
    """Draw the edge bands within the content area ``[area_lo, area_hi]`` across the axis.

    Each stack reads in increasing coordinate order (top to bottom, left to
    right), starting at its own end of the area.
    """
    low_side = Side.SECONDARY if frame.vertical else Side.PRIMARY
    high_side = Side.PRIMARY if frame.vertical else Side.SECONDARY
    draw_cells(renderer, scale.edge[low_side], frame, area_lo)
    draw_cells(renderer, scale.edge[high_side], frame, area_hi - scale.edge_high(frame))


# ─── Period labels for grid views ────────────────────────────────────────────


@dataclass(frozen=True)
class PeriodLabels:
    """Where a grid view (weekly, mini, text-mini) writes the labels of the timescale's period row."""

    #: Label for the first visible day of each period.
    start: dict[date, str]
    #: Label for the last visible day of each period (only when the row sets ``end_format``).
    end: dict[date, str]
    text: TextStyle


def period_labels(ctx: ScaleContext, days: Sequence[date]) -> PeriodLabels | None:
    """Label the days of a grid view from the theme's first ``fiscal_period`` row.

    The row is the single declaration of what a fiscal period is called and
    how it is styled.  A period that opens on a day the view does not draw
    (an NRF Sunday in a workweek view) is labelled on its first visible day.
    ``None`` when the theme has no such row or no fiscal calendar is in play.
    """
    if not ctx.config.fiscal_lookup or not days:
        return None
    ts = ctx.theme.timescale
    row = next((r for r in (*ts.primary, *ts.secondary) if r.unit == "fiscal_period"), None)
    if row is None:
        return None
    from shared.fiscal_renderer import format_fiscal_period_end_label

    visible = sorted(days)
    start: dict[date, str] = {}
    end: dict[date, str] = {}
    for n, group in enumerate(_groups(row, visible, ctx)):
        lo, hi = group[0].start, group[-1].end_exclusive
        inside = [d for d in visible if lo <= d < hi]
        if not inside:
            continue
        label = row.label_values[n % len(row.label_values)] if row.label_values else group[0].label
        opening = ctx.config.fiscal_lookup.get(lo.strftime("%Y%m%d"))
        if opening is not None and opening.is_period_start:  # a period joined part-way through has no start label
            start[inside[0]] = label
        if row.end_format:
            info = ctx.config.fiscal_lookup.get(inside[-1].strftime("%Y%m%d"))
            if info is not None:
                end[inside[-1]] = format_fiscal_period_end_label(info, ctx.config, row.end_format)
    return PeriodLabels(start, end, row_text_style(row, ctx.theme, ctx.theme.text.fiscal_label))


def grid_period_labels(config: Any) -> PeriodLabels | None:
    """:func:`period_labels` for the days a grid view draws: ``adjustedstart`` to ``adjustedend``
    (the fiscal calendar's own span when those are unset), less hidden weekend days."""
    import arrow

    from shared.date_utils import visible_days

    if not config.fiscal_lookup or not config.fiscal_show_period_labels:
        return None
    try:
        first = arrow.get(config.adjustedstart, "YYYYMMDD").date()
        last = arrow.get(config.adjustedend, "YYYYMMDD").date()
    except arrow.parser.ParserError:
        keys = sorted(config.fiscal_lookup)
        first, last = arrow.get(keys[0], "YYYYMMDD").date(), arrow.get(keys[-1], "YYYYMMDD").date()
    days = visible_days(first, last, int(config.weekend_style))
    return period_labels(ScaleContext(config.theme_v3, config, None, []), days)
