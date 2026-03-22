from __future__ import annotations

import sqlite3
from pathlib import Path

import ecalendar
from config.config import create_calendar_config


def _create_icons_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE icon (
                filename TEXT NOT NULL,
                name TEXT NOT NULL,
                alternativenames TEXT,
                svg TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO icon (filename, name, alternativenames, svg) VALUES (?, ?, ?, ?)",
            ("rocket.svg", "rocket", "launch,ship", '<svg viewBox="0 0 24 24"></svg>'),
        )
        conn.execute(
            "INSERT INTO icon (filename, name, alternativenames, svg) VALUES (?, ?, ?, ?)",
            ("star.svg", "star", "", '<svg viewBox="0 0 24 24"></svg>'),
        )
        conn.commit()
    finally:
        conn.close()


def _create_colors_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE colors (
                EN TEXT NOT NULL,
                red INTEGER NOT NULL,
                green INTEGER NOT NULL,
                blue INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO colors (EN, red, green, blue) VALUES (?, ?, ?, ?)",
            ("DarkSlateGrey", 47, 79, 79),
        )
        conn.execute(
            "INSERT INTO colors (EN, red, green, blue) VALUES (?, ?, ?, ?)",
            ("Tomato", 255, 99, 71),
        )
        conn.commit()
    finally:
        conn.close()


def test_icons_subcommand_lists_icons_from_database(tmp_path, capsys):
    db_path = tmp_path / "calendar.db"
    _create_icons_db(db_path)

    rc = ecalendar.run(["ecalendar.py", "icons", "--database", str(db_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Available SVG icons (2):" in out
    assert "rocket" in out
    assert "star" in out
    assert "file=" not in out


def test_colors_subcommand_lists_en_name_and_rgb(tmp_path, capsys):
    db_path = tmp_path / "calendar.db"
    _create_colors_db(db_path)

    rc = ecalendar.run(["ecalendar.py", "colors", "--database", str(db_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Available colors (2):" in out
    assert "DarkSlateGrey" in out
    assert "(47,79,79)" in out
    assert "Tomato" in out
    assert "(255,99,71)" in out


def test_help_weekly_references_icons_subcommand(capsys):
    rc = ecalendar.run(["ecalendar.py", "help", "weekly"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "ecalendar.py icons --database" in out
    assert "Fonts (used in themes and config/config.py):" not in out
    assert "(Use 'ecalendar.py fonts' for a full list.)" in out
    assert "(Use 'ecalendar.py colors' for a full list.)" in out


def test_fonts_subcommand_lists_registered_fonts(capsys):
    rc = ecalendar.run(["ecalendar.py", "fonts"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Available fonts (" in out
    assert "Roboto-Regular" in out


def test_weekly_parser_accepts_watermark_rotation_angle():
    parser = ecalendar._create_argument_parser("calendar.svg")
    args = parser.parse_args(
        [
            "weekly",
            "20260101",
            "20260131",
            "--watermark-rotation-angle",
            "22.5",
        ]
    )
    assert args.watermark_rotation_angle == 22.5


def test_apply_text_options_sets_watermark_rotation_angle():
    parser = ecalendar._create_argument_parser("calendar.svg")
    args = parser.parse_args(
        [
            "weekly",
            "20260101",
            "20260131",
            "--watermark",
            "WM",
            "--watermark-rotation-angle",
            "-15",
        ]
    )
    config = create_calendar_config()
    ecalendar._apply_text_options(args, config)

    assert config.watermark == "WM"
    assert config.watermark_rotation_angle == -15.0


def test_parse_atfile_lines_strips_comments_and_preserves_hash_numbers(tmp_path):
    atfile = tmp_path / "weekly_args.txt"
    atfile.write_text(
        "\n".join(
            [
                "",
                "# full line comment",
                "--watermark=Build # 42",
                "--headerleft=Sprint#2",
                "--footerleft=Release #1",
                "weekly # inline comment",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    lines = ecalendar._parse_atfile_lines(str(atfile))

    assert "--watermark=Build" in lines
    assert "--headerleft=Sprint#2" in lines
    assert "--footerleft=Release #1" in lines
    assert "weekly" in lines
    assert "# full line comment" not in lines


def test_run_sanitizes_atfiles_by_default(tmp_path, capsys):
    atfile = tmp_path / "help_args_default.txt"
    atfile.write_text(
        "\n".join(
            [
                "# comment",
                "weekly # help target",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rc = ecalendar.run(["ecalendar.py", "help", f"@{atfile}"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "usage: EventCalendar v9 weekly" in out


def test_to_output_dir_path_forces_output_folder():
    assert ecalendar._to_output_dir_path("calendar.svg") == "output/calendar.svg"
    assert ecalendar._to_output_dir_path("nested/path/out.svg") == "output/out.svg"


def test_blockplan_parser_accepts_dates():
    parser = ecalendar._create_argument_parser("calendar.svg")
    args = parser.parse_args(["blockplan", "20260101", "20260131"])
    assert args.command == "blockplan"
    assert args.begin == "20260101"
    assert args.end == "20260131"


def test_help_blockplan_shows_usage(capsys):
    rc = ecalendar.run(["ecalendar.py", "help", "blockplan"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "usage: EventCalendar v9 blockplan" in out
