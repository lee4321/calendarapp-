"""Gantt pagination: page planning, continuation files, and timescale continuity."""

from __future__ import annotations

from datetime import date

import pytest
from band_helpers import set_bands, set_fields
from test_gantt_marks import render, task

from config.config import create_calendar_config
from shared.date_utils import visible_days
from visualizers.gantt.layout import GanttLayout, plan_pages
from visualizers.gantt.renderer import _page_output_path

# ── Page planning ─────────────────────────────────────────────────────────


def test_a_chart_that_fits_is_one_page():
    pages = plan_pages(row_count=5, day_count=10, rows_per_page=10, days_per_page=20)
    assert len(pages) == 1
    assert (pages[0].row_start, pages[0].row_end) == (0, 5)
    assert (pages[0].day_start, pages[0].day_end) == (0, 10)
    assert pages[0].is_first


def test_rows_split_vertically():
    pages = plan_pages(row_count=5, day_count=10, rows_per_page=2, days_per_page=20)
    assert [(p.row_start, p.row_end) for p in pages] == [(0, 2), (2, 4), (4, 5)]
    assert all(p.day_start == 0 and p.day_end == 10 for p in pages)


def test_days_split_horizontally():
    pages = plan_pages(row_count=2, day_count=10, rows_per_page=10, days_per_page=4)
    assert [(p.day_start, p.day_end) for p in pages] == [(0, 4), (4, 8), (8, 10)]


def test_pages_run_row_major_so_one_task_reads_across_consecutive_pages():
    pages = plan_pages(row_count=4, day_count=8, rows_per_page=2, days_per_page=4)
    assert [(p.row_start, p.day_start) for p in pages] == [
        (0, 0),
        (0, 4),  # first rows, both halves of the range
        (2, 0),
        (2, 4),  # then the next rows
    ]


def test_pages_are_numbered_from_one():
    pages = plan_pages(row_count=4, day_count=8, rows_per_page=2, days_per_page=4)
    assert [p.number for p in pages] == [1, 2, 3, 4]
    assert [p.is_first for p in pages] == [True, False, False, False]


def test_an_exact_multiple_does_not_add_an_empty_page():
    pages = plan_pages(row_count=4, day_count=4, rows_per_page=2, days_per_page=2)
    assert len(pages) == 4
    assert all(p.row_count == 2 for p in pages)


def test_a_chart_with_no_rows_still_renders_one_page():
    pages = plan_pages(row_count=0, day_count=10, rows_per_page=5, days_per_page=10)
    assert len(pages) == 1
    assert pages[0].row_count == 0


@pytest.mark.parametrize("per_page", [0, -3])
def test_degenerate_page_sizes_cannot_produce_endless_pages(per_page):
    pages = plan_pages(row_count=3, day_count=3, rows_per_page=per_page, days_per_page=per_page)
    assert len(pages) == 9  # one row × one day each


# ── Continuation filenames (answer 12) ────────────────────────────────────


def test_continuation_pages_are_named_p2_p3():
    assert _page_output_path("output/chart.svg", 2) == "output/chart_p2.svg"
    assert _page_output_path("output/chart.svg", 3) == "output/chart_p3.svg"


def test_the_suffix_is_unpadded_unlike_the_sample_sheets():
    assert _page_output_path("chart.svg", 10) == "chart_p10.svg"


def test_a_path_without_an_extension_still_gets_one():
    assert _page_output_path("chart", 2) == "chart_p2.svg"


# ── Timescale continuity (answer 11) ──────────────────────────────────────


def week_row_over(start: date, end: date, page_slice: slice | None = None):
    """The week row planned over the whole range, drawn on the page ``days[page_slice]``."""
    from renderers.timescale import ScaleContext, plan_rows
    from shared.span import Span

    config = create_calendar_config()
    set_bands(config, primary=[{"label": "Week", "unit": "week", "label_format": "W{n}"}])
    days = visible_days(start, end, int(config.weekend_style))
    page = days[page_slice] if page_slice else days
    ctx = ScaleContext(config.theme_v3, config, None, [], measure=lambda *_: 0.0)
    plan = plan_rows(config.theme_v3.timescale.primary, Span(page, 0, 1000), ctx, full_days=days, min_segment_width=0)
    return plan.rows[0].cells, days


def test_band_segments_are_built_once_for_the_whole_range():
    """Per-page building would restart interval counters at each break."""
    cells, _days = week_row_over(date(2026, 2, 2), date(2027, 6, 30))

    assert cells[0].label == "W1"
    assert cells[-1].label != "W1", "week numbering must not restart mid-range"


def test_a_later_page_keeps_the_running_label():
    whole, _days = week_row_over(date(2026, 2, 2), date(2028, 12, 31))
    page, _ = week_row_over(date(2026, 2, 2), date(2028, 12, 31), slice(240, 480))
    by_start = {c.start: c.label for c in whole}

    # Whatever the page break, a week's label depends only on the date, never on the page.
    assert page[0].label != "W1"
    assert all(by_start[c.start] == c.label for c in page if not c.continues_before)


