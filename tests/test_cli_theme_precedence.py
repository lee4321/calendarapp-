"""CLI-over-theme precedence regression tests.

The theme engine is applied twice in ecalendar.run(); the second apply used
to silently overwrite explicit CLI values for ~30 options whenever the theme
set the same field (docs/cli_theme_overrides.html, Section 2).  The fix
routes every simple CLI→config assignment through _CLI_CONFIG_OVERRIDES,
applied once up front and re-asserted by _reapply_post_theme_cli_overrides()
after the final theme apply.

These tests lock that contract:
  * every table row survives a simulated theme overwrite,
  * omitted options leave theme values untouched,
  * the table stays in sync with the real parser (dest names and the
    argparse defaults each sentinel kind relies on) and with CalendarConfig.
"""

from __future__ import annotations

import argparse

import ecalendar
from cli.config_assembly import (
    _CLI_CONFIG_OVERRIDES,
    _apply_cli_config_overrides,
    _reapply_post_theme_cli_overrides,
)
from config.config import create_calendar_config

_THEME_SENTINEL = "THEME_VALUE"


def _cli_value_for(kind: str, arg_name: str):
    # store_true/store_false actions can only ever be flipped by the user;
    # "value" rows carry an arbitrary payload, so a unique string suffices
    # to detect the assignment.
    return True if kind in ("enable", "disable") else f"CLI_{arg_name}"


def test_cli_value_survives_theme_overwrite():
    for arg_name, config_attr, kind in _CLI_CONFIG_OVERRIDES:
        config = create_calendar_config()
        args = argparse.Namespace(**{arg_name: _cli_value_for(kind, arg_name)})

        _apply_cli_config_overrides(args, config)
        cli_result = getattr(config, config_attr)
        if kind != "value":
            assert cli_result is (kind == "enable"), (arg_name, config_attr)

        # Simulate the second theme.apply() clobbering the field ...
        setattr(config, config_attr, _THEME_SENTINEL)
        # ... the post-theme pass must restore the CLI value.
        _reapply_post_theme_cli_overrides(args, config)
        assert getattr(config, config_attr) == cli_result, (arg_name, config_attr)


def test_theme_value_kept_when_cli_omitted():
    config = create_calendar_config()
    args = argparse.Namespace()  # nothing given on the command line
    for _, config_attr, _ in _CLI_CONFIG_OVERRIDES:
        setattr(config, config_attr, _THEME_SENTINEL)
    _reapply_post_theme_cli_overrides(args, config)
    for _, config_attr, _ in _CLI_CONFIG_OVERRIDES:
        assert getattr(config, config_attr) == _THEME_SENTINEL, config_attr


def test_override_table_matches_parser_dests_and_defaults():
    """Each table row must name a real CLI dest whose argparse default is the
    sentinel its kind relies on: None for "value" rows (so ``is not None``
    means explicitly given), False for "enable"/"disable" store_true flags."""
    parser = ecalendar._create_argument_parser("x.svg")
    sub = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
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


def test_override_table_targets_real_config_fields():
    config = create_calendar_config()
    missing = [
        attr for _, attr, _ in _CLI_CONFIG_OVERRIDES if not hasattr(config, attr)
    ]
    assert not missing, f"table targets unknown CalendarConfig fields: {missing}"


def test_reapply_restores_text_options_over_theme():
    """Watermark text/rotation flow through _apply_text_options, which the
    post-theme pass re-runs so explicit CLI text beats theme watermark keys."""
    config = create_calendar_config()
    config.adjustedstart = "20260105"
    config.adjustedend = "20260630"
    args = argparse.Namespace(watermark_text="CLI_WM", watermark_rotation_angle=33.0)

    config.watermark_text = "THEME_WM"
    config.watermark_rotation_angle = 77.0
    _reapply_post_theme_cli_overrides(args, config)

    assert config.watermark_text == "CLI_WM"
    assert config.watermark_rotation_angle == 33.0
