from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

import ecalendar
from cli.errors import ConfigError
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
            "--watermark-text",
            "WM",
            "--watermark-rotation-angle",
            "-15",
        ]
    )
    config = create_calendar_config()
    ecalendar._apply_text_options(args, config)

    assert config.watermark_text == "WM"
    assert config.watermark_rotation_angle == -15.0


def test_parse_atfile_lines_strips_comments_and_preserves_hash_numbers(tmp_path):
    atfile = tmp_path / "weekly_args.txt"
    atfile.write_text(
        "\n".join(
            [
                "",
                "# full line comment",
                "--watermark-text=Build # 42",
                "--headerleft=Sprint#2",
                "--footerleft=Release #1",
                "weekly # inline comment",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    lines = ecalendar._parse_atfile_lines(str(atfile))

    assert "--watermark-text=Build" in lines
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
    assert "usage: EventCalendar weekly" in out


def test_to_output_dir_path_forces_output_folder():
    assert ecalendar._to_output_dir_path("calendar.svg") == "output/calendar.svg"
    assert ecalendar._to_output_dir_path("nested/path/out.svg") == "output/out.svg"


def test_to_output_dir_path_rejects_a_pathname_with_no_basename():
    """``-of .`` used to collapse to the bare directory name ``output``.

    Callers append a suffix to build the companion details page, so that
    yielded ``output_details.svg`` in the working directory — outside
    ``output/`` — written before the chart save failed on the directory.
    """
    for pathname in (".", "..", "/", "   "):
        with pytest.raises(ConfigError):
            ecalendar._to_output_dir_path(pathname)


def test_to_run_paths_gives_each_run_its_own_folder():
    paths = ecalendar._to_run_paths("nested/path/chart.svg")
    assert paths.folder == Path("output/chart")
    assert paths.main == Path("output/chart/chart.svg")
    assert paths.page(1) == paths.main
    assert paths.page(2) == Path("output/chart/chart_p2.svg")
    assert paths.markdown == Path("output/chart/chart.md")
    assert paths.csv == Path("output/chart/chart.csv")
    assert paths.icons_dir == Path("output/chart/icons")
    assert paths.icon("../../escape.svg") == Path("output/chart/icons/escape.svg")


def test_to_run_paths_rejects_a_pathname_with_no_basename():
    for pathname in (".", "..", "/", "   "):
        with pytest.raises(ConfigError):
            ecalendar._to_run_paths(pathname)


def test_run_paths_prepare_clears_only_what_a_run_writes(tmp_path):
    from shared.run_paths import RunPaths

    paths = RunPaths.for_output("chart.svg", root=tmp_path)
    (paths.folder / "icons").mkdir(parents=True)
    for name in (
        "chart.svg",
        "chart_p3.svg",
        "chart.md",
        "chart.csv",
        "chart_details.svg",
        "icons/x.svg",
        "notes.txt",
        "chart_backup.svg",
    ):
        (paths.folder / name).write_text("x")

    paths.prepare()

    assert sorted(p.name for p in paths.folder.rglob("*")) == ["chart_backup.svg", "notes.txt"]


def test_slugify_keeps_icon_filenames_safe():
    from shared.run_paths import slugify

    assert slugify("../Arrow Bar/Right!") == "arrow-bar-right"
    assert slugify("   ") == "icon"


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
    assert "usage: EventCalendar blockplan" in out


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))


def test_top_level_help_lists_subcommands_alphabetically():
    parser = ecalendar._create_argument_parser("calendar.svg")
    names = list(_subparsers_action(parser).choices)
    help_text = parser.format_help()

    # One line per subcommand, indented four spaces (wrapped help lines are
    # indented further).
    listed = [
        line.split()[0] for line in help_text.splitlines() if line.startswith("    ") and not line.startswith("     ")
    ]
    assert listed == sorted(names)
    # The {a,b,...} choices in the usage line and positional heading, too.
    assert "{" + ",".join(sorted(names)) + "}" in help_text
    assert "{" + ",".join(names) + "}" not in help_text
    # The parser itself keeps registration order for the UIs that walk it.
    assert names[0] == "weekly"


def test_unknown_subcommand_error_lists_choices_alphabetically(capsys):
    parser = ecalendar._create_argument_parser("calendar.svg")
    names = list(_subparsers_action(parser).choices)
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])
    err = capsys.readouterr().err

    assert "invalid choice: 'bogus'" in err
    assert f"(choose from {', '.join(sorted(names))})" in err


def test_help_subcommand_choices_are_sorted_and_cover_every_command(capsys):
    parser = ecalendar._create_argument_parser("calendar.svg")
    subparsers = _subparsers_action(parser)
    target = next(a for a in subparsers.choices["help"]._actions if a.dest == "subcommand")
    choices = list(target.choices)

    assert choices == sorted(choices)
    assert set(choices) == set(subparsers.choices) - {"help"}
    with pytest.raises(SystemExit):
        parser.parse_args(["help", "bogus"])
    assert f"(choose from {', '.join(choices)})" in capsys.readouterr().err


@pytest.mark.parametrize(
    "flag,value",
    [
        ("headerleft", "Hi"),
        ("headercenter", "Hi"),
        ("headerright", "Hi"),
        ("footerleft", "Hi"),
        ("footercenter", "Hi"),
        ("footerright", "Hi"),
        ("watermark_rotation_angle", 30.0),
    ],
)
def test_page_chrome_flags_do_not_warn_for_svg_views(flag, value, caplog):
    from visualizers.factory import VisualizerFactory

    args = argparse.Namespace(**{flag: value})
    with caplog.at_level("WARNING"):
        ecalendar._warn_unsupported_page_chrome(args, VisualizerFactory.create("weekly"), "weekly")

    assert "not supported" not in caplog.text


def test_page_chrome_flags_still_warn_for_text_mini(caplog):
    from visualizers.factory import VisualizerFactory

    args = argparse.Namespace(headerleft="Hi")
    with caplog.at_level("WARNING"):
        ecalendar._warn_unsupported_page_chrome(args, VisualizerFactory.create("text-mini"), "text-mini")

    assert "--headerleft is not supported for 'text-mini'" in caplog.text
