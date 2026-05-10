"""
Unified theme data model and loader.

This module implements the parsed-theme half of design §4–§6 (Unified rule
schema and Resolution & precedence).  It is being built in parallel with the
legacy theme_engine.py during the migration; nothing in this module is wired
into the runtime yet.  The atomic cutover commit will replace theme_engine
with calls into this module.

What's in here
--------------
* ``Rule`` / ``Selector`` lightweight wrappers around the YAML shape.
* ``UnifiedTheme`` — the loaded theme, exposing the raw section dicts plus a
  parsed ``style_rules`` list.  ``UnifiedTheme.resolve(target, context)`` is the
  query the renderer will call.
* ``ThemeError`` — raised on schema violations (legacy section names, unknown
  apply_to targets, malformed rules, missing required keys).
* ``parse_theme(path | dict)`` — the entry point.

What's NOT in here (yet)
------------------------
* The required-key registry per visualizer (lives in config/required_keys.py
  in the next commit).
* The example-from-basic-yaml lookup for missing-key errors (lives in
  config/missing_key.py).
* Style-rule resolution against actual event/day data — the predicates are
  recognized syntactically but not all are evaluated end-to-end yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# ─── Schema constants ────────────────────────────────────────────────────────

# Top-level sections recognized by the unified parser.  Anything not in this
# set is rejected with a ThemeError naming the converter.  This list mirrors
# the post-migration enumeration in design §9.4.
VALID_SECTIONS: frozenset[str] = frozenset({
    "theme",
    "base",
    "layout",
    "header",
    "footer",
    "events",
    "durations",
    "watermark",
    "fiscal",
    "colors",
    "weekly",
    "mini_calendar",
    "mini_details",
    "text_mini",
    "timeline",
    "timeline_events",
    "timeline_durations",
    "compact_plan",
    "blockplan",
    "excelheader",
    "time_bands",
    "style_rules",
})

# Legacy sections that the migration retires.  Their presence is a hard parse
# error pointing the author at tools/migrate_theme.py.
RETIRED_SECTIONS: frozenset[str] = frozenset({
    "text_styles",
    "box_styles",
    "line_styles",
    "icon_styles",
    "element_styles",
    "axis",
    "swimlane_rules",
})

# Recognized define: kinds.  Every define-rule must use one of these.
DEFINE_KINDS: frozenset[str] = frozenset({"text", "box", "line", "icon"})

# Recognized apply_to targets.  ``<kind>:<name>`` patterns also accepted
# dynamically (we just check the prefix is a valid kind).
APPLY_TO_BASE: frozenset[str] = frozenset({"element", "lane"})

# Token kinds for apply_to: ``<kind>:<name>`` references.
TOKEN_KINDS: frozenset[str] = DEFINE_KINDS

# Recognized selector keys.  This list is the syntactic registry — semantic
# matching for several of these still needs renderer-side hookup.  See
# design §4 schema tree.
SELECTOR_KEYS: frozenset[str] = frozenset({
    # context
    "papersize", "visualizer", "scope", "element",
    # content predicates
    "event_type", "task_name", "notes", "resource_group", "resource_names",
    "wbs", "milestone", "rollup", "federal_holiday", "company_holiday",
    "nonworkday", "workday", "weekend",
    "priority", "priority_min", "priority_max",
    "percent_complete", "band", "value", "repeat",
    "date", "date_overlap",
    "swimlane",
    "color", "icon",
    # aggregation modifiers
    "min_match", "any_event", "all_events",
})


# ─── Exception ──────────────────────────────────────────────────────────────


class ThemeError(ValueError):
    """Raised when a theme YAML violates the unified schema."""


# ─── Data model ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    """One entry in ``style_rules``."""

    name: str
    define: str | None       # "text" | "box" | "line" | "icon" | None
    as_name: str | None      # token name when define: is set
    apply_to: tuple[str, ...]  # list-valued apply_to is normalized to a tuple
    select: dict[str, Any]
    style: dict[str, Any]

    @property
    def is_definition(self) -> bool:
        return self.define is not None


@dataclass
class UnifiedTheme:
    """A parsed theme YAML.

    Raw sections are kept as dicts so non-styling consumers (renderers reading
    ``timeline.tick_label_format`` directly, etc.) can pull values without
    going through any resolver.  Styling consumers go through ``resolve()``
    and ``find_rules()``.
    """

    # Raw top-level sections.  Empty mapping if the section is absent.
    sections: dict[str, Any] = field(default_factory=dict)

    # Parsed ``style_rules`` (in declaration order).
    rules: list[Rule] = field(default_factory=list)

    # Token registry: ``<kind>:<name>`` -> list[Rule] (definitions and any
    # conditional overrides applying to that token).  Populated by
    # ``_build_token_index``.
    _token_index: dict[str, list[Rule]] = field(default_factory=dict)

    # ----- Section access (non-styling config) -------------------------------

    def section(self, name: str) -> dict[str, Any]:
        """Return a top-level section dict, or {} if absent."""
        v = self.sections.get(name)
        return v if isinstance(v, dict) else {}

    def has_section(self, name: str) -> bool:
        return name in self.sections and self.sections[name] is not None

    # ----- Token resolution --------------------------------------------------

    def resolve_token(self, token: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the merged style bag for ``token`` at ``context``.

        ``token`` is ``"<kind>:<name>"``.  ``context`` is a flat dict of
        selector values (papersize=letter, visualizer=weekly, etc.).  Definition
        rules apply unconditionally; conditional rules (those with a non-empty
        select:) layer on top in declaration order, last-wins.
        """
        ctx = context or {}
        layers = self._token_index.get(token, [])
        merged: dict[str, Any] = {}
        for rule in layers:
            if not _select_matches(rule.select, ctx):
                continue
            for k, v in rule.style.items():
                if k == "use":
                    # `use: <other-token>` pulls the referenced token's
                    # resolved style first; explicit keys then override.
                    referenced = self.resolve_token(v, ctx)
                    merged = {**referenced, **{kk: vv for kk, vv in merged.items() if kk != "use"}}
                else:
                    merged[k] = v
        return merged

    # ----- Rule matching -----------------------------------------------------

    def find_rules(self, target: str, context: dict[str, Any] | None = None) -> list[Rule]:
        """All rules whose ``apply_to`` mentions ``target`` and select matches."""
        ctx = context or {}
        out: list[Rule] = []
        for rule in self.rules:
            if rule.is_definition:
                continue
            if target not in rule.apply_to:
                continue
            if not _select_matches(rule.select, ctx):
                continue
            out.append(rule)
        return out

    def route_lane(self, context: dict[str, Any]) -> str | None:
        """First-match-wins lane routing (design §9.9).

        Returns the swimlane name for the first ``apply_to: lane`` rule whose
        select matches the context.  Returns ``None`` if no rule matches.
        """
        for rule in self.rules:
            if "lane" not in rule.apply_to:
                continue
            if not _select_matches(rule.select, context):
                continue
            lane = rule.style.get("swimlane")
            if isinstance(lane, str):
                return lane
        return None

    # ----- Token introspection ----------------------------------------------

    def defined_tokens(self) -> list[str]:
        """All ``<kind>:<name>`` tokens that have at least one definition."""
        return sorted(
            t for t, layers in self._token_index.items()
            if any(r.is_definition for r in layers)
        )