# ── Rendering across pages ────────────────────────────────────────────────


def many_tasks(count: int) -> list[dict]:
    return [task(Task_Name=f"task {n}", Source_ID=str(n), WBS=f"1.{n}") for n in range(count)]


def test_extra_pages_are_written_and_counted(tmp_path):
    """A page too short for every row spills into continuation files."""
    output = tmp_path / "chart.svg"
    renderer = render(
        many_tasks(30),
        outputfile=str(output),
        gantt_row_height=40.0,  # forces only a few rows per page
    )
    extra = renderer._extra_page_count
    assert extra >= 1
    for page in range(2, extra + 2):
        assert (tmp_path / f"chart_p{page}.svg").exists()


def test_a_chart_that_fits_writes_no_continuation_files(tmp_path):
    output = tmp_path / "chart.svg"
    renderer = render([task()], outputfile=str(output))
    assert renderer._extra_page_count == 0
    assert not (tmp_path / "chart_p2.svg").exists()


def test_horizontal_splitting_honors_the_minimum_day_width(tmp_path):
    """A range too long for legible columns splits instead of shrinking."""
    output = tmp_path / "chart.svg"
    renderer = render(
        [task()],
        start="20260202",
        end="20260731",
        outputfile=str(output),
        gantt_min_day_width=40.0,
    )
    assert renderer._extra_page_count >= 1


def test_a_zero_minimum_day_width_never_splits_horizontally(tmp_path):
    output = tmp_path / "chart.svg"
    renderer = render(
        [task()],
        start="20260202",
        end="20261231",
        outputfile=str(output),
        gantt_min_day_width=0.0,
    )
    assert renderer._extra_page_count == 0


def test_each_page_repeats_the_column_headers(tmp_path):
    """Answer 10/11: headers and timescale repeat on every page."""
    output = tmp_path / "chart.svg"
    renderer = render(
        many_tasks(30),
        outputfile=str(output),
        gantt_row_height=40.0,
    )
    pages = renderer._extra_page_count + 1
    headers = renderer.of_class(renderer.texts, "ec-column-header")
    assert len(headers) == 17 * pages


def test_rows_on_a_later_page_start_at_the_top_of_the_body(tmp_path):
    """The page's first row draws at the body's top edge, not its global offset."""
    output = tmp_path / "chart.svg"
    renderer = render(
        many_tasks(30),
        outputfile=str(output),
        gantt_row_height=40.0,
    )
    config = create_calendar_config()
    config.pageX, config.pageY = 1000.0, 400.0
    coords = GanttLayout().calculate(config)
    body_top = coords["GanttTableBody"][1]

    bars = renderer.of_class(renderer.rects, "ec-duration-bar")
    assert min(bar["y"] for bar in bars) < body_top + 40.0


def test_a_page_break_never_cuts_a_month_that_fits_a_page():
    """Pages come out a little shorter rather than splitting a month (decision 24)."""
    from visualizers.gantt.renderer import GanttRenderer

    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 612.0
    config.weekend_style = 1
    config.userstart = config.adjustedstart = "20260101"
    config.userend = config.adjustedend = "20260630"
    set_fields(config, gantt_min_day_width=5.0)
    set_bands(config, primary=[{"label": "Month", "unit": "month"}, {"label": "Date", "unit": "date"}], secondary=[])
    coords = GanttLayout().calculate(config)
    days = visible_days(date(2026, 1, 1), date(2026, 6, 30), 1)

    pages = GanttRenderer()._plan_pages(config, coords, [], days)

    assert len(pages) > 1
    starts = [days[p.day_start] for p in pages]
    assert all(d.day == 1 for d in starts), starts  # every page begins on the first of a month
    assert [days[p.day_end - 1] for p in pages[:-1]] == [
        d - __import__("datetime").timedelta(days=1) for d in starts[1:]
    ]


def test_a_segment_longer_than_a_page_is_clipped_on_every_page_it_crosses():
    from renderers.timescale import ScaleContext, plan_rows
    from shared.span import Span

    config = create_calendar_config()
    set_bands(config, primary=[{"label": "Year", "unit": "year", "date_format": "YYYY"}])
    days = visible_days(date(2026, 1, 1), date(2026, 12, 31), 1)
    ctx = ScaleContext(config.theme_v3, config, None, [], measure=lambda *_: 0.0)
    for page_days in (days[0:100], days[100:200]):
        (row,) = plan_rows(
            config.theme_v3.timescale.primary, Span(page_days, 0, 500), ctx, full_days=days, min_segment_width=0
        ).rows
        assert [c.label for c in row.cells] == ["2026"]  # the label is repeated on every page
