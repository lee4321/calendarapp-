"""Column mapping and value coercion for the schedule data elements.

Covers the vocabulary from ScheduleDataElements: that every documented
column name resolves to the right database column, and that each value
type lands in the right shape.
"""

import pytest

from importers.import_events import lookup_column, transform_row


def _row(**overrides) -> dict:
    """A minimal valid source row, plus whatever the test overrides."""
    base = {"Name": "Ditch", "Start": "20260602T1230", "Finish": "20260602T1630"}
    base.update(overrides)
    return base


def _transform(**overrides) -> dict:
    event, error = transform_row(_row(**overrides), user_id=1, import_id=1, event_id=1)
    assert error is None, error
    return event


# --------------------------------------------------------------- mapping


@pytest.mark.parametrize(
    "source_name,db_column",
    [
        ("ID", "source_id"),
        ("Name", "name"),
        ("WBS", "wbs"),
        ("Priority", "priority"),
        ("Milestone", "milestone"),
        ("Summary", "rollup"),
        ("Critical", "critical"),
        ("Start", "start_date"),
        ("Finish", "end_date"),
        ("Duration", "duration"),
        ("Work", "effort"),
        ("EarlyStart", "earliest_start_date"),
        ("EarlyFinish", "earliest_end_date"),
        ("LateStart", "latest_start_date"),
        ("LateFinish", "latest_end_date"),
        ("ActualStart", "actual_start_date"),
        ("ActualFinish", "actual_end_date"),
        ("Deadline", "deadline"),
        ("StartVariance", "start_variance"),
        ("FinishVariance", "finish_variance"),
        ("FixedCost", "fixed_cost"),
        ("PercentComplete", "percent_complete"),
        ("PercentWorkComplete", "percent_work_complete"),
        ("Cost", "cost"),
        ("Notes", "notes"),
        ("Resources", "resource_names"),
        ("ResourceGroups", "resource_group"),
        ("Predecessors", "predecessors"),
        ("Successors", "successors"),
        ("Icon", "icon"),
        ("Color", "color"),
        ("Tags", "tags"),
        ("Custom1", "custom1"),
        ("Custom5", "custom5"),
    ],
)
def test_every_documented_column_maps(source_name, db_column):
    assert lookup_column(source_name) == db_column


@pytest.mark.parametrize(
    "spelling", ["EarlyStart", "early_start", "Early Start", "earlystart", "EARLY-START"]
)
def test_spelling_variants_collapse(spelling):
    """Case, spaces, underscores and hyphens are all ignored."""
    assert lookup_column(spelling) == "earliest_start_date"


def test_summary_is_rollup_not_name():
    """Regression: Summary once mapped to the task name, silently
    overwriting it.  In the schedule vocabulary Summary is the rollup."""
    assert lookup_column("Summary") == "rollup"
    event = _transform(Summary="True")
    assert event["rollup"] == 1
    assert event["name"] == "Ditch"


def test_alternative_names_from_the_spec_map():
    assert lookup_column("GUID") == "source_id"
    assert lookup_column("TaskName") == "name"
    assert lookup_column("StartDate") == "start_date"
    assert lookup_column("EndDate") == "end_date"
    assert lookup_column("Effort") == "effort"
    assert lookup_column("resource_names") == "resource_names"
    assert lookup_column("resource_groups") == "resource_group"


def test_unknown_columns_are_ignored():
    assert lookup_column("SomeVendorField") is None
    event = _transform(SomeVendorField="x")
    assert "SomeVendorField" not in event


# ------------------------------------------------------------ date/time


def test_datetime_splits_into_date_and_time():
    event = _transform()
    assert event["start_date"] == "20260602"
    assert event["start_time"] == "1230"
    assert event["end_date"] == "20260602"
    assert event["end_time"] == "1630"


@pytest.mark.parametrize(
    "value,expected_time",
    [
        ("20260602T1230", "1230"),
        ("20260602T12:30", "1230"),  # the spec's own prose uses a colon
        ("2026-06-02 12:30", "1230"),
        ("6/2/2026 12:30 PM", "1230"),
    ],
)
def test_accepted_datetime_forms(value, expected_time):
    event = _transform(Start=value)
    assert event["start_date"] == "20260602"
    assert event["start_time"] == expected_time


@pytest.mark.parametrize("value", ["20260602", "2026-06-02", "6/2/2026"])
def test_date_without_time_leaves_time_null(value):
    """Midnight and 'no time given' must stay distinguishable."""
    event = _transform(Start=value)
    assert event["start_date"] == "20260602"
    assert event["start_time"] is None


