"""The companion SVG pages -- details, key, overflow -- no longer exist.

The run's details document replaced them (see renderers/markdown_details.py),
so no view writes one, no flag or config field turns one on, and a theme that
still configures one is told where its settings went.
"""

from __future__ import annotations

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