# ─── Selector matching ──────────────────────────────────────────────────────


def _select_matches(select: dict[str, Any], context: dict[str, Any]) -> bool:
    """True if every key in ``select`` is satisfied by ``context``.

    Empty ``select`` matches everything.  Predicate semantics:

    * String key with list-valued ``select`` value matches if ``context[key]``
      is in the list.
    * String key with scalar value matches on equality.
    * ``priority_min`` / ``priority_max`` / ``percent_complete: {min, max}``
      are recognized as range predicates.

    A rule with a constraint on key ``X`` does *not* apply unless the context
    binds ``X``.  This is the conservative interpretation: rules opt into
    contexts, they don't fall through unmatched.  An empty ``select`` is the
    explicit "always applies" form and is how token definitions are written.
    """
    for key, want in select.items():
        if key not in context:
            # Constraint not satisfied — context hasn't bound this key.
            return False
        have = context[key]
        if not _value_matches(want, have, key=key):
            return False
    return True


def _value_matches(want: Any, have: Any, *, key: str) -> bool:
    # Range predicate
    if isinstance(want, dict):
        lo = want.get("min")
        hi = want.get("max")
        try:
            n = float(have)
        except (TypeError, ValueError):
            return False
        if lo is not None and n < float(lo):
            return False
        if hi is not None and n > float(hi):
            return False
        return True

    # priority_min / priority_max keys
    if key.endswith("_min"):
        try:
            return float(have) >= float(want)
        except (TypeError, ValueError):
            return False
    if key.endswith("_max"):
        try:
            return float(have) <= float(want)
        except (TypeError, ValueError):
            return False

    # List-valued selector — substring match on string contexts, exact-match
    # on others.  Case-insensitive for strings.
    if isinstance(want, list):
        for item in want:
            if _scalar_matches(item, have):
                return True
        return False

    return _scalar_matches(want, have)


