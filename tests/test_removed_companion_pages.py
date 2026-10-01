"""The companion SVG pages -- details, key, overflow -- no longer exist.

The run's details document replaced them (see renderers/markdown_details.py),
so no view writes one, no flag or config field turns one on, and a theme that
still configures one is rejected.
"""

from __future__ import annotations

import pytest

from cli.args import _create_argument_parser
from config.theme_loader import ThemeError, load_theme


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
def test_a_theme_configuring_a_page_is_rejected(section, key):
    theme = {"theme": {"name": "t", "version": "3.0"}, section: {key: "x"}}
    with pytest.raises(ThemeError, match=key):
        load_theme(theme)
