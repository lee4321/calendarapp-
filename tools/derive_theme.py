#!/usr/bin/env python3
"""Rewrite a full theme as a child that ``extends:`` another theme.

The child keeps only what differs from the parent (see
``config/theme_inheritance.py`` for the merge rules).  Before anything is
written, the child is resolved back through the parent and compared with the
original theme, and the tool refuses unless the two are equal, so a derived
theme renders exactly as the full one did.

Usage:
    uv run python tools/derive_theme.py PARENT THEME.yaml             # print the child and its size
    uv run python tools/derive_theme.py PARENT THEME.yaml --in-place  # rewrite THEME.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.theme_inheritance import find_parent, merge_rules, read_theme_file, resolve_extends

_MISSING = object()


def derive(parent: dict[str, Any], theme: dict[str, Any], parent_ref: str) -> dict[str, Any]:
    """The smallest child of ``parent`` that resolves to ``theme``."""
    unset: list[str] = []
    child: dict[str, Any] = {"extends": parent_ref}
    body: dict[str, Any] = {}
    for key, value in theme.items():
        if key == "style_rules":
            overlay = rule_overlay(parent.get(key) or [], value or [])
            if overlay:
                body[key] = overlay
            continue
        delta = _diff(parent.get(key, _MISSING), value, key, unset)
        if delta is not _MISSING:
            body[key] = delta
    unset += [key for key in parent if key not in theme]
    if unset:
        child["unset"] = unset
    child.update(body)
    return child


def _diff(base: Any, value: Any, path: str, unset: list[str]) -> Any:
    """What a child must say so ``base`` merges to ``value`` (``_MISSING``: nothing)."""
    if isinstance(base, dict) and isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, sub in value.items():
            delta = _diff(base.get(key, _MISSING), sub, f"{path}.{key}", unset)
            if delta is not _MISSING:
                out[key] = delta
        unset += [f"{path}.{key}" for key in base if key not in value]
        return out or _MISSING
    return _MISSING if base == value else value


def rule_overlay(parent_rules: list[dict], rules: list[dict]) -> list[dict]:
    """``style_rules`` entries that turn ``parent_rules`` into ``rules``."""
    by_name = {r.get("name"): r for r in parent_rules}
    wanted = {r.get("name") for r in rules}
    overlay: list[dict] = []
    for i, rule in enumerate(rules):
        name = rule.get("name")
        base = by_name.get(name)
        if base is None:
            # A new rule lands after the one the previous entry touched, so
            # name the rule it follows unless that entry already did.
            if i and (not overlay or overlay[-1]["name"] != rules[i - 1]["name"]):
                overlay.append({"name": rules[i - 1]["name"]})
            overlay.append(rule)
            continue
        entry = _rule_delta(base, rule)
        if len(entry) > 1:
            overlay.append(entry)
    # Removals go last: each one moves the insertion point.
    overlay += [{"name": r["name"], "remove": True} for r in parent_rules if r.get("name") not in wanted]
    return overlay


def _rule_delta(base: dict, rule: dict) -> dict:
    entry: dict[str, Any] = {"name": rule["name"]}
    if any(key not in rule for key in base) or any(k not in rule.get("style", {}) for k in base.get("style") or {}):
        return {"name": rule["name"], "replace": True, **{k: v for k, v in rule.items() if k != "name"}}
    for key, value in rule.items():
        if key == "style" and isinstance(value, dict) and isinstance(base.get("style"), dict):
            style = {k: v for k, v in value.items() if base["style"].get(k, _MISSING) != v}
            if style:
                entry["style"] = style
        elif key != "name" and base.get(key, _MISSING) != value:
            entry[key] = value
    return entry


def same(a: Any, b: Any) -> bool:
    """Equal, including the order of every mapping's keys and every list."""
    if isinstance(a, dict) and isinstance(b, dict):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    return type(a) is type(b) and a == b


class _Dumper(yaml.SafeDumper):
    """Block style, except short flat mappings and lists, which stay on one line."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        super().increase_indent(flow, False)  # indent list items under their key


def _is_flat(value: Any) -> bool:
    items = value.values() if isinstance(value, dict) else value
    return all(not isinstance(v, (dict, list)) for v in items) and len(repr(value)) <= 72


def _dict(dumper: yaml.SafeDumper, data: dict) -> yaml.Node:
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=_is_flat(data))


def _list(dumper: yaml.SafeDumper, data: list) -> yaml.Node:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=_is_flat(data))


_Dumper.add_representer(dict, _dict)
_Dumper.add_representer(list, _list)


def dump(child: dict[str, Any]) -> str:
    return yaml.dump(child, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("parent", help="theme name or path to extend")
    parser.add_argument("theme", type=Path)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args(argv)

    theme = yaml.safe_load(args.theme.read_text()) or {}
    if "extends" in theme:
        print(f"{args.theme}: already extends {theme['extends']!r}", file=sys.stderr)
        return 1
    parent = read_theme_file(find_parent(args.parent, args.theme.parent))
    child = derive(parent, theme, args.parent)

    resolved = resolve_extends(child, args.theme.parent)
    if resolved != theme:
        print(f"{args.theme}: the derived child does not resolve to the original; left unchanged", file=sys.stderr)
        return 1
    if not same(resolved, theme):
        print(f"{args.theme}: note — equal, but some keys resolve in a different order", file=sys.stderr)
    assert merge_rules(parent.get("style_rules") or [], child.get("style_rules") or []) == theme.get("style_rules")

    header = (
        f"# {args.theme.stem}: every value not listed here comes from '{args.parent}'.\n"
        '# See USER_GUIDE.md, "Theme inheritance".  Rewritten by tools/derive_theme.py.\n'
    )
    text = header + dump(child)
    if resolve_extends(yaml.safe_load(text), args.theme.parent) != theme:
        print(f"{args.theme}: the written YAML does not read back equal; left unchanged", file=sys.stderr)
        return 1
    if args.in_place:
        args.theme.write_text(text)
    else:
        sys.stdout.write(text)
    before, after = len(args.theme.read_text().splitlines()) if not args.in_place else None, len(text.splitlines())
    print(f"{args.theme}: {after} lines" + (f" (was {before})" if before else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