def _scalar_matches(want: Any, have: Any) -> bool:
    if isinstance(want, str) and isinstance(have, str):
        return want.lower() in have.lower()
    return want == have


# ─── Parser ─────────────────────────────────────────────────────────────────


def parse_theme(source: str | Path | dict[str, Any]) -> UnifiedTheme:
    """Parse a theme from a YAML file, YAML string, or already-loaded dict.

    Raises :class:`ThemeError` on any schema violation, with a message that
    names the offending key and (for legacy sections) points at
    ``tools/migrate_theme.py``.
    """
    if isinstance(source, dict):
        raw = source
        origin = "<dict>"
    elif isinstance(source, Path):
        raw = yaml.safe_load(source.read_text()) or {}
        origin = str(source)
    elif isinstance(source, str):
        # Heuristic: treat as a path if it looks like one, otherwise as YAML text.
        if "\n" in source or source.lstrip().startswith(("{", "-", "#")):
            raw = yaml.safe_load(source) or {}
            origin = "<string>"
        else:
            p = Path(source)
            raw = yaml.safe_load(p.read_text()) or {}
            origin = str(p)
    else:
        raise TypeError(f"parse_theme expects path/string/dict, got {type(source)!r}")

    if not isinstance(raw, dict):
        raise ThemeError(f"{origin}: top-level theme must be a YAML mapping")

    _check_section_names(raw, origin=origin)

    rules = _parse_rules(raw.get("style_rules") or [], origin=origin)
    theme = UnifiedTheme(sections=raw, rules=rules)
    theme._token_index = _build_token_index(rules)
    return theme


def _check_section_names(raw: dict[str, Any], *, origin: str) -> None:
    for key in raw:
        if key in VALID_SECTIONS:
            continue
        if key in RETIRED_SECTIONS:
            raise ThemeError(
                f"{origin}: legacy section '{key}' is no longer supported; "
                "run `uv run python tools/migrate_theme.py` to convert this "
                "theme to the unified style_rules schema."
            )
        raise ThemeError(
            f"{origin}: unknown top-level section '{key}'. "
            f"Valid sections: {sorted(VALID_SECTIONS)}"
        )


