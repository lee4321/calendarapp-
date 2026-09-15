"""The companion SVG pages -- details, key, overflow -- no longer exist.

The run's details document replaced them (see renderers/markdown_details.py),
so no view writes one, no flag or config field turns one on, and a theme that
still configures one is told where its settings went.
"""

from __future__ import annotations

from dataclasses import fields

import pytest
import yaml

from cli.args import _create_argument_parser
from config.config import CalendarConfig
from config.theme_engine import ThemeEngine


@pytest.mark.parametrize(
    ("view", "flag"),
    [
        ("weekly", "--overflow"),
        ("mini", "--mini-details"),
        ("mini", "--no-mini-details"),
        ("mini-icon", "--mini-details"),
        ("candybar", "--no-mini-details"),
    ],
)
def test_views_reject_the_removed_flags(view, flag, capsys):
    parser = _create_argument_parser("out.svg")
    argv = [view, "20260101", "20260131"]
    parser.parse_args(argv)
    with pytest.raises(SystemExit):
        parser.parse_args([*argv, flag])
    assert flag in capsys.readouterr().err


def test_config_has_no_fields_for_the_removed_pages():
    names = {f.name for f in fields(CalendarConfig)}
    removed = {
        "include_overflow",
        "overflow_title_text",
        "overflow_output_suffix",
        "include_mini_details",
        "mini_details_headers",
        "include_gantt_details",
        "gantt_details_title_text",
        "compactplan_show_legend",
        "compactplan_key_title_text",
        "compactplan_show_holiday_list",
        "details_body_font_size",
    }
    assert not names & removed


def _theme_file(tmp_path, change) -> str:
    theme = yaml.safe_load((ThemeEngine.BUILTIN_THEMES_DIR / "basic.yaml").read_text())
    change(theme)
    path = tmp_path / "theme.yaml"
    path.write_text(yaml.safe_dump(theme))
    return str(path)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("gantt", "show_details"),
        ("gantt", "details_title_text"),
        ("compact_plan", "key_title_text"),
        ("compact_plan", "show_legend"),
        ("overflow", "title_text"),
    ],
)
def test_a_theme_configuring_a_page_is_pointed_at_details(tmp_path, section, key):
    path = _theme_file(tmp_path, lambda theme: theme.setdefault(section, {}).update({key: "x"}))
    engine = ThemeEngine()
    engine.load(path)
    with pytest.raises(Exception, match=r"details:"):
        engine.apply(CalendarConfig())


def test_a_mini_details_section_is_pointed_at_details(tmp_path):
    path = _theme_file(tmp_path, lambda theme: theme.update({"mini_details": {"title_text": "x"}}))
    engine = ThemeEngine()
    engine.load(path)
    with pytest.raises(Exception, match=r"details\.markdown\.columns"):
        engine.apply(CalendarConfig())


def test_migration_turns_mini_details_into_details_markdown():
    from tools.migrate_theme import _convert_mini_details

    converted = _convert_mini_details(
        {
            "enable": False,
            "title_text": "Event Details",
            "headers": ["Start Date", "Name / Description", "Milestone", "Days", "Group"],
            "column_widths": [0.16, 0.52, 0.1, 0.1, 0.12],
            "output_suffix": "_details",
        }
    )

    assert converted == {
        "markdown": {
            "columns": [
                {"field": "start_date", "date_format": "YYYY-MM-DD", "header": "Start Date"},
                {"field": "name", "header": "Name / Description"},
                {"field": "milestone", "header": "Milestone"},
                {"field": "priority", "header": "Days"},
                {"field": "resource_group", "header": "Group"},
            ],
            "enable": False,
            "title_text": "Event Details",
        }
    }
