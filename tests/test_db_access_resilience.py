import sqlite3

from shared.db_access import CalendarDB


def _make_db_without_companyspecialdays(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.commit()
    conn.close()


def test_get_special_days_returns_empty_when_company_table_missing(tmp_path):
    db_path = str(tmp_path / "missing_company.sqlite")
    _make_db_without_companyspecialdays(db_path)
    db = CalendarDB(db_path)

    assert db.get_special_days_for_date("20260101") == []


def test_is_nonworkday_uses_python_holidays(tmp_path):
    db_path = str(tmp_path / "no_gov.sqlite")
    _make_db_without_companyspecialdays(db_path)
    db = CalendarDB(db_path)
    # Manually inject a holiday into the in-memory store
    db._python_holidays = {
        "20260101": [
            {"displayname": "New Year", "icon": "us", "nonworkday": 1, "country": "US"}
        ]
    }

    assert db.is_nonworkday("20260101", "US") is True
    assert db.is_nonworkday("20260102", "US") is False


def test_get_holiday_title_uses_in_memory_holidays(tmp_path):
    db_path = str(tmp_path / "holiday_title.sqlite")
    _make_db_without_companyspecialdays(db_path)
    db = CalendarDB(db_path)
    db._python_holidays = {
        "20260101": [
            {"displayname": "Holiday", "icon": "star", "nonworkday": 1, "country": "US"}
        ]
    }

    title, icon = db.get_holiday_title_for_date("20260101", "US")
    assert title == "Holiday"
    assert icon == "star"


def test_get_holiday_title_resolves_numeric_icon_id_via_fonticon(tmp_path):
    db_path = str(tmp_path / "holiday_icon_id.sqlite")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE fonticon (id INTEGER PRIMARY KEY, name TEXT)")
    cur.execute("INSERT INTO fonticon (id, name) VALUES (42, 'calendar')")
    conn.commit()
    conn.close()

    db = CalendarDB(db_path)
    db._python_holidays = {
        "20260101": [
            {"displayname": "Holiday", "icon": "42", "nonworkday": 1, "country": "US"}
        ]
    }

    title, icon = db.get_holiday_title_for_date("20260101", "US")
    assert title == "Holiday"
    assert icon == "calendar"
