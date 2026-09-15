"""Government holidays carry their country code in every detail listing.

A calendar can load several countries at once (--country US,CA,UA), and the
countries share holiday *names* — 1 January is "New Year's Day" in both the US
and Canada — so a listing without the code cannot say whose holiday a row
describes.  Company special days come from the specialdays table, carry no
country, and are never prefixed.
"""

from datetime import date, timedelta

import pytest
from fakes import FakeCalendarDB

from config.config import create_calendar_config, setfontsizes
from shared.holiday_labels import format_holiday_label


class _StubDB(FakeCalendarDB):
    """Holidays keyed by daykey; special days likewise."""

    def __init__(self, holidays=None, specials=None):
        self._holidays = holidays or {}
        self._specials = specials or {}

    def get_holidays_for_date(self, daykey, country=None):
        return list(self._holidays.get(daykey, []))

    def get_special_days_for_date(self, daykey):
        return list(self._specials.get(daykey, []))


_HOLIDAYS = {
    "20260715": [{"displayname": "Ukrainian Statehood Day", "country": "UA"}],
    "20260704": [{"displayname": "Independence Day", "country": "US"}],
}
_SPECIALS = {"20260710": [{"name": "Company Picnic", "nonworkday": 1}]}


def _config():
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 612.0
    config = setfontsizes(config)
    config.userstart = config.adjustedstart = "20260701"
    config.userend = config.adjustedend = "20260731"
    return config


@pytest.mark.parametrize(
    "name, country, expected",
    [
        ("Ukrainian Statehood Day", "UA", "UA - Ukrainian Statehood Day"),
        ("New Year's Day", "CA, US", "CA, US - New Year's Day"),
        ("Company Picnic", None, "Company Picnic"),
        ("Company Picnic", "", "Company Picnic"),
        ("  Padded  ", " US ", "US - Padded"),
        ("", "US", ""),
    ],
)
def test_format_holiday_label(name, country, expected):
    assert format_holiday_label(name, country) == expected


def test_text_mini_details_carry_the_country_code():
    from visualizers.text_mini.renderer import TextMiniCalendarRenderer

    config = _config()
    db = _StubDB(_HOLIDAYS, _SPECIALS)
    _, details = TextMiniCalendarRenderer()._build_symbol_map(config, [], {}, db)
    by_text = {d.category: [e.text for e in details if e.category == d.category] for d in details}

    assert "UA - Ukrainian Statehood Day" in by_text["holiday"]
    assert "US - Independence Day" in by_text["holiday"]
    # A company special day is not a government holiday.
    assert by_text["nonworkday"] == ["Company Picnic"]


def test_holiday_rows_carry_the_country_code():
    from shared.holiday_listing import holiday_special_rows

    config = _config()
    config.country = "US,UA"
    daykeys = [f"202607{d:02d}" for d in range(1, 32)]
    rows = holiday_special_rows(daykeys, config, _StubDB(_HOLIDAYS, _SPECIALS))
    named = {r["name"]: r for r in rows}

    assert "UA - Ukrainian Statehood Day" in named
    assert "US - Independence Day" in named
    assert named["Company Picnic"]["kind"] == "Special Day"
    assert named["US - Independence Day"]["country"] == "US"


def test_holiday_rows_collapse_a_shared_name_onto_one_row():
    """The listing keys on the name, so a holiday both countries celebrate
    under the same name lists both codes rather than losing one."""
    from shared.holiday_listing import holiday_special_rows

    config = _config()
    config.country = "US,CA"
    db = _StubDB(
        {
            "20260701": [
                {"displayname": "New Year's Day", "country": "CA"},
                {"displayname": "New Year's Day", "country": "US"},
            ]
        }
    )
    rows = holiday_special_rows(["20260701"], config, db)

    assert [r["name"] for r in rows] == ["CA, US - New Year's Day"]
    assert rows[0]["raw_name"] == "New Year's Day"


def test_the_details_document_lists_holidays_with_their_country_code(tmp_path):
    from renderers.details_record import DetailsRecord
    from renderers.markdown_details import build_markdown
    from shared.holiday_listing import holiday_special_rows
    from shared.run_paths import RunPaths

    config = _config()
    config.country = "US,UA"
    days = [date(2026, 7, 1) + timedelta(days=i) for i in range(31)]
    rows = holiday_special_rows((d.strftime("%Y%m%d") for d in days), config, _StubDB(_HOLIDAYS, _SPECIALS))
    text = build_markdown(DetailsRecord("mini"), config, RunPaths.for_output("c.svg", root=tmp_path), rows, {})

    assert "UA - Ukrainian Statehood Day" in text
    assert "US - Independence Day" in text
    assert "Company Picnic" in text
