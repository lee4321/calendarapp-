"""The content filters are defined once for every subcommand that takes them.

``cli.args._add_content_filter_args()`` registers them and
``cli.config_assembly._apply_content_filters()`` wires them into the config,
for the SVG views, text-mini, excelblockplan and exportdata alike.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import ecalendar
from cli.args import _create_argument_parser
from cli.config_assembly import _apply_args_to_config, _apply_content_filters
from config.config import create_calendar_config

_FILTER_FLAGS = frozenset(
    {
        "--empty",
        "--shade",
        "--noevents",
        "--durations",
        "--nodurations",
        "--milestones",
        "--includenotes",
        "--WBS",
        "--status",
        "--country",
    }
)

_COMMON = {"--noevents", "--milestones", "--WBS", "--status", "--country"}
_PLAN = _COMMON | {"--empty", "--nodurations", "--includenotes"}
_MINI = _COMMON | {"--empty", "--shade", "--durations"}

#: The per-view gating: which filter flags each subcommand registers.
_EXPECTED = {
    "weekly": _PLAN | {"--shade"},
    "timeline": _PLAN,
    "blockplan": _PLAN,
    "gantt": _PLAN,
    "compactplan": _PLAN,
    "pit": _COMMON | {"--empty", "--includenotes"},
    "mini": _MINI,
    "mini-icon": _MINI,
    "candybar": _MINI,
    "text-mini": _COMMON | {"--empty", "--durations"},
    "excelblockplan": _COMMON | {"--empty", "--nodurations"},
    "exportdata": _COMMON | {"--nodurations"},
}

_REPO_DB = Path(__file__).resolve().parent.parent / "calendar.db"

#: Minimal paper-size table; _apply_args_to_config only looks the name up.
_PAPER_SIZES = {"Widescreen": (1056.0, 594.0)}


def _subparsers() -> dict[str, argparse.ArgumentParser]:
    parser = _create_argument_parser("out.svg")
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices


def _filter_actions(sub: argparse.ArgumentParser) -> dict[str, tuple]:
    """Filter flag → (options, default, help, metavar, type, group title)."""
    title = {id(action): group.title for group in sub._action_groups for action in group._group_actions}
    return {
        a.option_strings[0]: (
            tuple(a.option_strings),
            a.default,
            a.help,
            a.metavar,
            a.type,
            title[id(a)],
        )
        for a in sub._actions
        if a.option_strings and a.option_strings[0] in _FILTER_FLAGS
    }


def test_each_subcommand_registers_exactly_its_filters():
    subs = _subparsers()
    for command, expected in _EXPECTED.items():
        assert set(_filter_actions(subs[command])) == expected, command
    for command, sub in subs.items():
        if command not in _EXPECTED:
            titles = {g.title for g in sub._action_groups}
            assert "Content Filtering" not in titles, command


def test_every_filter_flag_has_one_definition():
    """Same options, default, help, metavar, type and group everywhere — the
    only sanctioned difference is excelblockplan's --empty wording."""
    definitions: dict[str, set[tuple]] = {}
    for command in _EXPECTED:
        for flag, spec in _filter_actions(_subparsers()[command]).items():
            if command == "excelblockplan" and flag == "--empty":
                assert spec[2] == "Create blank workbook (no events)"
                continue
            definitions.setdefault(flag, set()).add(spec)
    assert set(definitions) == _FILTER_FLAGS
    for flag, specs in definitions.items():
        assert len(specs) == 1, (flag, specs)
        assert next(iter(specs))[5] == "Content Filtering", flag


@pytest.mark.parametrize("command", ["blockplan", "excelblockplan", "exportdata"])
def test_filters_reach_the_config_identically(command):
    args = _subparsers()[command].parse_args(
        [
            "20260105",
            "20260109",
            "--noevents",
            "--milestones",
            "--WBS",
            "1.2",
            "--status",
            "all",
            "--country",
            "GB",
        ]
    )
    args.command = command
    config = create_calendar_config()
    _apply_content_filters(args, config)

    assert config.includeevents is False
    assert config.includedurations is True
    assert config.milestones is True
    assert config.WBS == "1.2"
    assert config.status_filter is None
    assert config.country == "GB"


@pytest.mark.parametrize("command", sorted(c for c, flags in _EXPECTED.items() if "--empty" in flags))
def test_empty_overrides_the_other_filters(command):
    args = _subparsers()[command].parse_args(["20260105", "20260109", "--empty", "--milestones"])
    args.command = command
    config = create_calendar_config()
    _apply_content_filters(args, config)

    assert (config.includeevents, config.includedurations, config.milestones) == (
        False,
        False,
        False,
    )


def test_svg_views_apply_empty_through_the_config_assembly():
    """run() no longer handles --empty itself; _apply_args_to_config does."""
    parser = _create_argument_parser("out.svg")
    args = parser.parse_args(["blockplan", "20260105", "20260109", "--empty", "--milestones"])
    config = create_calendar_config()
    _apply_args_to_config(args, config, _PAPER_SIZES)

    assert (config.includeevents, config.includedurations, config.milestones) == (
        False,
        False,
        False,
    )


@pytest.mark.parametrize("command", ["excelblockplan", "exportdata"])
def test_run_wires_the_shared_filters(command, tmp_path, monkeypatch):
    seen = []

    def spy(args, config):
        _apply_content_filters(args, config)
        seen.append((args.command, config.includeevents))

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ecalendar, "_apply_content_filters", spy)
    rc = ecalendar.run(
        [
            "ecalendar.py",
            command,
            "20260105",
            "20260109",
            "--noevents",
            "--database",
            str(_REPO_DB),
            "--quiet",
        ]
    )

    assert rc == 0
    assert seen == [(command, False)]
