"""Unit tests for StyleEngine.evaluate_band_segment (vertical_line apply_to)."""

from __future__ import annotations

from shared.rule_engine import DayContext, StyleEngine


def test_band_match_required():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Month", "repeat": True},
            "style": {"stroke_color": "red"},
        }
    ]
    engine = StyleEngine(rules)
    assert engine.evaluate_band_segment("Week", "W1") == []
    out = engine.evaluate_band_segment("Month", "Feb")
    assert len(out) == 1
    rule_index, sr = out[0]
    assert rule_index == 0
    assert sr.stroke_color == "red"


def test_repeat_true_ignores_value():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Week", "repeat": True},
            "style": {"stroke_color": "blue"},
        }
    ]
    engine = StyleEngine(rules)
    out_a = engine.evaluate_band_segment("Week", "W1")
    out_b = engine.evaluate_band_segment("Week", "W47")
    assert len(out_a) == 1 and len(out_b) == 1


def test_value_match_is_case_insensitive():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Day", "value": "tue"},
            "style": {"stroke_color": "magenta"},
        }
    ]
    engine = StyleEngine(rules)
    assert engine.evaluate_band_segment("DAY", "Tue") != []
    assert engine.evaluate_band_segment("Day", "TUE") != []
    assert engine.evaluate_band_segment("Day", "wed") == []


def test_value_required_when_repeat_absent():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Date"},  # no value, no repeat
            "style": {"stroke_color": "red"},
        }
    ]
    engine = StyleEngine(rules)
    assert engine.evaluate_band_segment("Date", "20260201") == []


def test_day_context_filters_segments():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Date", "repeat": True, "weekend": True},
            "style": {"fill_color": "lightgrey"},
        }
    ]
    engine = StyleEngine(rules)
    weekend_ctx = DayContext(date="20260207", weekend=True, nonworkday=True, workday=False)
    weekday_ctx = DayContext(date="20260205", weekend=False, nonworkday=False, workday=True)
    assert engine.evaluate_band_segment("Date", "20260207", weekend_ctx) != []
    assert engine.evaluate_band_segment("Date", "20260205", weekday_ctx) == []


def test_rule_index_is_stable_across_segments():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Month", "repeat": True},
            "style": {"stroke_color": "red"},
        },
        {
            "apply_to": "day_box",  # not a vertical_line rule
            "select": {"weekend": True},
            "style": {"fill_color": "grey"},
        },
        {
            "apply_to": "vertical_line",
            "select": {"band": "Quarter", "repeat": True},
            "style": {"stroke_color": "navy"},
        },
    ]
    engine = StyleEngine(rules)
    month_match = engine.evaluate_band_segment("Month", "Jan")[0]
    quarter_match = engine.evaluate_band_segment("Quarter", "Q1")[0]
    # rule_index should reflect the rule's position in the original list, not
    # its position among vertical_line rules only. So Month → 0 and Quarter → 2.
    assert month_match[0] == 0
    assert quarter_match[0] == 2


def test_apply_to_all_matches_vertical_line():
    rules = [
        {
            "apply_to": "all",
            "select": {"band": "Month", "repeat": True},
            "style": {"stroke_color": "purple"},
        }
    ]
    engine = StyleEngine(rules)
    assert engine.evaluate_band_segment("Month", "Feb") != []


def test_align_round_trips_through_style_block():
    rules = [
        {
            "apply_to": "vertical_line",
            "select": {"band": "Week", "repeat": True},
            "style": {"align": "End", "stroke_color": "red"},  # mixed case
        }
    ]
    engine = StyleEngine(rules)
    _, sr = engine.evaluate_band_segment("Week", "W1")[0]
    assert sr.align == "end"
