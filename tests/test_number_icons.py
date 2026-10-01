"""Numbered duration icons: the shared replacement every view can switch on."""

from __future__ import annotations

import pytest
from band_helpers import set_fields
from fakes import FakeCalendarDB

from config.config import ICON_SETS, create_calendar_config
from shared.data_models import Event
from shared.number_icons import number_duration_icons
from visualizers.factory import VisualizerFactory


def _dur(name: str, start: str, end: str, icon: str | None = "star") -> dict:
    return {"Task_Name": name, "Start": start, "End": end, "Icon": icon}


def _config(**overrides):
    config = create_calendar_config()
    set_fields(config, **overrides)
    return config


def test_a_view_with_numbering_off_keeps_its_events_icons():
    events = [_dur("A", "20260309", "20260313")]
    config = _config(weekly_number_duration_icons=False)

    assert number_duration_icons(events, config, "weekly") is events


def test_durations_are_numbered_in_placement_order_and_replace_the_event_icon():
    events = [_dur("B", "20260316", "20260320"), _dur("A", "20260309", "20260313"), _dur("Day", "20260310", "20260310")]
    config = _config(timeline_number_duration_icons=True, item_placement_order=["start_date"])

    out = number_duration_icons(events, config, "timeline")

    icons = ICON_SETS["darksquare"]
    assert out[1]["Icon"] == icons[0]  # A starts first
    assert out[0]["Icon"] == icons[1]
    assert out[2]["Icon"] == "star"  # a single-day event keeps its own
    assert events[0]["Icon"] == "star"  # inputs are not mutated


def test_milestones_are_not_numbered():
    milestone = {**_dur("M", "20260309", "20260313"), "Milestone": 1}
    config = _config(blockplan_number_duration_icons=True)

    assert number_duration_icons([milestone], config, "blockplan")[0]["Icon"] == "star"


def test_numbers_cycle_and_follow_the_configured_list():
    events = [_dur(f"T{n:02d}", f"202603{n + 1:02d}", f"202603{n + 2:02d}") for n in range(1, 4)]
    config = _config(
        gantt_number_duration_icons=True, duration_icon_list="circles", item_placement_order=["start_date"]
    )

    out = number_duration_icons(events, config, "gantt")

    assert [e["Icon"] for e in out] == ICON_SETS["circles"][:3]


def test_event_objects_are_replaced_not_mutated():
    event = Event(task_name="A", start="20260309", end="20260313", icon="star")
    config = _config(pit_number_duration_icons=True)

    (out,) = number_duration_icons([event], config, "pit")

    assert out.icon == ICON_SETS["darksquare"][0]
    assert event.icon == "star"


@pytest.mark.parametrize("view", ["weekly", "timeline", "blockplan", "gantt", "compactplan", "pit", "mini", "candybar"])
def test_the_visualizer_numbers_its_events(view, monkeypatch):
    config = _config()
    visualizer = VisualizerFactory.create(view)

    class _DB(FakeCalendarDB):
        def get_all_events_in_range(self, start: str, end: str) -> list[dict]:
            return [_dur("A", "20260309", "20260313")]

    monkeypatch.setattr("visualizers.base.filter_events", lambda events, _c: events)
    (event,) = visualizer._prepare_data(config, _DB())

    assert event["Icon"] == ICON_SETS["darksquare"][0]


def test_numbering_is_on_by_default_and_one_switch_turns_it_off():
    config = create_calendar_config()
    assert config.theme_v3.durations.replace_icons_with_numbers is True

    set_fields(config, weekly_number_duration_icons=False)
    events = [_dur("A", "20260309", "20260313")]
    assert number_duration_icons(events, config, "weekly") is events


def test_the_original_icon_is_kept_beside_the_number():
    events = [_dur("A", "20260309", "20260313"), _dur("B", "20260316", "20260320", icon=None)]
    config = _config(weekly_number_duration_icons=True, item_placement_order=["start_date"])

    a, b = number_duration_icons(events, config, "weekly")

    assert (a["Original_Icon"], b["Original_Icon"]) == ("star", "")
    assert Event.from_dict(a).original_icon == "star"


def test_the_details_record_and_csv_report_the_event_data_icon():
    from renderers.details_record import DetailsRecord
    from renderers.event_csv import build_event_csv

    config = _config(weekly_number_duration_icons=True)
    (event,) = number_duration_icons([_dur("A", "20260309", "20260313")], config, "weekly")
    record = DetailsRecord("weekly", [event])

    (note,) = record.events
    assert note.raw["Icon"] == "star"  # the re-importable row keeps the data
    assert note.event.icon == ICON_SETS["darksquare"][0]

    import csv
    import io

    (row,) = csv.DictReader(io.StringIO(build_event_csv(record, config)))
    assert (row["icon"], row["original_icon"], row["icons"]) == ("star", "star", "")
