"""Theme inheritance: a theme ``extends:`` another and states only what differs.

A child theme names its parent and carries its own changes::

    extends: corporate              # a built-in name, or a path to a .yaml file
    unset: [candybar.month_shade_colors]
    theme: {name: Dark, description: ...}
    timeline:
      axis_color: white             # everything else under timeline: comes from corporate
    style_rules:
      - name: define text:heading   # a parent rule, by name: merged in place
        style: {color: white}
      - name: dark background       # a new name: inserted after the entry above
        apply_to: box:default
        style: {fill: black}

The merge is resolved at load time, so everything downstream (the theme
engine, ``parse_theme``, ``tools/validate_theme.py``) sees one ordinary theme:

* **Sections** merge key by key, recursively.  Lists and scalars replace.
* **``unset``** lists dotted keys to delete from the merged result — for a key
  the parent sets that the child wants left at the built-in default.
* **``style_rules``** are matched by ``name``.  An entry naming a parent rule
  merges into it where it stands (``style`` key by key, every other key
  replaced); ``replace: true`` swaps the whole rule and ``remove: true`` drops
  it.  An entry with a new name is inserted after the rule the previous entry
  touched, or first when it leads the list, so rule order — which decides
  which rule wins — is always explicit.

A parent can itself extend another theme.  ``tools/derive_theme.py`` writes a
child from a full theme and proves that resolving it gives the original back.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from config.unified_theme import ThemeError

BUILTIN_THEMES_DIR = Path(__file__).parent / "themes"

#: Keys that steer the merge and are gone from the resolved theme.
INHERITANCE_KEYS = ("extends", "unset")


def read_theme_file(path: str | Path) -> dict[str, Any]:
    """Load a theme file and resolve its ``extends:`` chain."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ThemeError(f"Invalid YAML in theme file '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeError(f"{path}: top-level theme must be a YAML mapping")
    return resolve_extends(data, path.parent, (path.resolve(),))


def resolve_extends(
    data: dict[str, Any], base_dir: Path | None = None, _chain: tuple[Path, ...] = ()
) -> dict[str, Any]:
    """Return ``data`` merged over its parent; ``data`` itself if it extends nothing."""
    ref = data.get("extends")
    if ref is None:
        if "unset" in data:
            raise ThemeError("'unset' only applies to a theme that 'extends' another")
        return data
    parent_path = find_parent(str(ref), base_dir)
    if parent_path.resolve() in _chain:
        cycle = " -> ".join(p.stem for p in (*_chain, parent_path))
        raise ThemeError(f"themes extend each other in a loop: {cycle}")
    parent = yaml.safe_load(parent_path.read_text()) or {}
    parent = resolve_extends(parent, parent_path.parent, (*_chain, parent_path.resolve()))
    merged = merge_theme(parent, {k: v for k, v in data.items() if k not in INHERITANCE_KEYS})
    for dotted in data.get("unset") or []:
        _unset(merged, str(dotted))
    return merged


def find_parent(ref: str, base_dir: Path | None) -> Path:
    """``extends:`` target: a path (relative to the child) or a theme name."""
    here = base_dir or Path.cwd()
    if ref.endswith((".yaml", ".yml")):
        candidates = [here / ref]
    else:
        candidates = [here / f"{ref}.yaml", BUILTIN_THEMES_DIR / f"{ref}.yaml"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ThemeError(f"extends: theme '{ref}' not found (looked for {', '.join(map(str, candidates))})")


def merge_theme(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """``child``'s sections merged over a copy of ``parent``."""
    merged = copy.deepcopy(parent)
    for key, value in child.items():
        if key == "style_rules":
            merged[key] = merge_rules(merged.get(key) or [], value or [])
        else:
            merged[key] = _deep_merge(merged.get(key), value)
    return merged


def merge_rules(parent_rules: list[dict[str, Any]], overlay: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply a child's ``style_rules`` entries to its parent's, by rule name."""
    rules = [copy.deepcopy(r) for r in parent_rules]
    _require_unique_names(rules, "the parent theme")
    _require_unique_names(overlay, "this theme")
    touched = -1  # index of the rule the previous entry touched
    for entry in overlay:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            raise ThemeError("every style_rules entry of a theme that extends another needs a 'name'")
        at = next((i for i, rule in enumerate(rules) if rule.get("name") == name), None)
        body = {k: copy.deepcopy(v) for k, v in entry.items() if k not in ("remove", "replace")}
        if at is None:
            if entry.get("remove") or entry.get("replace"):
                raise ThemeError(f"style_rules: no rule named '{name}' in the parent theme to remove or replace")
            touched += 1
            rules.insert(touched, body)
        elif entry.get("remove"):
            del rules[at]
            touched = at - 1
        else:
            rules[at] = body if entry.get("replace") else _merge_rule(rules[at], body)
            touched = at
    return rules


def _merge_rule(base: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in entry.items():
        if key == "style" and isinstance(value, dict) and isinstance(base.get("style"), dict):
            merged["style"] = {**base["style"], **value}
        else:
            merged[key] = value
    return merged


def _deep_merge(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        merged = dict(base)
        for key, value in over.items():
            merged[key] = _deep_merge(base[key], value) if key in base else copy.deepcopy(value)
        return merged
    return copy.deepcopy(over)


def _unset(data: dict[str, Any], dotted: str) -> None:
    *parents, last = dotted.split(".")
    node: Any = data
    for part in parents:
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict) or last not in node:
        raise ThemeError(f"unset: '{dotted}' is not set by the parent theme")
    del node[last]


def _require_unique_names(rules: list[Any], where: str) -> None:
    seen: set[str] = set()
    for rule in rules:
        name = rule.get("name") if isinstance(rule, dict) else None
        if name in seen:
            raise ThemeError(f"style_rules: two rules in {where} are named '{name}'; names must be unique to inherit")
        if name:
            seen.add(name)
