#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database access layer for calendar application.
Provides SQLite access to calendar.db for events, holidays, and special days.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

logger = logging.getLogger(__name__)

# Holiday categories from the 'holidays' package that count as non-working days.
_NONWORK_CATEGORIES: frozenset[str] = frozenset({"public", "government"})
# Additional informational holiday categories (shown as titles, not shaded).
_EXTRA_CATEGORIES: frozenset[str] = frozenset({"optional", "half_day", "unofficial"})
# Countries loaded when no --country flag is given.
_DEFAULT_COUNTRIES: tuple[str, ...] = ("US", "CA")


def _parse_country_codes(country: str | None) -> frozenset[str] | None:
    """Normalise a ``--country`` argument to a frozenset of uppercase 2-letter codes.

    Accepts:
        None              → None  (no filter; callers use _DEFAULT_COUNTRIES or all)
        ``"US"``          → ``frozenset({"US"})``
        ``"US,CA,GB"``    → ``frozenset({"US", "CA", "GB"})``

    Returns ``None`` (not an empty set) when *country* is ``None`` so callers
    can distinguish "user did not specify" from "user specified nothing".
    Whitespace around codes is stripped; empty tokens from trailing commas are
    ignored; all codes are upper-cased.
    """
    if country is None:
        return None
    codes = frozenset(c.strip().upper() for c in country.split(",") if c.strip())
    return codes if codes else None


