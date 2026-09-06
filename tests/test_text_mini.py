import tempfile
from pathlib import Path

import pytest

import ecalendar
from config.config import create_calendar_config, setfontsizes
from visualizers.text_mini.visualizer import TextMiniCalendarVisualizer


#: Minimal paper-size table; _apply_args_to_config only looks the name up.
_PAPER_SIZES = {"Widescreen": (1056.0, 594.0), "Letter": (792.0, 612.0)}


class _FakeDB:
    def __init__(self, events, holidays=None, specials=None):
        self._events = events
        self._holidays = holidays or {}
        self._specials = specials or {}

    def get_all_events_in_range(self, start, end):
        return self._events

    def get_holidays_for_date(self, daykey, country=None):
        return self._holidays.get(daykey, [])

    def get_special_days_for_date(self, daykey):
        return self._specials.get(daykey, [])


def test_text_mini_generates_file_with_symbols():
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.userstart = "20260101"
    config.userend = "20260131"
    config.adjustedstart = "20260101"
    config.adjustedend = "20260131"
    config.mini_columns = 1
    config.mini_rows = 1
    config.mini_show_week_numbers = True
    config.rollups = False

    events = [
        {
            "Start": "20260115",
            "End": "20260115",
            "Task_Name": "Milestone 1",
            "Milestone": True,
            "Priority": 1,
        }
    ]
    holidays = {
        "20260107": [{"displayname": "Holiday", "nonworkday": 1}],
    }

    db = _FakeDB(events, holidays=holidays)
    visualizer = TextMiniCalendarVisualizer()

    with tempfile.TemporaryDirectory() as td:
        config.outputfile = str(Path(td) / "mini.txt")
        result = visualizer.generate(config, db)
        content = Path(result.output_path).read_text(encoding="utf-8")

    assert "Milestone 1" in content
    assert "Holiday" in content


def _config_for(tmp_dir, **overrides):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.userstart = config.adjustedstart = "20260101"
    config.userend = config.adjustedend = "20260131"
    config.mini_columns = config.mini_rows = 1
    config.rollups = False
    config.outputfile = str(Path(tmp_dir) / "mini.txt")
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


_MIXED_EVENTS = [
    {
        "Start": "20260115", "End": "20260115",
        "Task_Name": "Kickoff", "Milestone": True,
    },
    {
        "Start": "20260119", "End": "20260119",
        "Task_Name": "Review", "Milestone": False,
    },
    {
        "Start": "20260105", "End": "20260123",
        "Task_Name": "Long Build", "Milestone": False,
    },
]


def _text_for(includedurations):
    db = _FakeDB(
        _MIXED_EVENTS,
        holidays={"20260101": [{"displayname": "New Year", "nonworkday": 1}]},
        specials={"20260107": [{"name": "Company Day", "nonworkday": 1}]},
    )
    with tempfile.TemporaryDirectory() as td:
        config = _config_for(td, includedurations=includedurations)
        TextMiniCalendarVisualizer().generate(config, db)
        return Path(config.outputfile).read_text(encoding="utf-8")


def test_text_mini_defaults_to_excluding_durations():
    """A multi-day bar paints a run of fill symbols across the grid and
    buries the single-day marks it crosses, so text-mini leaves it out."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    args = parser.parse_args(["text-mini", "20260101", "20260131"])
    config = create_calendar_config()
    ecalendar._apply_args_to_config(args, config, _PAPER_SIZES)

    assert config.includedurations is False
    # Everything text-mini does show is still on.
    assert config.includeevents is True


def test_text_mini_takes_durations_when_asked():
    parser = ecalendar._create_argument_parser("calendar.svg")
    args = parser.parse_args(
        ["text-mini", "20260101", "20260131", "--durations"]
    )
    config = create_calendar_config()
    ecalendar._apply_args_to_config(args, config, _PAPER_SIZES)

    assert config.includedurations is True


def test_mini_family_no_longer_offers_nodurations():
    """The opt-out is gone: it would only restate the default."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    for command in ("text-mini", "mini", "mini-icon", "candybar"):
        with pytest.raises(SystemExit):
            parser.parse_args(
                [command, "20260101", "20260131", "--nodurations"]
            )


