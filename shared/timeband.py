"""Shared timeband segment builder used by all visualizers with timebands.

Visualizers (blockplan, compactplan, excelheader, …) all expose a list of
header bands whose unit type drives how segments are generated.  This module
centralizes the segment generation logic so a single timeband definition can
be reused across visualizations.

Supported ``unit`` values:
  - ``fiscal_quarter`` — labelled by ``label_format`` (default ``FY{fy} Q{q}``).
  - ``fiscal_period``  — labelled by the fiscal-period engine.
  - ``month``          — labelled by ``date_format`` (default ``MMM``).
    ``label_format`` is accepted as an alias.
  - ``week``           — labelled by ``label_format`` with placeholders
    ``{n}`` (sequential 1-based), ``{week}`` (ISO week), ``{start}``/``{end}``
    (M/D date strings).
  - ``interval``       — labelled by ``"{prefix}{index}"``.
  - ``date`` / ``dow`` — one segment per visible day; ``date_format``
    (``label_format`` accepted as an alias).
  - ``countdown`` / ``countup`` — per-day count to/from a reference date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import arrow

from shared.fiscal_renderer import (
    _shift_months,
    build_fiscal_period_segments,
    build_fiscal_quarter_segments,
)

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


@dataclass(frozen=True)
class BandSegment:
    """A labeled segment within a time-band column."""

    start: date
    end_exclusive: date
    label: str


def build_segments(
    band: dict[str, Any],
    start: date,
    end: date,
    config: "CalendarConfig",
    *,
    visible_days: list[date] | None = None,
    db: "CalendarDB | None" = None,
    week_start_default: int = 0,
    fiscal_year_start_month_default: int = 2,
) -> list[BandSegment]:
    """Build the labeled segment list for a single time-band definition.

    *week_start_default* and *fiscal_year_start_month_default* let each caller
    fall back to its own visualizer-level config defaults when the band dict
    omits these keys.
    """
    unit = str(band.get("unit", "date")).strip().lower()
    segments: list[BandSegment] = []
    one_day = timedelta(days=1)

    if unit == "fiscal_quarter":
        fiscal_start = int(
            band.get("fiscal_year_start_month", fiscal_year_start_month_default)
        )
        lbl_fmt = str(band.get("label_format", "FY{fy} Q{q}"))
        for seg in build_fiscal_quarter_segments(
            start, end, config,
            fiscal_start_month=fiscal_start,
            label_format=lbl_fmt,
        ):
            segments.append(
                BandSegment(start=seg.start, end_exclusive=seg.end_exclusive, label=seg.label)
            )
        return segments

    if unit == "fiscal_period":
        for seg in build_fiscal_period_segments(start, end, config):
            segments.append(
                BandSegment(start=seg.start, end_exclusive=seg.end_exclusive, label=seg.label)
            )
        return segments

    if unit == "month":
        cursor = date(start.year, start.month, 1)
        fmt = str(band.get("date_format") or band.get("label_format") or "MMM")
        while cursor <= end:
            next_cursor = _shift_months(cursor, 1)
            if next_cursor > start:
                label = arrow.get(cursor).format(fmt)
                segments.append(
                    BandSegment(
                        start=max(cursor, start),
                        end_exclusive=min(next_cursor, end + one_day),
                        label=label,
                    )
                )
            cursor = next_cursor
        return [s for s in segments if s.start < s.end_exclusive]

    if unit == "week":
        week_start = int(band.get("week_start", week_start_default))
        delta = (start.weekday() - week_start) % 7
        cursor = start - timedelta(days=delta)
        seq_n = 1
        while cursor <= end:
            next_cursor = cursor + timedelta(days=7)
            if next_cursor > start:
                iso_week = cursor.isocalendar()[1]
                w_end = next_cursor - one_day
                label = str(band.get("label_format", "Week {week}")).format(
                    n=seq_n,
                    week=iso_week,
                    start=cursor.strftime("%-m/%-d"),
                    end=w_end.strftime("%-m/%-d"),
                )
                segments.append(
                    BandSegment(
                        start=max(cursor, start),
                        end_exclusive=min(next_cursor, end + one_day),
                        label=label,
                    )
                )
                seq_n += 1
            cursor = next_cursor
        return [s for s in segments if s.start < s.end_exclusive]

    if unit == "interval":
        interval_days = max(1, int(band.get("interval_days", 14)))
        prefix = str(band.get("prefix", ""))
        start_index = int(band.get("start_index", 1))
        max_index_raw = band.get("max_index")
        max_index = int(max_index_raw) if max_index_raw is not None else None
        anchor_str = band.get("anchor_date") or band.get("anchor")
        if anchor_str:
            anchor = date.fromisoformat(str(anchor_str))
            delta_days = (start - anchor).days
            if delta_days >= 0:
                intervals_elapsed = delta_days // interval_days
            else:
                intervals_elapsed = -((-delta_days - 1) // interval_days + 1)
            cursor = anchor + timedelta(days=intervals_elapsed * interval_days)
            if max_index is not None:
                cycle_len = max_index - start_index + 1
                index = start_index + (intervals_elapsed % cycle_len)
            else:
                index = start_index + intervals_elapsed
        else:
            cursor = start
            index = start_index
        while cursor <= end:
            next_cursor = cursor + timedelta(days=interval_days)
            seg_start = max(cursor, start)
            seg_end = min(next_cursor, end + one_day)
            if seg_start < seg_end:
                segments.append(
                    BandSegment(
                        start=seg_start,
                        end_exclusive=seg_end,
                        label=f"{prefix}{index}".strip(),
                    )
                )
            cursor = next_cursor
            index += 1
            if max_index is not None and index > max_index:
                index = start_index
        return segments

    if unit in {"date", "dow"}:
        fmt = str(
            band.get("date_format")
            or band.get("label_format")
            or ("D" if unit == "date" else "ddd")
        )
        if visible_days is not None:
            iter_days = [d for d in visible_days if start <= d <= end]
        else:
            iter_days = []
            cursor = start
            while cursor <= end:
                iter_days.append(cursor)
                cursor += one_day
        for cursor in iter_days:
            segments.append(
                BandSegment(
                    start=cursor,
                    end_exclusive=cursor + one_day,
                    label=arrow.get(cursor).format(fmt),
                )
            )
        return segments

    if unit in {"countdown", "countup"}:
        if unit == "countdown":
            ref_str = band.get("target_date") or band.get("target")
        else:
            ref_str = band.get("start_date") or band.get("start")
        if not ref_str:
            return []
        ref_date = date.fromisoformat(str(ref_str))
        skip_wk = bool(band.get("skip_weekends", False))
        skip_nwd = bool(band.get("skip_nonworkdays", False))
        label_fmt = str(band.get("label_format", "{n}"))

        nwd_set: set[date] = set()
        if skip_nwd and db is not None:
            span_start = min(start, ref_date)
            span_end = max(end, ref_date)
            d_iter = span_start
            while d_iter <= span_end:
                if db.is_nonworkday(d_iter.strftime("%Y%m%d")):
                    nwd_set.add(d_iter)
                d_iter += timedelta(days=1)

        def _count_days(from_d: date, to_d: date) -> int:
            if from_d == to_d:
                return 0
            sign = 1 if to_d > from_d else -1
            count = 0
            cursor = from_d + timedelta(days=sign)
            while (sign == 1 and cursor <= to_d) or (sign == -1 and cursor >= to_d):
                if not (skip_wk and cursor.weekday() >= 5) and cursor not in nwd_set:
                    count += 1
                cursor += timedelta(days=sign)
            return sign * count

        iter_days = [d for d in (visible_days or []) if start <= d <= end]
        if not iter_days:
            c = start
            while c <= end:
                iter_days.append(c)
                c += timedelta(days=1)

        for d in iter_days:
            if unit == "countdown":
                n = _count_days(d, ref_date)
            else:
                n = _count_days(ref_date, d)
            segments.append(
                BandSegment(
                    start=d,
                    end_exclusive=d + one_day,
                    label=label_fmt.format(n=n),
                )
            )
        return segments

    return [BandSegment(start=start, end_exclusive=end + one_day, label="")]
