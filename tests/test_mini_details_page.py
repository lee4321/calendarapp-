"""
Tests for the mini / mini-icon / candybar companion details page.

The page lists the range's events and then the holidays and special days
the calendar shows.  It is written by the shared details-page writer, so
what is tested here is mini's content and its column model rather than
the page mechanics (those live in tests/test_details_page.py).
"""

from __future__ import annotations

from config.config import create_calendar_config, setfontsizes
from shared.date_utils import calc_calendar_range
from visualizers.mini.renderer import MiniCalendarRenderer


def _config(**overrides):
    cfg = create_calendar_config()
    cfg.pageX = 792.0
    cfg.pageY = 612.0
    calc_calendar_range(cfg, "20260401", "20260630")
    setfontsizes(cfg)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _event(**fields) -> dict:
    base = {
        "Start": "20260403",
        "End": "20260403",
        "Task_Name": "Sprint 1 Demo",
        "Notes": "",
        "Milestone": 0,
        "Priority": 2,
        "Resource_Group": "Product",
    }
    base.update(fields)
    return base


# ── Columns ───────────────────────────────────────────────────────────────

def test_columns_come_from_the_theme_headers():
    cfg = _config(
        mini_details_headers=["When", "What", "Who"],
        mini_details_column_widths=[1.0, 2.0, 1.0],
    )
    columns = MiniCalendarRenderer._details_columns(cfg)

    assert [c.heading for c in columns] == ["When", "What", "Who"]
    assert [round(c.width, 3) for c in columns] == [0.25, 0.5, 0.25]


def test_mismatched_headers_and_widths_fall_back_together():
    """A half-edited theme would otherwise put the wrong heading over
    every column."""
    cfg = _config(
        mini_details_headers=["When", "What", "Who"],
        mini_details_column_widths=[0.5, 0.5],
    )
    columns = MiniCalendarRenderer._details_columns(cfg)

    assert [c.heading for c in columns][:2] == ["Start Date", "Name / Description"]
    assert len(columns) == 5


def test_widths_are_normalized_to_span_the_page_once():
    cfg = _config()
    columns = MiniCalendarRenderer._details_columns(cfg)

    assert round(sum(c.width for c in columns), 6) == 1.0


def test_the_date_and_name_columns_carry_their_own_text_tokens():
    cfg = _config()
    columns = MiniCalendarRenderer._details_columns(cfg)

    assert columns[0].token == "text:event_date"
    assert columns[0].css_class == "ec-event-date"
    assert columns[1].token == "text:event_name"
    assert columns[1].css_class == "ec-event-name"


# ── Row content ───────────────────────────────────────────────────────────

def test_a_row_states_the_event_across_the_default_columns():
    cells = MiniCalendarRenderer._details_event_cells(
        _event(Milestone=1, Priority=1), 5
    )

    assert cells == ["2026-04-03", "Sprint 1 Demo", "True", "1", "Product"]


def test_a_row_is_padded_or_trimmed_to_the_column_count():
    """A theme asking for fewer columns must not slide the next event's
    values left, nor a wider one leave a short row."""
    assert MiniCalendarRenderer._details_event_cells(_event(), 2) == [
        "2026-04-03", "Sprint 1 Demo",
    ]
    assert MiniCalendarRenderer._details_event_cells(_event(), 7)[-2:] == ["", ""]


def test_a_single_day_event_notes_carry_no_end_date():
    note = MiniCalendarRenderer._details_event_note(
        _event(Notes="Stakeholder demo")
    )

    assert note == "Stakeholder demo"


def test_a_multi_day_event_states_its_end_date_in_the_sub_line():
    note = MiniCalendarRenderer._details_event_note(
        _event(End="20260410", Notes="Stakeholder demo")
    )

    assert note == "Stakeholder demo | End: 2026-04-10"


def test_a_multi_day_event_with_no_notes_still_states_its_end():
    note = MiniCalendarRenderer._details_event_note(_event(End="20260410"))

    assert note == "End: 2026-04-10"


def test_a_finish_column_stands_in_for_a_missing_end():
    note = MiniCalendarRenderer._details_event_note(
        {"Start": "20260403", "Finish": "20260410", "Task_Name": "x", "Notes": ""}
    )

    assert note == "End: 2026-04-10"


# ── Ordering ──────────────────────────────────────────────────────────────

def test_events_are_listed_by_span_then_name():
    events = [
        _event(Start="20260410", Task_Name="Later"),
        _event(Start="20260403", Task_Name="Beta"),
        _event(Start="20260403", Task_Name="Alpha"),
    ]
    ordered = MiniCalendarRenderer._details_sorted_events(events)

    assert [e["Task_Name"] for e in ordered] == ["Alpha", "Beta", "Later"]


# ── The flags that switch the page on and off ─────────────────────────────

def _parse(view: str, *flags):
    from cli.args import _create_argument_parser

    return _create_argument_parser("out.svg").parse_args([view, *flags])


def test_the_page_is_written_by_default():
    assert create_calendar_config().include_mini_details is True


def test_no_mini_details_suppresses_the_page():
    """The page used to be unsuppressable: it defaults on and the only
    flag could only turn it on again."""
    from cli.config_assembly import _apply_cli_config_overrides

    cfg = create_calendar_config()
    _apply_cli_config_overrides(_parse("mini", "--no-mini-details"), cfg)

    assert cfg.include_mini_details is False


def test_mini_details_turns_the_page_back_on_over_a_theme():
    from cli.config_assembly import _reapply_post_theme_cli_overrides

    cfg = create_calendar_config()
    cfg.include_mini_details = False  # as a theme's mini_details.enable would
    _reapply_post_theme_cli_overrides(_parse("mini", "--mini-details"), cfg)

    assert cfg.include_mini_details is True


def test_every_view_that_writes_the_page_can_name_it():
    """candybar and mini-icon inherit the renderer that writes the page,
    so they need the flags that govern it."""
    for view in ("mini", "mini-icon", "candybar"):
        assert _parse(view, "--no-mini-details").no_mini_details is True
        assert _parse(view, "--mini-details").mini_details is True
