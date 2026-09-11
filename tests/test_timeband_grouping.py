"""``show_every`` cell merging, shared by every visualizer with timebands.

:func:`shared.timeband.group_segments` is what blockplan and compactplan
both merge a band's segments through, so a catalog entry's ``show_every``
reads the same wherever it is placed.
"""

from __future__ import annotations

from datetime import date

from config.config import CalendarConfig
from shared.timeband import build_segments, group_segments

# Mon 4 May – Fri 15 May 2026, weekdays only: two working weeks.
_WEEKDAYS = [date(2026, 5, d) for d in (4, 5, 6, 7, 8, 11, 12, 13, 14, 15)]


def _date_cells(band: dict, **kwargs) -> list[list[int]]:
    segments = build_segments(
        band, _WEEKDAYS[0], _WEEKDAYS[-1], CalendarConfig(), visible_days=_WEEKDAYS
    )
    return [[seg.start.day for seg in cell] for cell in group_segments(segments, band, **kwargs)]


def test_without_show_every_each_segment_is_its_own_cell():
    assert _date_cells({"unit": "date"}) == [[d.day] for d in _WEEKDAYS]


def test_show_every_merges_that_many_date_cells():
    assert _date_cells({"unit": "date", "show_every": 2}) == [
        [4, 5], [6, 7], [8], [11, 12], [13, 14], [15],
    ]


def test_a_merged_date_cell_never_crosses_a_week():
    """Fri 8 stays alone rather than joining Mon 11, so the date row's
    borders line up with the week row above it."""
    cells = _date_cells({"unit": "date", "show_every": 3})

    assert cells == [[4, 5, 6], [7, 8], [11, 12, 13], [14, 15]]


def test_the_week_start_decides_where_a_merge_must_break():
    cells = _date_cells({"unit": "date", "show_every": 3, "week_start": 2})

    # Weeks begin on Wednesday: a cell ends before every Wednesday.
    assert cells == [[4, 5], [6, 7, 8], [11, 12], [13, 14, 15]]


def test_the_caller_supplies_the_default_week_start():
    cells = _date_cells({"unit": "date", "show_every": 3}, week_start_default=2)

    assert cells == [[4, 5], [6, 7, 8], [11, 12], [13, 14, 15]]


def test_other_units_merge_straight_through():
    band = {"unit": "week", "show_every": 2}
    segments = build_segments(
        band, date(2026, 5, 4), date(2026, 6, 26), CalendarConfig()
    )
    cells = group_segments(segments, band)

    assert [len(cell) for cell in cells] == [2, 2, 2, 2]
