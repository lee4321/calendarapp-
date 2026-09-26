#!/usr/bin/env python3
"""Move retired section style keys into ``style_rules`` token rules.

Some visualizers used to read a style twice: from a token (``box:cell``) and,
when the token left an attribute unset, from a section key
(``weekly.day_box.stroke_color``) or that key's built-in default.  The section
keys are retired, so every style has one source.  This tool rewrites a theme
so it renders exactly as before:

* For each retired key it works out the value the old code would have used —
  the key itself, its section/``base`` cascade, or the old built-in default.
* Where the theme's token, resolved for that visualizer, leaves the attribute
  unset (the only case in which the old code consulted the key), the value
  goes into a rule ``apply_to: <token>`` selected on the visualizer.  A key
  the old code read ahead of the token (``override``) is written whenever the
  token's value differs.  The rule is inserted
  before the token's other conditional rules, so any of those that match still
  win, as they did before.
* The retired keys are removed.  Comments elsewhere in the file are kept.

Usage:
    uv run python tools/convert_style_keys.py THEME.yaml [...]           # print what changes
    uv run python tools/convert_style_keys.py --in-place THEME.yaml [...]  # rewrite (keeps THEME.yaml.bak)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.retired_style_keys import RETIRED, RETIRED_PATHS, Retired
from config.unified_theme import parse_theme


def _lookup(data: dict, dotted: str) -> tuple[bool, Any]:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def resolve_old_value(data: dict, r: Retired) -> Any:
    """The value the old code used: key, parent section, ``base``, else default.

    A key that resolves to None hands over to its ``fallback`` key, as the old
    code's ``or`` chain did.
    """
    top = r.section.split(".")[0]
    value = r.default
    for path in (f"{r.section}.{r.key}", f"{top}.{r.key}", f"base.{r.key}"):
        found, found_value = _lookup(data, path)
        if found:
            value = found_value
            break
    if value is None and r.fallback:
        other = next(o for o in RETIRED if f"{o.section}.{o.key}" == r.fallback)
        return resolve_old_value(data, other)
    return value


def _has_view_rule(data: dict, token: str, visualizer: str) -> bool:
    """True when a rule already styles ``token`` for exactly this view."""
    for rule in data.get("style_rules") or []:
        if not isinstance(rule, dict) or rule.get("select") != {"visualizer": visualizer}:
            continue
        targets = rule.get("apply_to")
        if token in ([targets] if isinstance(targets, str) else list(targets or [])):
            return True
    return False


def converted_rules(data: dict) -> list[tuple[str, dict]]:
    """``[(token, rule)]`` a theme needs so it renders as it did."""
    theme = parse_theme(data)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    sources: dict[tuple[str, str], set[str]] = {}
    for r in RETIRED:
        # The old code read the key only when the token, resolved for this
        # view, left the attribute unset.  Resolving with just the view (no
        # paper size etc.) counts definitions and view-wide rules — including
        # a rule an earlier run of this tool added, so it is idempotent.
        resolved = theme.resolve_token(r.token, {"visualizer": r.visualizer})
        value = resolve_old_value(data, r)
        if value is None:
            continue  # nothing was drawn from it either way
        if r.attr in resolved and (not r.override or resolved[r.attr] == value):
            continue
        if r.override and _has_view_rule(data, r.token, r.visualizer):
            continue  # converted already: the view rule is where the value lives
        groups.setdefault((r.token, r.visualizer), {})[r.attr] = value
        sources.setdefault((r.token, r.visualizer), set()).add(r.section)
    rules = []
    for (token, visualizer), style in groups.items():
        rule = {
            "name": f"{token} — {visualizer} (from {', '.join(sorted(sources[(token, visualizer)]))})",
            "apply_to": token,
            "select": {"visualizer": visualizer},
            "style": style,
        }
        rules.append((token, rule))
    return rules


# ── Line-based YAML editing (keeps comments) ───────────────────────────────


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block_end(lines: list[str], start: int, indent: int) -> int:
    k = start + 1
    while k < len(lines) and (
        not lines[k].strip()
        or _indent(lines[k]) > indent
        or (_indent(lines[k]) == indent and lines[k].lstrip().startswith("- "))
    ):
        k += 1
    while k - 1 > start and (
        not lines[k - 1].strip() or (lines[k - 1].lstrip().startswith("#") and _indent(lines[k - 1]) <= indent)
    ):
        k -= 1
    return k


def _find_key(lines: list[str], start: int, end: int, indent: int, key: str) -> int | None:
    pattern = re.compile(r"^" + " " * indent + re.escape(key) + r":(\s|$)")
    return next((j for j in range(start, end) if pattern.match(lines[j])), None)


def remove_path(text: str, dotted: str) -> tuple[str, bool]:
    """Delete one dotted key (and ancestors it leaves empty)."""
    lines = text.split("\n")
    start, end, stack = 0, len(lines), []
    for depth, part in enumerate(dotted.split(".")):
        j = _find_key(lines, start, end, 2 * depth, part)
        if j is None:
            return text, False
        k = _block_end(lines, j, 2 * depth)
        stack.append((j, 2 * depth))
        start, end = j + 1, k
    for level, (j, indent) in enumerate(reversed(stack)):
        k = _block_end(lines, j, indent)
        if level:
            body = [line for line in lines[j + 1 : k] if line.strip() and not line.lstrip().startswith("#")]
            if body or lines[j].split(":", 1)[1].split("#")[0].strip():
                break
        a = j
        while a > 0 and lines[a - 1].lstrip().startswith("#") and _indent(lines[a - 1]) == indent:
            a -= 1
        del lines[a:k]
    return "\n".join(lines), True


def _rule_lines(rule: dict, indent: str) -> list[str]:
    dumped = yaml.safe_dump([rule], sort_keys=False, allow_unicode=True, default_flow_style=None, width=1000)
    return [indent + line if line else line for line in dumped.rstrip("\n").split("\n")]


def insert_rules(text: str, data: dict, rules: list[tuple[str, dict]]) -> str:
    """Insert each rule before the first conditional rule targeting its token."""
    lines = text.split("\n")
    head = _find_key(lines, 0, len(lines), 0, "style_rules")
    if head is None:
        lines += ["style_rules:"]
        head = len(lines) - 1
    end = _block_end(lines, head, 0)
    first = next((j for j in range(head + 1, end) if lines[j].lstrip().startswith("- ")), None)
    depth = _indent(lines[first]) if first is not None else 2
    # Only lines at the first item's own indent start a rule; a nested list
    # (``apply_to:`` entries) sits deeper even when the items are at column 0.
    items = [j for j in range(head + 1, end) if lines[j].lstrip().startswith("- ") and _indent(lines[j]) == depth]
    item_indent = " " * depth
    existing = data.get("style_rules") or []
    placed = []
    for order, (token, rule) in enumerate(rules):
        at = end
        for idx, existing_rule in enumerate(existing):
            targets = existing_rule.get("apply_to") if isinstance(existing_rule, dict) else None
            targets = [targets] if isinstance(targets, str) else list(targets or [])
            if token in targets and idx < len(items):
                at = items[idx]
                break
        placed.append((at, order, rule))
    # Bottom-up, so an insertion never shifts a line still to be used.
    for at, _order, rule in sorted(placed, key=lambda p: (p[0], p[1]), reverse=True):
        lines[at:at] = _rule_lines(rule, item_indent)
    return "\n".join(lines)


def convert_text(text: str) -> tuple[str, list[str]]:
    """Return the converted theme text and a list of changes made."""
    data = yaml.safe_load(text) or {}
    if "extends" in data:
        # Retired keys predate inheritance: convert a full theme, then derive.
        raise ValueError("convert the full theme before it extends another (tools/derive_theme.py)")
    rules = converted_rules(data)
    changes = [f"add rule: {rule['name']} {rule['style']}" for _t, rule in rules]
    text = insert_rules(text, data, rules)
    for dotted in sorted(RETIRED_PATHS | {f"{r.section.split('.')[0]}.{r.key}" for r in RETIRED}):
        found, _ = _lookup(yaml.safe_load(text) or {}, dotted)
        if found and dotted in RETIRED_PATHS | _parent_paths_only_retired(data):
            text, _ok = remove_path(text, dotted)
            changes.append(f"remove key: {dotted}")
    # The edits are line-based; refuse to hand back a theme they broke.
    converted = yaml.safe_load(text) or {}
    if len(converted.get("style_rules") or []) != len(data.get("style_rules") or []) + len(rules):
        raise ValueError("conversion lost or duplicated a style rule; the theme was not changed")
    return text, changes


def _parent_paths_only_retired(data: dict) -> set[str]:
    """Section-level cascade keys (``weekly.stroke_color``) that only fed retired keys."""
    from config.theme_engine import _consumed_theme_paths

    consumed = _consumed_theme_paths()
    return {
        f"{r.section.split('.')[0]}.{r.key}" for r in RETIRED if f"{r.section.split('.')[0]}.{r.key}" not in consumed
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("themes", nargs="+", type=Path)
    parser.add_argument("--in-place", action="store_true", help="rewrite the files (a .bak copy is kept)")
    args = parser.parse_args(argv)
    for path in args.themes:
        new_text, changes = convert_text(path.read_text())
        print(f"{path}: {len(changes)} change(s)")
        for change in changes:
            print(f"  {change}")
        if args.in_place and changes:
            shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
            path.write_text(new_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