def test_actual_dates_keep_their_time():
    event = _transform(ActualStart="20260602T0800", ActualFinish="20260602T1200")
    assert event["actual_start_date"] == "20260602"
    assert event["actual_start_time"] == "0800"
    assert event["actual_end_date"] == "20260602"
    assert event["actual_end_time"] == "1200"


def test_schedule_window_dates_are_date_only():
    event = _transform(EarlyStart="20260523T0800", Deadline="20260630")
    assert event["earliest_start_date"] == "20260523"
    assert event["deadline"] == "20260630"


def test_reversed_dates_are_swapped():
    event = _transform(Start="20260610", Finish="20260602")
    assert event["start_date"] == "20260602"
    assert event["end_date"] == "20260610"


def test_missing_one_date_copies_the_other():
    event = _transform(Start=None, Finish="20260602T1630")
    assert event["start_date"] == "20260602"
    assert event["end_date"] == "20260602"
    assert event["start_time"] == "1630"


def test_row_without_any_date_fails():
    _event, error = transform_row(
        {"Name": "Ditch"}, user_id=1, import_id=1, event_id=1
    )
    assert error == "Invalid or missing dates"


def test_row_without_name_fails():
    _event, error = transform_row(
        {"Start": "20260602"}, user_id=1, import_id=1, event_id=1
    )
    assert error == "Task_Name is required"


# -------------------------------------------------------------- numbers


def test_duration_keeps_text_and_stores_decimal_days():
    event = _transform(Duration="4hr", Work="0.5d")
    assert event["duration_text"] == "4hr"
    assert event["duration"] == pytest.approx(0.5)
    assert event["effort_text"] == "0.5d"
    assert event["effort"] == pytest.approx(0.5)


def test_unparseable_duration_keeps_text_and_nulls_the_number():
    event = _transform(Duration="TBD")
    assert event["duration_text"] == "TBD"
    assert event["duration"] is None


@pytest.mark.parametrize(
    "value,expected", [("True", 1), ("False", 0), ("1", 1), ("0", 0), ("Yes", 1), ("N", 0), ("", 0)]
)
def test_boolean_columns(value, expected):
    event = _transform(Milestone=value, Critical=value, Summary=value)
    assert event["milestone"] == expected
    assert event["critical"] == expected
    assert event["rollup"] == expected


@pytest.mark.parametrize(
    "value,expected", [("1.0", 1.0), ("0.85", 0.85), ("85", 0.85), ("100", 1.0), ("0", 0.0), ("", 0.0)]
)
def test_percent_accepts_both_conventions(value, expected):
    event = _transform(PercentComplete=value, PercentWorkComplete=value)
    assert event["percent_complete"] == pytest.approx(expected)
    assert event["percent_work_complete"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "value,expected",
    [("250.00", 250.0), ("$250.00", 250.0), ("1,200", 1200.0), ("(500)", -500.0), ("", None)],
)
def test_currency_columns(value, expected):
    event = _transform(Cost=value, FixedCost=value)
    assert event["cost"] == expected
    assert event["fixed_cost"] == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1,5", 1.5),  # decimal comma, not fifteen
        ("1,50", 1.5),
        ("1,200", 1200.0),  # thousands separator
        ("$1,234.56", 1234.56),  # anglo
        ("1.234,56", 1234.56),  # european
        ("€1.234,56", 1234.56),
        ("(1,5)", -1.5),
    ],
)
def test_currency_respects_decimal_commas(value, expected):
    """Currency shares the duration parser's separator rule."""
    event = _transform(Cost=value)
    assert event["cost"] == pytest.approx(expected)


def test_priority_defaults_to_zero_when_blank():
    assert _transform(Priority="")["priority"] == 0
    assert _transform(Priority="77")["priority"] == 77


# ----------------------------------------------------------------- text


def test_numeric_looking_text_keeps_no_trailing_decimal():
    """pandas types these columns float64; '258.0' would corrupt the ref."""
    event = _transform(ID=143.0, Predecessors=123.0, Successors=258.0, WBS=1.0)
    assert event["source_id"] == "143"
    assert event["predecessors"] == "123"
    assert event["successors"] == "258"
    assert event["wbs"] == "1"


def test_custom_fields_and_lists_pass_through():
    event = _transform(
        Resources="Pete, Garcia",
        ResourceGroups="Facilities",
        Tags="Construction, Grounds",
        Custom1="Equipment: $250.00",
        Custom3="CoA: 99345B2026",
    )
    assert event["resource_names"] == "Pete, Garcia"
    assert event["resource_group"] == "Facilities"
    assert event["tags"] == "Construction, Grounds"
    assert event["custom1"] == "Equipment: $250.00"
    assert event["custom3"] == "CoA: 99345B2026"


def test_status_defaults_to_active():
    assert _transform()["status"] == "active"
    assert _transform(Status="draft")["status"] == "draft"
