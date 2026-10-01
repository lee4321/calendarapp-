"""The glyphs table: created and seeded by tools/db/create_glyphs.py, never by the program."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from cli.errors import DatabaseError, GlyphsTableMissingError
from shared.db_access import CalendarDB
from tools.db.create_glyphs import DEFAULT_SEED, create_glyphs, load_seed

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def bare_db(tmp_path):
    """A database with no glyphs table."""
    path = tmp_path / "bare.db"
    sqlite3.connect(path).close()
    return path


class TestScript:
    def test_creates_the_table_and_loads_the_seed(self, bare_db):
        groups, glyphs = create_glyphs(bare_db, {"a": ["x", "y"], "b": ["z"]})
        assert (groups, glyphs) == (2, 3)
        db = CalendarDB(str(bare_db))
        assert db.get_glyphs("a") == ["x", "y"]
        assert db.list_glyph_groups() == {"a": 2, "b": 1}

    def test_rerun_replaces_a_group_and_leaves_others_alone(self, bare_db):
        create_glyphs(bare_db, {"a": ["x", "y"], "mine": ["m"]})
        create_glyphs(bare_db, {"a": ["q"]})
        db = CalendarDB(str(bare_db))
        assert db.get_glyphs("a") == ["q"]
        assert db.get_glyphs("mine") == ["m"]

    def test_order_is_seq_order(self, bare_db):
        create_glyphs(bare_db, {"digits": list("9876543210")})
        assert CalendarDB(str(bare_db)).get_glyphs("digits") == list("9876543210")

    def test_the_shipped_seed_is_well_formed(self):
        seed = load_seed(DEFAULT_SEED)
        assert len(seed["day-circled"]) == 31
        assert len(seed["digits-ascii"]) == 10
        assert all(len(seed[g]) == 10 for g in ("digits-superscript", "digits-seven-segment"))

    @pytest.mark.parametrize("bad", [[], {"g": []}, {"g": [""]}, {"g": "abc"}])
    def test_a_malformed_seed_is_rejected(self, tmp_path, bad):
        path = tmp_path / "seed.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            load_seed(path)

    def test_runs_from_the_command_line(self, bare_db):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "db" / "create_glyphs.py"), "--database", str(bare_db)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "10 groups" in result.stdout

    def test_a_missing_database_is_an_error_not_a_new_file(self, tmp_path):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "db" / "create_glyphs.py"), "--database", str(tmp_path / "nope.db")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert not (tmp_path / "nope.db").exists()


class TestProgramNeverCreatesTheTable:
    def test_missing_table_stops_with_the_fix(self, bare_db):
        db = CalendarDB(str(bare_db))
        with pytest.raises(GlyphsTableMissingError, match=r"create_glyphs\.py --database .*bare\.db"):
            db.get_glyphs("anything")
        with pytest.raises(DatabaseError):
            db.list_glyph_groups()
        tables = {r[0] for r in sqlite3.connect(bare_db).execute("SELECT name FROM sqlite_master")}
        assert "glyphs" not in tables

    def test_unknown_group_lists_the_groups_that_exist(self, bare_db):
        create_glyphs(bare_db, {"alpha": ["a"], "beta": ["b"]})
        with pytest.raises(KeyError, match="'nope' not found; groups in the database: alpha, beta"):
            CalendarDB(str(bare_db)).get_glyphs("nope")


def test_test_databases_carry_the_glyph_groups(temp_calendar_db):
    assert "text-mini-event" in CalendarDB(str(temp_calendar_db)).list_glyph_groups()
