#!/usr/bin/env python3
"""
Validate a theme YAML against the unified schema.

Use this during the migration to check whether a theme is ready for the
unified runtime (design §11.2).  The script:

  1. Parses the theme with :func:`config.unified_theme.parse_theme`.  If
     the parser rejects it (legacy section names, unknown selectors,
     malformed rules), the error is printed and the script exits non-zero.

  2. For each requested visualizer (default: all), runs the
     :func:`config.required_keys.check_required_keys` probe and reports
     any missing settings or tokens with the §11.2 error format —
     including a paste-ready snippet pulled from basic.yaml.

  3. Optionally runs the theme through the converter first
     (``--convert``).  Useful when validating a legacy theme without
     committing the conversion.

Exit codes
----------
  0 — theme parses cleanly and satisfies every requested visualizer.
  1 — theme parses but is missing one or more required keys.
  2 — theme does not parse (invalid schema).

Examples
--------
    uv run python tools/validate_theme.py config/themes/basic.yaml
    uv run python tools/validate_theme.py config/themes/SAMPLE.yaml --visualizer weekly
    uv run python tools/validate_theme.py config/themes/default.yaml --convert
    uv run python tools/validate_theme.py config/themes/default.yaml --convert -v blockplan,timeline

"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure imports work whether the script is run directly or via -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from config.required_keys import (
    VISUALIZERS,
    check_required_keys,
    format_missing_key_error,
)
from config.unified_theme import ThemeError, parse_theme


def _deep_to_dict(obj):
    """OrderedDict-trees -> plain-dict trees (the parser accepts plain dicts)."""
    if isinstance(obj, dict):
        return {k: _deep_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_to_dict(v) for v in obj]
    return obj


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("theme", help="Path to a theme YAML file.")
    parser.add_argument(
        "-v", "--visualizer",
        help=(
            "Visualizer(s) to validate against (comma-separated). "
            f"Default: all of {sorted(VISUALIZERS)}."
        ),
    )
    parser.add_argument(
        "--convert", action="store_true",
        help=(
            "Run the theme through tools/migrate_theme.py first.  Use this on "
            "legacy themes that haven't been migrated yet."
        ),
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress the success line on a clean pass.",
    )
    args = parser.parse_args(argv)

    theme_path = Path(args.theme)
    if not theme_path.exists():
        print(f"error: theme file not found: {theme_path}", file=sys.stderr)
        return 2

    # Resolve which visualizers to check.
    if args.visualizer:
        requested = [v.strip() for v in args.visualizer.split(",") if v.strip()]
        unknown = set(requested) - VISUALIZERS
        if unknown:
            print(
                f"error: unknown visualizer(s) {sorted(unknown)}. "
                f"Known: {sorted(VISUALIZERS)}",
                file=sys.stderr,
            )
            return 2
    else:
        requested = sorted(VISUALIZERS)

    # Load and optionally convert.
    raw = yaml.safe_load(theme_path.read_text()) or {}
    if args.convert:
        from tools.migrate_theme import convert_theme
        raw = _deep_to_dict(convert_theme(raw, fname=theme_path.name))

    # Parse.
    try:
        theme = parse_theme(raw)
    except ThemeError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        if not args.convert:
            print(
                "hint: this looks like a legacy theme.  Run again with --convert "
                "to migrate it on the fly, or commit a permanent conversion via:"
                "\n    uv run python tools/migrate_theme.py --in-place "
                f"{theme_path}\n",
                file=sys.stderr,
            )
        return 2

    # Required-key probe per requested visualizer.
    any_missing = False
    for v in requested:
        missing = check_required_keys(theme, v)
        if not missing:
            if not args.quiet:
                print(f"  {v:14s}  ok  ({len(theme.defined_tokens())} tokens defined)")
            continue
        any_missing = True
        print(format_missing_key_error(missing, visualizer=v, theme_origin=str(theme_path)))

    if any_missing:
        return 1

    if not args.quiet:
        print(f"\n{theme_path} satisfies every requested visualizer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