class CalendarDB:
    """SQLite database access for calendar data."""

    def __init__(self, db_path: str = "calendar.db"):
        self.db_path = db_path
        # In-memory government holidays populated by load_python_holidays().
        self._python_holidays: dict[str, list[dict]] = {}

    def load_python_holidays(
        self, country: str | None, adjustedstart: str, adjustedend: str
    ) -> None:
        """
        Load government holidays from the 'holidays' Python package.

        Loads public, government, optional, half-day, and unofficial holidays
        for every country in scope.  Public and government holidays are marked
        nonworkday=1 (shaded on the calendar); optional/half-day/unofficial
        holidays are marked nonworkday=0 (title shown, no shading).

        When *country* is None the default countries (US and CA) are loaded.

        Args:
            country: One or more ISO 3166-1 alpha-2 country codes.  Accepts a
                     single code ("US"), a comma-separated list ("US,CA,GB"), or
                     None to load the default set (US + CA).
            adjustedstart: Calendar start date in YYYYMMDD format.
            adjustedend:   Calendar end date in YYYYMMDD format.

        Raises:
            ImportError: If the 'holidays' package is not installed.
        """
        self._python_holidays = {}

        import holidays as holidays_lib

        start_year = datetime.strptime(adjustedstart, "%Y%m%d").year
        end_year = datetime.strptime(adjustedend, "%Y%m%d").year
        years = list(range(start_year, end_year + 1))

        # Normalise the country argument: split comma-separated codes and
        # fall back to the default set when nothing is specified.
        codes = _parse_country_codes(country)
        countries = sorted(codes) if codes else list(_DEFAULT_COUNTRIES)
        for ctry in countries:
            self._load_country_holidays(holidays_lib, ctry, years)

        total_dates = len(self._python_holidays)
        year_str = ", ".join(str(y) for y in years)
        logger.info(
            f"Loaded {total_dates} holiday dates for "
            f"{', '.join(countries)} ({year_str})"
        )

    def _load_country_holidays(
        self, holidays_lib, country: str, years: list[int]
    ) -> None:
        """
        Load all supported holiday categories for *country* into _python_holidays.

        Strategy:
        - 'public' and 'government' are treated as a single nonwork pool.
          They are unioned by date: 'public' names take precedence when both
          cover the same day; 'government'-only days (e.g. CA Boxing Day) are
          still included as nonworkday=1.
        - 'optional', 'half_day', 'unofficial' are added as nonworkday=0
          for dates not already covered by the nonwork pool.
        """
        # Probe the country to discover which categories it supports.
        try:
            probe = holidays_lib.country_holidays(country, years=years[:1])
        except (KeyError, NotImplementedError):
            logger.warning(
                f"'holidays' package does not support country '{country}'; skipping"
            )
            return

        supported: set[str] = set(getattr(probe, "supported_categories", {"public"}))

        # --- Step 1: build nonwork pool (public ∪ government), deduped by date ---
        # Load 'public' first so its names take precedence over 'government' names
        # on days covered by both.
        nonwork_dates: dict[str, str] = {}  # daykey → display name
        for cat in ("public", "government"):
            if cat not in supported:
                continue
            try:
                h = holidays_lib.country_holidays(
                    country, years=years, categories=(cat,)
                )
            except Exception as e:
                logger.debug(f"Could not load '{cat}' holidays for {country}: {e}")
                continue
            for dt, name in h.items():
                daykey = dt.strftime("%Y%m%d")
                nonwork_dates.setdefault(daykey, name)  # first writer (public) wins

        country_icon = country.lower()
        for daykey, name in nonwork_dates.items():
            self._python_holidays.setdefault(daykey, []).append(
                {
                    "displayname": name,
                    "icon": country_icon,
                    "nonworkday": 1,
                    "country": country,
                }
            )

        # --- Step 2: add informational (non-nonwork) holidays ---
        for cat in ("optional", "half_day", "unofficial"):
            if cat not in supported:
                continue
            try:
                h = holidays_lib.country_holidays(
                    country, years=years, categories=(cat,)
                )
            except Exception as e:
                logger.debug(f"Could not load '{cat}' holidays for {country}: {e}")
                continue
            for dt, name in h.items():
                daykey = dt.strftime("%Y%m%d")
                # Skip dates already covered as nonwork days.
                if daykey in nonwork_dates:
                    continue
                # Deduplicate by name within this country+date.
                existing_names = {
                    e["displayname"]
                    for e in self._python_holidays.get(daykey, [])
                    if e.get("country") == country
                }
                if name in existing_names:
                    continue
                self._python_holidays.setdefault(daykey, []).append(
                    {
                        "displayname": name,
                        "icon": country_icon,
                        "nonworkday": 0,
                        "country": country,
                    }
                )

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Public context manager for database connections."""
        return self._get_connection()

    def get_events_for_date_range(
        self, start: str, end: str, user_id: int | None = None
    ) -> list[dict]:
        """
        Get events within a date range.

        Args:
            start: Start date in YYYYMMDD format
            end: End date in YYYYMMDD format
            user_id: Optional user ID filter

        Returns:
            List of event dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if user_id is not None:
                cursor.execute(
                    """
                    SELECT * FROM events
                    WHERE start_date >= ? AND start_date <= ?
                    AND user_id = ?
                    ORDER BY priority, name
                    """,
                    (start, end, user_id),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM events
                    WHERE start_date >= ? AND start_date <= ?
                    ORDER BY priority, name
                    """,
                    (start, end),
                )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_holidays_for_date(
        self, daykey: str, country: str | None = None
    ) -> list[dict]:
        """
        Get government holidays for a specific date.

        Args:
            daykey: Date in YYYYMMDD format
            country: Country code filter.  Accepts a single code ("US"), a
                     comma-separated list ("US,CA,GB"), or None to return
                     holidays for all loaded countries.

        Returns:
            List of holiday dictionaries with keys: displayname, icon, nonworkday, country
        """
        codes = _parse_country_codes(country)
        results = self._python_holidays.get(daykey, [])
        if codes is not None:
            results = [h for h in results if h.get("country") in codes]
        return results

    def get_special_days_for_date(self, daykey: str) -> list[dict]:
        """
        Get company special days for a specific date.

        Args:
            daykey: Date in YYYYMMDD format

        Returns:
            List of special day dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Note: The 'marks' column may not exist in all database versions
            # We query available columns and handle missing ones gracefully
            try:
                cursor.execute(
                    """
                    SELECT name, notes, icon, nonworkday, daycolor, pattern, patterncolor, marks
                    FROM companyspecialdays
                    WHERE startdate <= ? AND enddate >= ?
                    AND visible = 1
                    """,
                    (daykey, daykey),
                )
            except Exception:
                try:
                    cursor.execute(
                        """
                        SELECT name, notes, icon, nonworkday, daycolor, pattern, patterncolor
                        FROM companyspecialdays
                        WHERE startdate <= ? AND enddate >= ?
                        AND visible = 1
                        """,
                        (daykey, daykey),
                    )
                except Exception:
                    return []
            rows = cursor.fetchall()
            results = []
            for row in rows:
                d = dict(row)
                # Add marks field with empty string if not present
                d["marks"] = d.get("marks", "")
                results.append(d)
            return results

    def is_nonworkday(self, daykey: str, country: str | None = None) -> bool:
        """
        Check if a date is a non-working day (government holiday or company special day).

        Args:
            daykey: Date in YYYYMMDD format
            country: Country code filter.  Accepts a single code ("US"), a
                     comma-separated list ("US,CA,GB"), or None to check all countries.

        Returns:
            True if the date is a non-working day
        """
        codes = _parse_country_codes(country)
        hols = self._python_holidays.get(daykey, [])
        if codes is not None:
            hols = [h for h in hols if h.get("country") in codes]
        if any(h.get("nonworkday") for h in hols):
            return True
        # Check company special days in the DB
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT 1 FROM companyspecialdays
                    WHERE startdate <= ? AND enddate >= ?
                    AND nonworkday = 1
                    LIMIT 1
                    """,
                    (daykey, daykey),
                )
                return cursor.fetchone() is not None
            except sqlite3.OperationalError:
                return False

    def is_government_nonworkday(self, daykey: str, country: str | None = None) -> bool:
        """
        Check if a date has a government holiday marked as a non-working day.

        Args:
            daykey: Date in YYYYMMDD format
            country: Country code filter.  Accepts a single code ("US"), a
                     comma-separated list ("US,CA,GB"), or None to check all countries.

        Returns:
            True if a government holiday with nonworkday=1 exists for this date
        """
        codes = _parse_country_codes(country)
        hols = self._python_holidays.get(daykey, [])
        if codes is not None:
            hols = [h for h in hols if h.get("country") in codes]
        return any(h.get("nonworkday") for h in hols)

    def get_special_markings_for_date(self, daykey: str) -> dict:
        """
        Get company special-day markings for a date.

        Args:
            daykey: Date in YYYYMMDD format

        Returns:
            Dictionary with 'nonworkday' bool and 'marks' list
        """
        special_days = self.get_special_days_for_date(daykey)

        nonworkday = any(day.get("nonworkday", 0) for day in special_days)

        marks = []
        for day in special_days:
            if day.get("marks"):
                marks.append(day["marks"])

        return {"nonworkday": nonworkday, "marks": marks}

    def get_holiday_title_for_date(
        self, daykey: str, country: str | None = None
    ) -> tuple[str | None, str | None]:
        """
        Get holiday title and icon for a date.

        Args:
            daykey: Date in YYYYMMDD format
            country: Country code filter (e.g. "US"). None selects all countries.

        Returns:
            Tuple of (title, icon) or (None, None) if no holiday
        """
        holidays = self.get_holidays_for_date(daykey, country)

        if holidays:
            holiday = holidays[0]
            title = holiday.get("displayname")
            raw_icon = (
                holiday.get("icon")
                or holiday.get("displayiconid")
                or holiday.get("displayicon")
                or ""
            )
            icon = str(raw_icon).strip()
            # Backward compatibility: if holiday icon is stored as numeric ID,
            # resolve it through fonticon.
            if icon.isdigit():
                resolved = self.get_icon_by_id(int(icon))
                if resolved:
                    icon = resolved
            return title, icon

        # Check company special days
        special_days = self.get_special_days_for_date(daykey)
        for day in special_days:
            if day.get("name"):
                return day.get("name"), day.get("icon", "")

        return None, None

    def get_all_events_in_range(self, start: str, end: str) -> list[dict]:
        """
        Get all events (including multi-day durations) that overlap with date range.

        Args:
            start: Start date in YYYYMMDD format
            end: End date in YYYYMMDD format

        Returns:
            List of event dictionaries with normalized field names
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id as ID,
                    priority as Priority,
                    wbs as WBS,
                    rollup as Rollup,
                    milestone as Milestone,
                    percent_complete as Percent_Complete,
                    name as Task_Name,
                    effort as Effort,
                    duration as Duration,
                    start_date as Start_Date,
                    end_date as Finish_Date,
                    predecessors as Predecessors,
                    resource_names as Resource_Names,
                    resource_group as Resource_Group,
                    notes as Notes,
                    icon as Icon,
                    color as Color,
                    marks as Marks,
                    start_date as Datekey,
                    start_date as Start,
                    end_date as End
                FROM events
                WHERE (start_date <= ? AND end_date >= ?)
                   OR (start_date >= ? AND start_date <= ?)
                ORDER BY priority, name
                """,
                (end, start, start, end),
            )
            rows = cursor.fetchall()

            events = []
            for row in rows:
                event = dict(row)
                # Set nonworkday to False for regular events
                event["nonworkday"] = False
                # Normalize None values (render layer handles None safely)
                for key, value in event.items():
                    if value is None:
                        event[key] = None
                events.append(event)

            return events

    def get_icon_by_id(self, icon_id: int) -> str | None:
        """
        Get icon name by ID from fonticon table.

        Args:
            icon_id: Icon ID

        Returns:
            Icon name or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM fonticon WHERE id = ?",
                (icon_id,),
            )
            row = cursor.fetchone()
            return row["name"] if row else None

    def get_all_icons(self) -> list[dict]:
        """
        Return all icon rows from icon table ordered by name.

        Returns:
            List of dict rows with keys: filename, name, alternativenames, svg
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT filename, name, alternativenames, svg FROM icon ORDER BY name"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_colors(self) -> list[dict]:
        """
        Return all color rows from colors table ordered by EN name.

        Returns:
            List of dict rows with keys: EN, hex, red, green, blue.
            ``hex`` is always computed from the rgb values so it is
            available even on databases that lack a dedicated ``hex`` column.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT EN, red, green, blue FROM colors ORDER BY EN")
            rows = []
            for row in cursor.fetchall():
                d = dict(row)
                r = int(d.get("red") or 0)
                g = int(d.get("green") or 0)
                b = int(d.get("blue") or 0)
                d["hex"] = f"#{r:02X}{g:02X}{b:02X}"
                rows.append(d)
            return rows

    def resolve_color_name(self, name: str) -> str:
        """Return the hex value for a DB color name, or the original string if not found.

        Looks up the EN column case-insensitively.  Allows themes to use
        human-friendly names like 'bondi blue' or 'roman silver' that are
        stored in the colors table but are not valid SVG/CSS color strings.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT red, green, blue FROM colors WHERE lower(EN) = lower(?)",
                (name,),
            )
            row = cursor.fetchone()
            if row is None:
                return name
            r, g, b = int(row["red"]), int(row["green"]), int(row["blue"])
            return f"#{r:02X}{g:02X}{b:02X}"

    @staticmethod
    def _split_icon_aliases(raw: str | None) -> list[str]:
        """Split alternativenames text into normalized aliases."""
        if not raw:
            return []
        cleaned = str(raw).replace("|", ",").replace(";", ",")
        aliases = [p.strip().lower() for p in cleaned.split(",")]
        return [a for a in aliases if a]

    def get_icon_svg_map(self) -> dict[str, str]:
        """
        Return an icon lookup map for name/aliases to SVG markup.

        Keys are lowercase icon names and aliases.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, alternativenames, svg FROM icon")
            icon_map: dict[str, str] = {}
            for row in cursor.fetchall():
                name = str(row["name"]).strip().lower()
                svg = row["svg"]
                if not name or not svg:
                    continue
                icon_map[name] = svg
                for alias in self._split_icon_aliases(row["alternativenames"]):
                    icon_map.setdefault(alias, svg)
            return icon_map

    def get_paper_sizes(self) -> dict[str, tuple[float, float]]:
        """
        Load paper sizes from the papersizes table.

        Returns a dict mapping paper name to (width_pts, height_pts) in
        portrait-canonical form (width <= height). When landscape=1 in the DB,
        width and height are swapped so the narrower dimension comes first.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, width_points, height_points, landscape "
                "FROM papersizes ORDER BY name"
            )
            sizes: dict[str, tuple[float, float]] = {}
            for row in cursor.fetchall():
                w = row["width_points"]
                h = row["height_points"]
                if row["landscape"] == 1:
                    sizes[row["name"]] = (h, w)
                else:
                    sizes[row["name"]] = (w, h)
            return sizes

    def get_paper_size_names(self) -> list[str]:
        """Return sorted list of available paper size names."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM papersizes ORDER BY name")
            return [row["name"] for row in cursor.fetchall()]

    def get_pattern_svg(self, name: str) -> str | None:
        """
        Return the SVG string for a named pattern, or None if not found.

        Args:
            name: Pattern name (e.g. "brick-wall", "polka-dots")

        Returns:
            SVG string or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT svg FROM patterns WHERE name = ?", (name,))
            row = cursor.fetchone()
            return row["svg"] if row else None

    def get_all_patterns(self) -> dict[str, str]:
        """
        Return all patterns as {name: svg} for bulk preloading.

        Returns:
            Dict mapping pattern name to SVG string
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, svg FROM patterns")
            return {row["name"]: row["svg"] for row in cursor.fetchall()}

    def get_palette(self, name: str) -> list[str] | None:
        """
        Return the color list for a named palette, or None if not found.

        Args:
            name: Palette name (e.g. "Accent", "afmhot")

        Returns:
            List of hex color strings (e.g. ["#7fc97f", "#beaed4", ...]) or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT palette FROM palettes WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row is None:
                return None
            return [c.strip() for c in row["palette"].split(",") if c.strip()]

    def get_all_palettes(self) -> dict[str, list[str]]:
        """
        Return all palettes as {name: [colors]} for bulk preloading.

        Returns:
            Dict mapping palette name to list of hex color strings
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, palette FROM palettes")
            return {
                row["name"]: [c.strip() for c in row["palette"].split(",") if c.strip()]
                for row in cursor.fetchall()
            }

    def sample_palette_n(self, name: str, n: int) -> list[str] | None:
        """
        Return exactly n colors from a named palette, cycling if shorter than n.

        Args:
            name: Palette name (e.g. "Accent", "Berlin")
            n: Number of colors to return

        Returns:
            List of n hex color strings, or None if palette not found
        """
        colors = self.get_palette(name)
        if colors is None:
            return None
        return [colors[i % len(colors)] for i in range(n)]

    def get_paper_sizes_grouped(self) -> dict[str, list[tuple[str, float, float]]]:
        """
        Load paper sizes grouped by category.

        Returns a dict mapping group name to list of (name, width_pts, height_pts)
        tuples in portrait-canonical form.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT "group", name, width_points, height_points, landscape '
                'FROM papersizes ORDER BY "group", name'
            )
            groups: dict[str, list[tuple[str, float, float]]] = {}
            for row in cursor.fetchall():
                w = row["width_points"]
                h = row["height_points"]
                if row["landscape"] == 1:
                    w, h = h, w
                group = row["group"]
                if group not in groups:
                    groups[group] = []
                groups[group].append((row["name"], w, h))
            return groups


if __name__ == "__main__":
    # Test the database access
    db = CalendarDB()
    print("Testing CalendarDB...")

    # Test get_events_for_date_range
    events = db.get_events_for_date_range("20250101", "20250131")
    print(f"Events in January 2025: {len(events)}")

    # Test get_holidays_for_date
    holidays = db.get_holidays_for_date("20250101", "US")
    print(f"Holidays on 2025-01-01: {holidays}")

    # Test is_nonworkday
    is_nwd = db.is_nonworkday("20250101", "US")
    print(f"Is 2025-01-01 a non-workday? {is_nwd}")
