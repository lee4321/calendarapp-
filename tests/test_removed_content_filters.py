"""The --ignorecomplete and --rollups content filters no longer exist.

No view registers either flag, CalendarConfig has no field for them, and the
shared filter keeps items regardless of completion or rollup status.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from cli.args import _create_argument_parser
from config.config import CalendarConfig
from visualizers.base import filter_events

# Every command that used to accept the two flags.
_FILTER_VIEWS = (
    "blockplan", "candybar", "compactplan", "excelblockplan", "exportdata",
    "gantt", "mini", "mini-icon", "pit", "text-mini", "timeline", "weekly",
)


@pytest.mark.parametrize("view", _FILTER_VIEWS)
@pytest.mark.parametrize("flag", ["--ignorecomplete", "--rollups"])
def test_views_reject_the_removed_flags(view, flag, capsys):
    parser = _create_argument_parser("out.svg")
    argv = [view, "20260101", "20260131"]
    parser.parse_args(argv)  # the view itself still parses without the flag
    with pytest.raises(SystemExit):
        parser.parse_args([*argv, flag])
    assert flag in capsys.readouterr().err


def test_config_has_no_fields_for_the_removed_filters():
    names = {f.name for f in fields(CalendarConfig)}
    assert not names & {"ignorecomplete", "rollups"}


def test_filter_keeps_complete_and_non_rollup_items():
    events = [
        {"Task_Name": "Done", "Start": "20260105", "End": "20260105",
         "Percent_Complete": 1},
        {"Task_Name": "Summary", "Start": "20260105", "End": "20260109",
         "Rollup": 1},
        {"Task_Name": "Plain", "Start": "20260106", "End": "20260106"},
    ]
    kept = filter_events(events, CalendarConfig())
    assert [ev["Task_Name"] for ev in kept] == ["Done", "Summary", "Plain"]
