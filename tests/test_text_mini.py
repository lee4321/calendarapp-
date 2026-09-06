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


def test_text_mini_no_longer_offers_nodurations():
    """The opt-out is gone: it would only restate the default."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["text-mini", "20260101", "20260131", "--nodurations"]
        )


def test_other_views_still_take_durations_by_default():
    """Only text-mini flips; the SVG views keep --nodurations as the opt-out."""
    parser = ecalendar._create_argument_parser("calendar.svg")
    for command in ("weekly", "mini", "timeline"):
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
