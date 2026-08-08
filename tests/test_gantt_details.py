"""The companion details page: task listing, exception log, and its pagination."""

from __future__ import annotations

import pytest

from test_gantt_marks import render, task
from visualizers.gantt.details import (
    KIND_CLIPPED_END,
    KIND_HIDDEN_HOLIDAY,
    KIND_LABELS,
    KIND_SNAPPED_EVENT,
    GanttException,
    details_output_path,
    format_datekey,
)


# ── Small helpers ─────────────────────────────────────────────────────────


def test_the_details_suffix_is_inserted_before_the_extension():
    assert details_output_path("output/chart.svg", "_details") == (
        "output/chart_details.svg"
    )


def test_a_path_without_an_extension_still_gets_one():
    assert details_output_path("chart", "_details") == "chart_details.svg"


@pytest.mark.parametrize(
    "raw,expected",
    [("20260202", "2026-02-02"), ("", ""), ("nonsense", "nonsense"), (None, "")],
)
def test_datekeys_are_formatted_for_reading(raw, expected):
    assert format_datekey(raw) == expected


def test_every_exception_kind_has_a_readable_label():
    for kind in KIND_LABELS:
        assert GanttException(kind=kind, task="t").label == KIND_LABELS[kind]


def test_an_unknown_kind_falls_back_to_its_own_name():
    assert GanttException(kind="mystery", task="t").label == "mystery"


# ── Files written ─────────────────────────────────────────────────────────


def test_the_details_page_is_written_next_to_the_chart(tmp_path):
    output = tmp_path / "chart.svg"
    renderer = render([task()], outputfile=str(output))

    assert (tmp_path / "chart_details.svg").exists()
    assert renderer._details_page_count == 1


def test_the_details_page_can_be_switched_off(tmp_path):
    output = tmp_path / "chart.svg"
    renderer = render([task()], outputfile=str(output), include_gantt_details=False)

    assert not (tmp_path / "chart_details.svg").exists()
    assert renderer._details_page_count == 0


def test_a_long_listing_continues_onto_further_details_pages(tmp_path):
    """The log must not be truncated — it is the point of the page."""
    output = tmp_path / "chart.svg"
    tasks = [
        task(Task_Name=f"task {n}", Source_ID=str(n), WBS=f"1.{n}")
        for n in range(120)
    ]
    renderer = render(tasks, outputfile=str(output))

    assert renderer._details_page_count >= 2
    assert (tmp_path / "chart_details_p2.svg").exists()


def test_the_details_pass_restores_the_chart_drawing(tmp_path):
    """The base class saves whatever is in _drawing as page 1.

    Leaving the last details page there would write the details content
    over the chart.  This harness starts with no drawing, so the check is
    that the value it was given back is the one it started with.
    """
    output = tmp_path / "chart.svg"
    renderer = render([task()], outputfile=str(output))
    assert renderer._drawing is None
    assert renderer._details_page_count == 1   # details really did render


# ── Content ───────────────────────────────────────────────────────────────


def details_text(renderer) -> list[str]:
    """Every string drawn, in order."""
    return [item["text"] for item in renderer.texts]


def test_both_sections_are_titled(tmp_path):
    renderer = render([task()], outputfile=str(tmp_path / "chart.svg"))
    text = details_text(renderer)
    assert "Gantt Details" in text
    assert "Tasks" in text
    assert "Exceptions" in text


def test_each_section_heading_is_drawn_once_per_page(tmp_path):
    """A page break replays the heading; starting the first page must not."""
    renderer = render([task()], outputfile=str(tmp_path / "chart.svg"))
    text = details_text(renderer)
    assert text.count("Tasks") == 1
    assert text.count("Exceptions") == 1


def test_every_task_is_listed(tmp_path):
    tasks = [
        task(Task_Name=f"task {n}", Source_ID=str(n), WBS=f"1.{n}")
        for n in range(5)
    ]
    renderer = render(tasks, outputfile=str(tmp_path / "chart.svg"))
    text = details_text(renderer)
    for n in range(5):
        assert f"task {n}" in text


def test_icon_columns_are_spelled_out_rather_than_left_blank(tmp_path):
    """The page has no glyphs, so `rollup` reads as a word."""
    renderer = render(
        [task(Task_Name="a rollup", Rollup=1)],
        outputfile=str(tmp_path / "chart.svg"),
    )
    assert "Yes" in details_text(renderer)


def test_a_clean_chart_says_so(tmp_path):
    renderer = render([task()], outputfile=str(tmp_path / "chart.svg"))
    assert renderer.exceptions == []
    assert "Every item was drawn as scheduled." in details_text(renderer)


def test_exceptions_reach_the_page(tmp_path):
    renderer = render(
        [
            task(Task_Name="overrun", Start="20260210", End="20260601"),
            task(Task_Name="saturday", Start="20260207", End="20260207"),
        ],
        outputfile=str(tmp_path / "chart.svg"),
    )
    text = details_text(renderer)

    kinds = {e.kind for e in renderer.exceptions}
    assert {KIND_CLIPPED_END, KIND_SNAPPED_EVENT} <= kinds
    assert KIND_LABELS[KIND_CLIPPED_END] in text
    assert KIND_LABELS[KIND_SNAPPED_EVENT] in text
    assert "2026-02-07" in text          # the snapped event's own date


def test_a_hidden_holiday_is_reported_without_a_task_name(tmp_path):
    class _HolidayDB:
        holidays = {"20260208"}          # a Sunday

        @staticmethod
        def get_palette(name):
            return None

        @staticmethod
        def get_icon_svg_map():
            return {}

        @classmethod
        def is_government_nonworkday(cls, daykey, country=None):
            return daykey in cls.holidays

        @staticmethod
        def get_special_days_for_date(daykey):
            return []

    renderer = render(
        [task()], db=_HolidayDB(), outputfile=str(tmp_path / "chart.svg")
    )
    entry = next(e for e in renderer.exceptions if e.kind == KIND_HIDDEN_HOLIDAY)
    assert entry.task == ""
    assert entry.datekey == "20260208"
    assert KIND_LABELS[KIND_HIDDEN_HOLIDAY] in details_text(renderer)
