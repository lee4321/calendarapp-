"""Decoration is set by themes only: no CLI flag overrides it.

Every flag that used to override a theme's decoration (colours, shading,
icons, ticks, leaders, today line, watermark, ...) is gone, and the parsers
may only offer the explicit allowlist of content / layout / output flags.
A new flag must be added to the allowlist on purpose, which is the moment to
ask whether it belongs in a theme instead.
"""

from __future__ import annotations

import argparse

import pytest

from cli.args import _create_argument_parser

_REMOVED = {
    "weekly": ["--shade", "--fiscal-colors", "--watermark-text", "--watermark-rotation-angle", "--watermark-image"],
    "mini": ["--mini-grid-lines", "--mini-icon-set", "--mini-no-adjacent", "--mini-title-format", "--shade"],
    "mini-icon": ["--mini-icon-set", "--mini-grid-lines", "--fiscal-colors"],
    "candybar": [
        "--candybar-month-rotation",
        "--candybar-weekend-fill",
        "--candybar-month-shading",
        "--candybar-month-side",
        "--candybar-no-week-numbers",
        "--candybar-suppress-weekends",
    ],
    "timeline": [
        "--today-line-length",
        "--today-line-direction",
        "--label-fill-opacity",
        "--fiscal-show-periods",
        "--fiscal-show-quarters",
    ],
    "pit": [
        "--label-side",
        "--tick-unit",
        "--tick-interval",
        "--tick-label-format",
        "--tick-length",
        "--no-ticks",
        "--no-tick-labels",
        "--date-placement",
        "--today-line",
        "--no-today-line",
        "--today-date",
        "--today-label",
        "--event-icon",
        "--milestone-icon",
        "--marker-size",
        "--label-icon-size",
        "--label-icon-gap",
        "--leader-dash",
        "--leader-label-anchor",
        "--leader-length",
        "--leader-stub",
    ],
}

#: Every long option any subcommand may register.
_ALLOWED = frozenset(
    [
        "--WBS",
        "--candybar-cell-width",
        "--candybar-max-rows-per-page",
        "--candybar-row-height",
        "--color",
        "--columns",
        "--country",
        "--csv",
        "--database",
        "--details-md",
        "--direction",
        "--durations",
        "--embed-data",
        "--empty",
        "--filter",
        "--fiscal",
        "--fiscal-year-offset",
        "--footer",
        "--footercenter",
        "--footerleft",
        "--footerright",
        "--fullset",
        "--header",
        "--headercenter",
        "--headerleft",
        "--headerright",
        "--help",
        "--icons",
        "--includenotes",
        "--margin",
        "--milestones",
        "--mini-columns",
        "--mini-rows",
        "--monthnames",
        "--no-csv",
        "--no-details-md",
        "--no-icons",
        "--nodurations",
        "--noevents",
        "--orientation",
        "--outputfile",
        "--paginate",
        "--papersize",
        "--quiet",
        "--rows",
        "--shrink",
        "--sized",
        "--status",
        "--theme",
        "--tile-size",
        "--trace-style",
        "--verbose",
        "--week-number-mode",
        "--week1-start",
        "--weekend-days",
        "--weekends",
        "--weeknumbers",
    ]
)


def _subparsers() -> dict[str, argparse.ArgumentParser]:
    parser = _create_argument_parser("out.svg")
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


@pytest.mark.parametrize(
    "view,flag",
    [(view, flag) for view, flags in _REMOVED.items() for flag in flags],
)
def test_decoration_flags_are_rejected(view, flag, capsys):
    parser = _create_argument_parser("out.svg")
    argv = [view, "20260101", "20260131"]
    parser.parse_args(argv)
    with pytest.raises(SystemExit):
        parser.parse_args([*argv, flag])
    assert flag in capsys.readouterr().err


def test_parsers_offer_only_allowlisted_options():
    offered: set[str] = set()
    for sub in _subparsers().values():
        for action in sub._actions:
            offered.update(o for o in action.option_strings if o.startswith("--"))
    assert offered <= _ALLOWED, (
        f"new CLI options need review (decoration belongs in a theme): {sorted(offered - _ALLOWED)}"
    )