def test_mini_family_defaults_to_excluding_durations():
    """mini, mini-icon and candybar paint a duration bar across a run of day
    cells and bury the day marks under it, so they follow text-mini: single-day
    events and milestones only, with --durations to opt back in."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    for command in ("mini", "mini-icon", "candybar"):
        config = create_calendar_config()
        args = parser.parse_args([command, "20260101", "20260131"])
        ecalendar._apply_args_to_config(args, config, _PAPER_SIZES)
        assert config.includedurations is False, command
        assert config.includeevents is True, command

        config = create_calendar_config()
        args = parser.parse_args(
            [command, "20260101", "20260131", "--durations"]
        )
        ecalendar._apply_args_to_config(args, config, _PAPER_SIZES)
        assert config.includedurations is True, command


def test_other_views_still_take_durations_by_default():
    """Only the mini family flips; other views keep --nodurations as the opt-out."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    for command in ("weekly", "timeline", "blockplan"):
        config = create_calendar_config()
        args = parser.parse_args([command, "20260101", "20260131"])
        ecalendar._apply_args_to_config(args, config, _PAPER_SIZES)
        assert config.includedurations is True, command

        config = create_calendar_config()
        args = parser.parse_args(
            [command, "20260101", "20260131", "--nodurations"]
        )
        ecalendar._apply_args_to_config(args, config, _PAPER_SIZES)
        assert config.includedurations is False, command


def test_the_kept_content_is_events_milestones_holidays_and_specials():
    text = _text_for(False)
    assert "Kickoff" in text          # milestone
    assert "Review" in text           # single-day event
    assert "New Year" in text         # government holiday
    assert "Company Day" in text      # special day
    assert "Long Build" not in text   # multi-day duration


def test_durations_come_back_when_asked_for():
    text = _text_for(True)
    assert "Long Build" in text
    assert "Kickoff" in text


def _symbol_map_for(events, config_overrides=None):
    from visualizers.text_mini.renderer import TextMiniCalendarRenderer

    with tempfile.TemporaryDirectory() as td:
        config = _config_for(td, **(config_overrides or {}))
    renderer = TextMiniCalendarRenderer()
    events_by_day = renderer._index_events_by_day(events)
    return renderer._build_symbol_map(config, events, events_by_day, _FakeDB([]))


def test_symbols_are_assigned_in_ascending_date_order():
    """The query can hand back rows in any order; the symbol cycles must still
    run in calendar order so the first symbol of each list lands on the
    earliest day it applies to."""
    events = [
        {"Start": "20260120", "End": "20260120", "Task_Name": "Late event"},
        {"Start": "20260106", "End": "20260106", "Task_Name": "Early event"},
        {"Start": "20260113", "End": "20260113", "Task_Name": "Mid event"},
        {"Start": "20260122", "End": "20260122",
         "Task_Name": "Late milestone", "Milestone": True},
        {"Start": "20260108", "End": "20260108",
         "Task_Name": "Early milestone", "Milestone": True},
    ]
    symbol_map, details = _symbol_map_for(events)

    config = create_calendar_config()
    first_event, second_event, third_event = config.text_mini_event_symbols[:3]
    first_ms, second_ms = config.text_mini_milestone_symbols[:2]

    assert symbol_map["20260106"] == first_event
    assert symbol_map["20260113"] == second_event
    assert symbol_map["20260120"] == third_event
    assert symbol_map["20260108"] == first_ms
    assert symbol_map["20260122"] == second_ms

    # The details list follows the same order.
    assert [d.text for d in details] == [
        "Early event", "Early milestone", "Mid event",
        "Late event", "Late milestone",
    ]


def test_symbol_order_is_stable_for_events_sharing_a_start_date():
    """End date then name break the tie, so the same input always assigns the
    same symbols."""
    events = [
        {"Start": "20260112", "End": "20260112", "Task_Name": "Beta"},
        {"Start": "20260112", "End": "20260112", "Task_Name": "Alpha"},
    ]
    _, details = _symbol_map_for(events)

    assert [d.text for d in details] == ["Alpha", "Beta"]


def test_holiday_and_nonworkday_symbols_run_in_date_order():
    """These two cycles walk the day range rather than the event list, so they
    are ascending by construction — this pins that."""
    from visualizers.text_mini.renderer import TextMiniCalendarRenderer

    db = _FakeDB(
        [],
        holidays={
            "20260119": [{"displayname": "Later Holiday"}],
            "20260101": [{"displayname": "Earlier Holiday"}],
        },
        specials={
            "20260126": [{"name": "Later Shutdown", "nonworkday": 1}],
            "20260105": [{"name": "Earlier Shutdown", "nonworkday": 1}],
        },
    )
    with tempfile.TemporaryDirectory() as td:
        config = _config_for(td)
    renderer = TextMiniCalendarRenderer()
    symbol_map, details = renderer._build_symbol_map(config, [], {}, db)

    first_hol, second_hol = config.text_mini_holiday_symbols[:2]
    first_nwd, second_nwd = config.text_mini_nonworkday_symbols[:2]

    assert symbol_map["20260101"] == first_hol
    assert symbol_map["20260119"] == second_hol
    assert symbol_map["20260105"] == first_nwd
    assert symbol_map["20260126"] == second_nwd
    assert [d.text for d in details] == [
        "Earlier Holiday", "Earlier Shutdown", "Later Holiday", "Later Shutdown",
    ]


