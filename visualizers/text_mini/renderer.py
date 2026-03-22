"""
Text-based mini calendar renderer.

Produces a UTF-8 text file with compact monthly calendars and
an optional event list.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import arrow

from shared.date_utils import (
    get_week_number,
    get_months_in_range,
    index_events_by_day as _index_events_by_day,
)
from config.config import weekend_style_starts_sunday

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


@dataclass
class DetailEntry:
    symbol: str
    date_text: str
    text: str


class TextMiniCalendarRenderer:
    """Render the text-mini view to a UTF-8 text file."""

    def render(
        self,
        config: CalendarConfig,
        events: list[dict],
        db: CalendarDB,
    ) -> Path:
        content = self._build_text(config, events, db)
        out_path = Path(config.outputfile)
        out_path.write_text(content, encoding="utf-8")
        return out_path

    # ---------------------------------------------------------------------
    # Text generation
    # ---------------------------------------------------------------------

    def _build_text(
        self,
        config: CalendarConfig,
        events: list[dict],
        db: CalendarDB,
    ) -> str:
        week_start_sunday = config.mini_week_start == 0 or (
            config.mini_week_start == -1
            and weekend_style_starts_sunday(config.weekend_style)
        )
        cal = calendar.Calendar(firstweekday=6 if week_start_sunday else 0)

        months = get_months_in_range(config.adjustedstart, config.adjustedend)
        cols = config.mini_columns
        rows = (
            config.mini_rows
            if config.mini_rows > 0
            else (len(months) + cols - 1) // cols
        )

        effective_events = events if config.includeevents else []
        events_by_day = self._index_events_by_day(effective_events)
        symbol_map, detail_entries = self._build_symbol_map(
            config, effective_events, events_by_day, db
        )

        lines: list[str] = []
        for row_idx in range(rows):
            row_months = months[row_idx * cols : (row_idx + 1) * cols]
            if not row_months:
                break
            lines.extend(
                self._render_month_row(
                    config,
                    cal,
                    row_months,
                    events_by_day,
                    symbol_map,
                    week_start_sunday,
                )
            )
            lines.append("")

        if detail_entries:
            lines.extend(self._render_details(detail_entries))

        return "\n".join(lines).rstrip() + "\n"

    def _render_month_row(
        self,
        config: CalendarConfig,
        cal: calendar.Calendar,
        months: list[tuple[int, int]],
        events_by_day: dict[str, list[dict]],
        symbol_map: dict[str, str],
        week_start_sunday: bool,
    ) -> list[str]:
        cell_w = max(1, config.text_mini_cell_width)
        gap = " " * max(1, config.text_mini_month_gap)

        month_blocks: list[list[str]] = []
        max_rows = 0
        for year, month in months:
            block = self._render_single_month(
                config, cal, year, month, events_by_day, symbol_map, week_start_sunday
            )
            max_rows = max(max_rows, len(block))
            month_blocks.append(block)

        for block in month_blocks:
            while len(block) < max_rows:
                block.append(" " * len(block[0]))

        merged: list[str] = []
        for r in range(max_rows):
            merged.append(gap.join(block[r] for block in month_blocks))
        return merged

    def _render_single_month(
        self,
        config: CalendarConfig,
        cal: calendar.Calendar,
        year: int,
        month: int,
        events_by_day: dict[str, list[dict]],
        symbol_map: dict[str, str],
        week_start_sunday: bool,
    ) -> list[str]:
        cell_w = max(1, config.text_mini_cell_width)
        sep = " "

        month_name = arrow.Arrow(year, month, 1).format("MMMM")
        month_title = self._center_text(month_name, self._month_line_width(config))

        day_labels = (
            ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
            if week_start_sunday
            else ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        )
        header = sep.join(label.rjust(cell_w) for label in day_labels)
        if config.mini_show_week_numbers:
            week_w = len(self._format_week_number(1, config))
            header = (" " * week_w) + " " + header

        lines = [month_title, header]

        month_dates = cal.monthdatescalendar(year, month)
        for week in month_dates:
            row_cells = []
            for d in week:
                key = d.strftime("%Y%m%d")
                if d.month != month and not config.mini_show_adjacent:
                    row_cells.append(" " * cell_w)
                    continue
                symbol = symbol_map.get(key)
                if symbol:
                    row_cells.append(symbol.rjust(cell_w))
                else:
                    row_cells.append(self._format_day_number(d.day, config, cell_w))

            line = sep.join(row_cells)
            if config.mini_show_week_numbers:
                wn_value = get_week_number(
                    d=week[0],
                    mode=config.mini_week_number_mode,
                    anchor=self._week_anchor(config),
                )
                line = self._format_week_number(wn_value, config) + " " + line
            lines.append(line)

        return lines

    # ------------------------------------------------------------------
    # Symbols and details
    # ------------------------------------------------------------------

    def _build_symbol_map(
        self,
        config: CalendarConfig,
        events: list[dict],
        events_by_day: dict[str, list[dict]],
        db: CalendarDB,
    ) -> tuple[dict[str, str], list[DetailEntry]]:
        symbol_map: dict[str, str] = {}
        details: list[DetailEntry] = []

        # Assign symbols to events
        milestone_symbols = self._cycle(config.text_mini_milestone_symbols)
        event_symbols = self._cycle(config.text_mini_event_symbols)
        duration_symbols = self._cycle(config.text_mini_duration_symbols)

        event_symbol_map: dict[int, str] = {}
        duration_entries: list[tuple[str, str, str]] = []

        for event in events:
            start = (event.get("Start") or "")[:8]
            end = (event.get("End") or event.get("Finish") or "")[:8]
            if not start:
                continue
            is_duration = end and end != start
            if event.get("Milestone"):
                symbol = next(milestone_symbols)
            elif is_duration:
                symbol = next(duration_symbols)
            else:
                symbol = next(event_symbols)
            event_symbol_map[id(event)] = symbol

            if is_duration:
                duration_entries.append((symbol, start, end))
            else:
                date_text = self._format_short_date(start)
                details.append(
                    DetailEntry(symbol, date_text, event.get("Task_Name") or "")
                )

        # Apply event symbols to days
        for daykey, day_events in events_by_day.items():
            for event in day_events:
                symbol = event_symbol_map.get(id(event))
                if not symbol:
                    continue
                if event.get("Milestone"):
                    self._set_symbol(symbol_map, daykey, symbol, 80)
                elif (event.get("End") or event.get("Finish")) and (
                    (event.get("End") or event.get("Finish"))[:8] != event.get("Start")
                ):
                    # duration will be handled separately
                    pass
                else:
                    self._set_symbol(symbol_map, daykey, symbol, 50)

        # Duration markers and details
        for symbol, start, end in duration_entries:
            if start:
                self._set_symbol(symbol_map, start, symbol, 70)
            if end and end != start:
                self._set_symbol(symbol_map, end, symbol, 70)
            if start and end and end != start:
                s = arrow.get(start, "YYYYMMDD")
                e = arrow.get(end, "YYYYMMDD")
                for dt in arrow.Arrow.range("day", s.shift(days=1), e.shift(days=-1)):
                    self._set_symbol(
                        symbol_map,
                        dt.format("YYYYMMDD"),
                        config.text_mini_duration_fill,
                        60,
                    )
            details.append(
                DetailEntry(
                    symbol,
                    f"{self._format_short_date(start)} - {self._format_short_date(end)}",
                    self._duration_name_for(events, start, end),
                )
            )

        # Holidays and special days
        holiday_symbols = self._cycle(config.text_mini_holiday_symbols)
        nonwork_symbols = self._cycle(config.text_mini_nonworkday_symbols)

        for daykey in self._iter_daykeys(config):
            holidays = db.get_holidays_for_date(daykey, config.country)
            if holidays:
                holiday = holidays[0]
                symbol = next(holiday_symbols)
                self._set_symbol(symbol_map, daykey, symbol, 100)
                details.append(
                    DetailEntry(
                        symbol,
                        self._format_short_date(daykey),
                        holiday.get("displayname", "Holiday"),
                    )
                )

            special_days = db.get_special_days_for_date(daykey)
            for sd in special_days:
                if sd.get("nonworkday"):
                    symbol = next(nonwork_symbols)
                    self._set_symbol(symbol_map, daykey, symbol, 90)
                    details.append(
                        DetailEntry(
                            symbol,
                            self._format_short_date(daykey),
                            sd.get("name", "Nonworkday"),
                        )
                    )

        return symbol_map, details

    def _duration_name_for(self, events: list[dict], start: str, end: str) -> str:
        for event in events:
            s = (event.get("Start") or "")[:8]
            e = (event.get("End") or event.get("Finish") or "")[:8]
            if s == start and e == end:
                return event.get("Task_Name") or ""
        return ""

    def _set_symbol(
        self, symbol_map: dict[str, str], daykey: str, symbol: str, priority: int
    ):
        existing = symbol_map.get(daykey)
        if not existing:
            symbol_map[daykey] = symbol
            symbol_map[f"_prio_{daykey}"] = priority  # type: ignore
            return
        prev = symbol_map.get(f"_prio_{daykey}", 0)  # type: ignore
        if priority >= prev:
            symbol_map[daykey] = symbol
            symbol_map[f"_prio_{daykey}"] = priority  # type: ignore

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _index_events_by_day(self, events: list[dict]) -> dict[str, list[dict]]:
        return _index_events_by_day(events)

    def _format_day_number(self, day: int, config: CalendarConfig, width: int) -> str:
        digits = config.text_mini_day_number_digits
        text = "".join(digits[int(d)] for d in str(day))
        return text.rjust(width)

    def _format_week_number(self, wn: int, config: CalendarConfig) -> str:
        digits = config.text_mini_week_number_digits
        text = "".join(digits[int(d)] for d in str(max(0, wn)))
        return text.rjust(2)

    def _format_short_date(self, yyyymmdd: str) -> str:
        if not yyyymmdd or len(yyyymmdd) < 8:
            return ""
        y = int(yyyymmdd[:4])
        m = int(yyyymmdd[4:6])
        d = int(yyyymmdd[6:8])
        return f"{m}/{d}"

    def _center_text(self, text: str, width: int) -> str:
        if len(text) >= width:
            return text
        pad = width - len(text)
        left = pad // 2
        right = pad - left
        return (" " * left) + text + (" " * right)

    def _month_line_width(self, config: CalendarConfig) -> int:
        cell_w = max(1, config.text_mini_cell_width)
        base = (cell_w * 7) + 6
        if config.mini_show_week_numbers:
            base += 3
        return base

    def _render_details(self, details: list[DetailEntry]) -> list[str]:
        lines: list[str] = []
        for entry in details:
            lines.append(f"  {entry.symbol} {entry.date_text} {entry.text}".rstrip())
        return lines

    def _iter_daykeys(self, config: CalendarConfig):
        if not config.adjustedstart or not config.adjustedend:
            return []
        s = arrow.get(config.adjustedstart, "YYYYMMDD")
        e = arrow.get(config.adjustedend, "YYYYMMDD")
        return [dt.format("YYYYMMDD") for dt in arrow.Arrow.range("day", s, e)]

    def _week_anchor(self, config: CalendarConfig):
        if config.mini_week_number_mode != "custom" or not config.mini_week1_start:
            return None
        try:
            return arrow.get(config.mini_week1_start, "YYYYMMDD").date()
        except Exception:
            return None

    def _cycle(self, items: list[str]):
        idx = 0
        while True:
            if not items:
                yield ""
            else:
                yield items[idx % len(items)]
                idx += 1
