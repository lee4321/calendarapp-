"""Dependency-string parsing: refs, link types, lag, and refusals.

`parse_links` turns the predecessor/successor text schedule tools export
into structured links.  It is the only place the MS Project grammar is
decided, so the whole grammar is pinned here.
"""

import pytest

from shared.duration_parser import DAYS_PER_WEEK, HOURS_PER_DAY
from shared.predecessors import (
    DEFAULT_LINK_TYPE,
    LINK_TYPES,
    Link,
    parse_links,
    parse_links_with_rejects,
)


# ── Empty input ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", [None, "", "   ", ",", " , ; ", "\n"])
def test_empty_input_yields_no_links(text):
    assert parse_links(text) == []


# ── Bare references ───────────────────────────────────────────────────────


def test_bare_number_is_a_source_id_with_default_type():
    (link,) = parse_links("12")
    assert link == Link(ref="12", type="FS")


def test_numeric_cell_is_accepted():
    """A spreadsheet column typed as a number arrives as an int."""
    (link,) = parse_links(7)
    assert link.ref == "7"
    assert link.type == DEFAULT_LINK_TYPE


def test_guid_reference_survives_intact():
    (link,) = parse_links("A3F2-9C11-4E7B")
    assert link.ref == "A3F2-9C11-4E7B"
    assert link.type == "FS"


# ── Link types ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("link_type", sorted(LINK_TYPES))
def test_every_link_type_parses(link_type):
    (link,) = parse_links(f"12{link_type}")
    assert link.ref == "12"
    assert link.type == link_type


def test_link_type_is_case_insensitive_and_normalized():
    (link,) = parse_links("12ss")
    assert link.type == "SS"


def test_whitespace_inside_a_token_is_ignored():
    (link,) = parse_links("  12 FS + 3 d  ")
    assert link.ref == "12"
    assert link.type == "FS"
    assert link.lag_days == 3.0


# ── Lag ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected_days",
    [
        ("12FS+3d", 3.0),
        ("12FS-3d", -3.0),
        ("12FS+3", 3.0),  # bare number is days
        ("12SS+2w", 2 * DAYS_PER_WEEK),
        ("12FF-4h", -4 / HOURS_PER_DAY),
        ("12SF+0.5d", 0.5),
    ],
)
def test_lag_magnitude_and_sign(text, expected_days):
    (link,) = parse_links(text)
    assert link.lag_days == pytest.approx(expected_days)
    assert link.lag_percent is None


def test_lag_text_is_preserved_as_written():
    (link,) = parse_links("12FS+3d")
    assert link.lag_text == "+3d"


def test_percentage_lag_is_kept_separate_from_days():
    (link,) = parse_links("12FS+50%")
    assert link.lag_percent == 50.0
    assert link.lag_days == 0.0


def test_negative_percentage_lag():
    (link,) = parse_links("12FS-25%")
    assert link.lag_percent == -25.0


@pytest.mark.parametrize("text,days", [("12FS+3ed", 3.0), ("12FS-2ew", -2 * DAYS_PER_WEEK)])
def test_elapsed_lag_is_flagged(text, days):
    (link,) = parse_links(text)
    assert link.lag_elapsed is True
    assert link.lag_days == pytest.approx(days)


def test_absent_lag_is_zero_and_untagged():
    (link,) = parse_links("12FS")
    assert link.lag_days == 0.0
    assert link.lag_percent is None
    assert link.lag_elapsed is False
    assert link.lag_text is None


# ── Lists ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("separator", [",", ";", "\n"])
def test_all_list_separators(separator):
    links = parse_links(separator.join(["3", "7FS+2d", "9SS"]))
    assert [link.ref for link in links] == ["3", "7", "9"]
    assert [link.type for link in links] == ["FS", "FS", "SS"]


def test_written_order_and_duplicates_are_preserved():
    links = parse_links("9,3,9")
    assert [link.ref for link in links] == ["9", "3", "9"]


def test_decimal_comma_lag_splits_the_documented_way():
    """The comma is always a separator, so "+1,5d" becomes "+1" and "5d".

    Pinning the documented limitation: the surviving "5d" is a reference
    that will simply not resolve to any task, which the details page
    reports at resolution time rather than here.
    """
    links, rejected = parse_links_with_rejects("3FS+1,5d;7")
    assert [link.ref for link in links] == ["3", "5d", "7"]
    assert links[0].lag_days == 1.0
    assert rejected == []


# ── Refusals ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["FS", "SS", "+3d"])
def test_tokens_without_a_reference_are_rejected(text):
    links, rejected = parse_links_with_rejects(text)
    assert links == []
    assert rejected == [text]


def test_unparseable_lag_keeps_the_link_and_reports_the_token():
    links, rejected = parse_links_with_rejects("12FS+about a week")
    (link,) = links
    assert link.ref == "12"
    assert link.type == "FS"
    assert link.lag_days == 0.0
    # Whitespace is stripped before matching, so the kept text is compacted.
    assert link.lag_text == "+aboutaweek"
    assert rejected == ["12FS+about a week"]


def test_good_tokens_survive_a_bad_neighbour():
    links, rejected = parse_links_with_rejects("3,FS,9FF-2d")
    assert [link.ref for link in links] == ["3", "9"]
    assert rejected == ["FS"]


def test_parse_links_drops_what_the_verbose_form_reports():
    assert parse_links("3,FS,9") == [
        link for link in parse_links_with_rejects("3,FS,9")[0]
    ]