def test_text_mini_accepts_a_theme():
    """run() applies a theme only when args.theme exists, so without --theme on
    the parser text-mini silently ignored every themed value it reads."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    args = parser.parse_args(
        ["text-mini", "20260101", "20260131", "--theme", "dark"]
    )

    assert args.theme == "dark"


def test_text_mini_honors_mini_calendar_show_adjacent():
    """The theme key reaches the renderer, which blanks the leading/trailing
    cells that belong to a neighbouring month."""
    from config.theme_engine import ThemeEngine

    db = _FakeDB([])
    texts = {}
    for show_adjacent in (True, False):
        with tempfile.TemporaryDirectory() as td:
            config = _config_for(td)
            config.userstart = config.adjustedstart = "20260201"
            config.userend = config.adjustedend = "20260228"
            theme = ThemeEngine()
            theme._theme_data = {"mini_calendar": {"show_adjacent": show_adjacent}}
            theme.apply(config)

            assert config.mini_show_adjacent is show_adjacent
            TextMiniCalendarVisualizer().generate(config, db)
            texts[show_adjacent] = Path(config.outputfile).read_text(encoding="utf-8")

    # February 2026 starts on a Sunday, so the first week row carries six days
    # of January when adjacent days are shown and blanks them when not.  Count
    # filled cells rather than matching text: day numbers render as configured
    # glyphs, not ASCII digits.
    first_week_on = texts[True].splitlines()[2].split()
    first_week_off = texts[False].splitlines()[2].split()

    assert len(first_week_on) == 7
    assert len(first_week_off) == 1
    assert first_week_on[-1] == first_week_off[-1]  # Feb 1 either way


def _details_block(text):
    """The lines from the 'Calendar Details' heading to the end."""
    lines = text.splitlines()
    start = lines.index("Calendar Details")
    return [ln for ln in lines[start:] if ln.strip()]


def test_details_are_grouped_under_a_heading_and_per_type_subheadings():
    events = [
        {"Start": "20260106", "End": "20260106", "Task_Name": "Standup"},
        {"Start": "20260108", "End": "20260108",
         "Task_Name": "Kickoff", "Milestone": True},
        {"Start": "20260112", "End": "20260116", "Task_Name": "Build Week"},
    ]
    db = _FakeDB(
        events,
        holidays={"20260101": [{"displayname": "New Year"}]},
        specials={"20260105": [{"name": "Company Day", "nonworkday": 1}]},
    )
    with tempfile.TemporaryDirectory() as td:
        config = _config_for(td, includedurations=True)
        TextMiniCalendarVisualizer().generate(config, db)
        block = _details_block(Path(config.outputfile).read_text(encoding="utf-8"))

    assert block[0] == "Calendar Details"
    subheadings = [ln.strip() for ln in block if not ln.startswith("    ")]
    assert subheadings == [
        "Calendar Details", "Events", "Milestones", "Durations",
        "Holidays", "Non-Working Days",
    ]
    # Each entry sits under its own subheading.
    assert "Standup" in block[block.index("  Events") + 1]
    assert "Kickoff" in block[block.index("  Milestones") + 1]
    assert "Build Week" in block[block.index("  Durations") + 1]
    assert "New Year" in block[block.index("  Holidays") + 1]
    assert "Company Day" in block[block.index("  Non-Working Days") + 1]


def test_empty_detail_sections_are_skipped():
    """A calendar with only holidays prints one subheading, not five."""
    db = _FakeDB([], holidays={"20260101": [{"displayname": "New Year"}]})
    with tempfile.TemporaryDirectory() as td:
        config = _config_for(td)
        TextMiniCalendarVisualizer().generate(config, db)
        block = _details_block(Path(config.outputfile).read_text(encoding="utf-8"))

    subheadings = [ln.strip() for ln in block if not ln.startswith("    ")]
    assert subheadings == ["Calendar Details", "Holidays"]


def test_detail_dates_are_zero_padded_mm_dd():
    events = [
        {"Start": "20260102", "End": "20260102", "Task_Name": "Single"},
        {"Start": "20260105", "End": "20260109", "Task_Name": "Span"},
    ]
    with tempfile.TemporaryDirectory() as td:
        config = _config_for(td, includedurations=True)
        TextMiniCalendarVisualizer().generate(config, db=_FakeDB(events))
        text = Path(config.outputfile).read_text(encoding="utf-8")

    assert "01/02 Single" in text
    assert "01/05 - 01/09 Span" in text