def _parse_rules(raw_rules: Iterable[Any], *, origin: str) -> list[Rule]:
    out: list[Rule] = []
    for i, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ThemeError(f"{origin}: style_rules[{i}] must be a mapping")

        name = str(raw.get("name") or f"rule_{i}")
        define = raw.get("define")
        as_name = raw.get("as")
        apply_to = raw.get("apply_to")
        select = raw.get("select") or {}
        style = raw.get("style") or {}

        if define is not None:
            if define not in DEFINE_KINDS:
                raise ThemeError(
                    f"{origin}: style_rules[{i}] '{name}': define: must be one of "
                    f"{sorted(DEFINE_KINDS)}, got {define!r}"
                )
            if not isinstance(as_name, str) or not as_name:
                raise ThemeError(
                    f"{origin}: style_rules[{i}] '{name}': define: requires a non-empty `as:` token name"
                )
            if apply_to is not None:
                raise ThemeError(
                    f"{origin}: style_rules[{i}] '{name}': `apply_to:` must be omitted on a `define:` rule"
                )
            # The rule's effective target is the token slot.  Normalize.
            apply_to_tuple = (f"{define}:{as_name}",)
        else:
            if apply_to is None:
                raise ThemeError(
                    f"{origin}: style_rules[{i}] '{name}': `apply_to:` is required (or use `define:`)"
                )
            apply_to_tuple = _normalize_apply_to(apply_to, name=name, index=i, origin=origin)

        if not isinstance(select, dict):
            raise ThemeError(f"{origin}: style_rules[{i}] '{name}': select: must be a mapping")
        if not isinstance(style, dict):
            raise ThemeError(f"{origin}: style_rules[{i}] '{name}': style: must be a mapping")

        _check_selector_keys(select, name=name, index=i, origin=origin)

        out.append(Rule(
            name=name,
            define=define,
            as_name=as_name if isinstance(as_name, str) else None,
            apply_to=apply_to_tuple,
            select=select,
            style=style,
        ))
    return out


_TOKEN_RE = re.compile(r"^([a-z]+):([A-Za-z_][\w-]*)$")


def _normalize_apply_to(value: Any, *, name: str, index: int, origin: str) -> tuple[str, ...]:
    if isinstance(value, str):
        value_list: list[str] = [value]
    elif isinstance(value, list):
        value_list = [str(x) for x in value]
    else:
        raise ThemeError(
            f"{origin}: style_rules[{index}] '{name}': apply_to: must be a string or list of strings"
        )
    normalized: list[str] = []
    for t in value_list:
        if t in APPLY_TO_BASE:
            normalized.append(t)
            continue
        m = _TOKEN_RE.match(t)
        if m and m.group(1) in TOKEN_KINDS:
            normalized.append(t)
            continue
        raise ThemeError(
            f"{origin}: style_rules[{index}] '{name}': apply_to target '{t}' is not recognized. "
            f"Expected one of {sorted(APPLY_TO_BASE)} or a <kind>:<name> token "
            f"where kind is one of {sorted(TOKEN_KINDS)}."
        )
    return tuple(normalized)


def _check_selector_keys(select: dict[str, Any], *, name: str, index: int, origin: str) -> None:
    for k in select:
        if k in SELECTOR_KEYS:
            continue
        raise ThemeError(
            f"{origin}: style_rules[{index}] '{name}': unknown selector key '{k}'. "
            f"Recognized keys: {sorted(SELECTOR_KEYS)}"
        )


def _build_token_index(rules: list[Rule]) -> dict[str, list[Rule]]:
    """Build the token registry per design §6 Pass 1."""
    idx: dict[str, list[Rule]] = {}
    for rule in rules:
        for target in rule.apply_to:
            if ":" in target:
                idx.setdefault(target, []).append(rule)
    return idx


# ─── Public entry points ────────────────────────────────────────────────────


def load_theme_file(path: str | Path) -> UnifiedTheme:
    """Convenience wrapper around :func:`parse_theme` for callers that have a path."""
    return parse_theme(Path(path))


__all__ = [
    "Rule",
    "ThemeError",
    "UnifiedTheme",
    "load_theme_file",
    "parse_theme",
    "VALID_SECTIONS",
    "RETIRED_SECTIONS",
    "DEFINE_KINDS",
    "TOKEN_KINDS",
    "SELECTOR_KEYS",
]
