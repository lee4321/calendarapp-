"""A list ``fill`` cycles across vertical_line band segments only.

Every other target draws a single color, so it takes the list's first entry
rather than a Python list that would reach the SVG as ``"['red', 'blue']"``.
"""

from __future__ import annotations

from shared.rule_engine import DayContext, StyleEngine


def _rules(apply_to: str, select: dict, fill: list) -> list[dict]:
    return [{"apply_to": apply_to, "select": select, "style": {"fill": fill}}]


def test_day_box_rule_takes_the_first_color_of_a_fill_list():
    engine = StyleEngine(_rules("day_box", {"workday": True}, ["red", "blue"]))
    assert engine.evaluate_day(DayContext(date="20260914")).fill_color == "red"


def test_empty_entries_in_a_fill_list_are_skipped():
    engine = StyleEngine(_rules("day_box", {}, ["", "blue"]))
    assert engine.evaluate_day(DayContext(date="20260914")).fill_color == "blue"


def test_vertical_line_rule_keeps_the_whole_fill_list():
    engine = StyleEngine(
        _rules("vertical_line", {"band": "Month", "repeat": True}, ["red", "blue"])
    )
    [(_, sr)] = engine.evaluate_band_segment("Month", "Sep")
    assert sr.fill_color == ["red", "blue"]
