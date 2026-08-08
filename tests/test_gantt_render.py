"""Gantt rendering: the day axis, weekend handling, and row capacity.

The axis decision is the one that shapes every later phase: with
``weekend_style == 0`` non-working days leave the axis entirely, so bar
geometry is column-index based rather than linear in date.
"""

from __future__ import annotations

from datetime import date

import pytest

from config.config import CalendarConfig
from shared.date_utils import visible_days
from visualizers.gantt.renderer import GanttRenderer


@pytest.fixture
def config() -> CalendarConfig:
    config = CalendarConfig()
    config.pageX, config.pageY = 792.0, 612.0
    return config


# ── Date range ────────────────────────────────────────────────────────────


def test_range_comes_from_the_user_dates(config):
    config.userstart, config.userend = "20260202", "20260213"
    assert GanttRenderer._range(config) == (date(2026, 2, 2), date(2026, 2, 13))


def test_range_falls_back_to_the_adjusted_dates(config):
    config.userstart, config.userend = "", ""
    config.adjustedstart, config.adjustedend = "20260202", "20260213"
    assert GanttRenderer._range(config) == (date(2026, 2, 2), date(2026, 2, 13))


def test_a_reversed_range_is_put_back_in_order(config):
    config.userstart, config.userend = "20260213", "20260202"
    assert GanttRenderer._range(config) == (date(2026, 2, 2), date(2026, 2, 13))


# ── The day axis ──────────────────────────────────────────────────────────


def test_workweek_style_drops_weekend_columns_entirely():
    """weekend_style 0: Sat/Sun are not columns, so the axis is non-linear."""
    days = visible_days(date(2026, 2, 2), date(2026, 2, 15), 0)
    assert len(days) == 10
    assert all(day.weekday() < 5 for day in days)


@pytest.mark.parametrize("style", [1, 2, 3, 4])
def test_other_weekend_styles_keep_every_day(style):
    days = visible_days(date(2026, 2, 2), date(2026, 2, 15), style)
    assert len(days) == 14
    assert any(day.weekday() >= 5 for day in days)


def test_day_width_divides_the_chart_evenly():
    days = visible_days(date(2026, 2, 2), date(2026, 2, 6), 0)
    assert GanttRenderer._day_width(500.0, days) == pytest.approx(100.0)


def test_day_width_is_zero_without_days():
    assert GanttRenderer._day_width(500.0, []) == 0.0


# ── Row capacity ──────────────────────────────────────────────────────────


def test_row_capacity_is_the_body_height_over_the_row_height(config):
    config.gantt_row_height = 10.0
    assert GanttRenderer()._rows_that_fit(config, 105.0) == 10


def test_a_body_shorter_than_one_row_holds_none(config):
    config.gantt_row_height = 20.0
    assert GanttRenderer()._rows_that_fit(config, 5.0) == 0


def test_a_degenerate_row_height_cannot_divide_by_zero(config):
    config.gantt_row_height = 0.0
    assert GanttRenderer()._rows_that_fit(config, 100.0) == 100
