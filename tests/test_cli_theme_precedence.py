"""CLI-over-theme precedence regression tests.

The run's theme is loaded first and every command-line option is applied
after it (ecalendar.run), so an explicit option always beats the theme's value
for the same setting.  Every simple CLI assignment goes through
_CLI_CONFIG_OVERRIDES; these tests lock that contract:

  * every table row writes its target (a config field or a ``theme:`` path),
  * options left off the command line leave the theme's values alone,
  * the table stays in sync with the real parser (dest names and the
    argparse defaults each sentinel kind relies on) and with the schema.
"""

from __future__ import annotations

import argparse

import ecalendar
from cli.config_assembly import _CLI_CONFIG_OVERRIDES, _apply_cli_config_overrides, load_run_theme
from config.config import create_calendar_config
from config.theme_paths import get_path


def _read(config, target):
    return (
        get_path(config.theme_v3, target[len("theme:") :]) if target.startswith("theme:") else getattr(config, target)
    )


def _cli_value_for(kind: str, arg_name: str):
    # store_true actions can only ever be flipped by the user; "value" rows
    # carry an arbitrary payload, so a unique string detects the assignment.
    return True if kind in ("enable", "disable") else f"CLI_{arg_name}"


def test_cli_value_beats_the_themes_value():
    for arg_name, target, kind in _CLI_CONFIG_OVERRIDES:
        config = create_calendar_config()
        load_run_theme(config, "default")
        args = argparse.Namespace(**{arg_name: _cli_value_for(kind, arg_name)})

        _apply_cli_config_overrides(args, config)

        expected = (kind == "enable") if kind != "value" else f"CLI_{arg_name}"
        assert _read(config, target) == expected, (arg_name, target)


def test_theme_value_kept_when_cli_omitted():
    config = create_calendar_config()
    load_run_theme(config, "default")
    before = {target: _read(config, target) for _, target, _ in _CLI_CONFIG_OVERRIDES}

    _apply_cli_config_overrides(argparse.Namespace(), config)

    assert {target: _read(config, target) for _, target, _ in _CLI_CONFIG_OVERRIDES} == before


def test_override_table_matches_parser_dests_and_defaults():
    """Each table row must name a real CLI dest whose argparse default is the
    sentinel its kind relies on: None for "value" rows (so ``is not None``
    means explicitly given), False for "enable"/"disable" store_true flags."""
    parser = ecalendar._create_argument_parser("x.svg")
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    defaults: dict[str, set] = {}
    for subparser in sub.choices.values():
        try:
            ns = subparser.parse_args([])
        except SystemExit:
            continue  # subcommands with required positionals (help)
        for dest, val in vars(ns).items():
            defaults.setdefault(dest, set()).add(val)

    for arg_name, _, kind in _CLI_CONFIG_OVERRIDES:
        assert arg_name in defaults, f"no subcommand offers --option with dest {arg_name}"
        want = {None} if kind == "value" else {False}
        assert defaults[arg_name] == want, (arg_name, kind, defaults[arg_name])


def test_override_table_targets_real_fields():
    config = create_calendar_config()
    for _, target, _ in _CLI_CONFIG_OVERRIDES:
        if target.startswith("theme:"):
            get_path(config.theme_v3, target[len("theme:") :])  # raises AttributeError when the path is wrong
        else:
            assert hasattr(config, target), target


def test_header_text_option_expands_template_variables():
    from cli.config_assembly import _apply_text_options

    config = create_calendar_config()
    config.adjustedstart = "20260105"
    config.adjustedend = "20260630"

    _apply_text_options(argparse.Namespace(headerleft="From [startdate]"), config)

    assert config.header_left_text == "From 20260105"


def test_watermark_text_comes_from_the_theme_with_template_vars_expanded():
    from band_helpers import update_theme

    from cli.config_assembly import _apply_text_options

    config = create_calendar_config()
    config.adjustedstart = "20260105"
    config.adjustedend = "20260630"
    update_theme(config, watermark={"text": "From [startdate]"})
    _apply_text_options(argparse.Namespace(), config)

    assert config.theme_v3.watermark.text == "From 20260105"
