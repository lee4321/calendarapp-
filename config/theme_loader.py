"""Strict loader for version-3.0 themes.

``load_theme`` reads a theme (built-in name, file path, or already-parsed
mapping) and returns a :class:`config.theme_schema.Theme`.  The schema
dataclasses are the only defaults, so a theme may omit anything; what it does
say must be exactly right:

* A theme that does not declare ``theme.version: '3.0'`` stops the run with an
  :class:`UnsupportedThemeError` ("not supported").  There is no converter and
  no fallback.
* An unknown or misplaced key stops the run with a :class:`ThemeError` that
  names the key's path and lists the keys valid at that spot.
* A value of the wrong type, out of range, or naming an unregistered font does
  the same.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Union, get_args, get_origin

import yaml

from config import theme_schema as schema
from config.theme_schema import SELECTOR_KEYS, THEME_VERSION, BoxRole, IconRole, LineSpec, StyleRule, TextRole, Theme

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

BUILTIN_THEMES_DIR = Path(__file__).parent / "themes"

#: Role kinds a style rule may name in ``apply_to`` and the schema type that holds each.
_ROLE_KINDS: dict[str, tuple[type[DataclassInstance], type[DataclassInstance]]] = {
    "text": (TextRole, schema.TextRoles),
    "box": (BoxRole, schema.BoxRoles),
    "line": (LineSpec, schema.LineRoles),
    "icon": (IconRole, schema.IconRoles),
}


class ThemeError(ValueError):
    """A theme file is invalid."""


class UnsupportedThemeError(ThemeError):
    """The theme is not one this program can read."""


# ─── Loading ─────────────────────────────────────────────────────────────────


def list_builtin_themes() -> list[str]:
    return sorted(p.stem for p in BUILTIN_THEMES_DIR.glob("*.yaml"))


def load_theme(source: str | Path | Mapping[str, Any], *, font_registry: typing.Container[str] | None = None) -> Theme:
    """Parse *source* into a :class:`Theme`.

    *source* is a built-in theme name, a path to a ``.yaml`` file, or a mapping.
    *font_registry* is the set of font names a theme may use; it defaults to the
    program's ``FONT_REGISTRY``.
    """
    data, label = _read(source)
    _check_version(data, label)
    theme = _parse(Theme, data, "", font_registry=_registry(font_registry))
    _check_style_rules(theme)
    _check_details_columns(theme)
    return theme


def _read(source: str | Path | Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if isinstance(source, Mapping):
        meta = source.get("theme")
        return dict(source), str(meta.get("name", "<mapping>")) if isinstance(meta, Mapping) else "<mapping>"
    text = str(source)
    path = Path(text)
    if not text.endswith((".yaml", ".yml")) and not path.is_file():
        path = BUILTIN_THEMES_DIR / f"{text}.yaml"
    if not path.is_file():
        raise ThemeError(f"theme '{text}' not found (built-in themes: {', '.join(list_builtin_themes()) or 'none'})")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ThemeError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ThemeError(f"{path}: a theme must be a YAML mapping")
    return data, path.stem


def _check_version(data: Mapping[str, Any], label: str) -> None:
    meta = data.get("theme")
    version = meta.get("version") if isinstance(meta, Mapping) else None
    name = meta.get("name", label) if isinstance(meta, Mapping) else label
    if str(version) != THEME_VERSION:
        found = f"declares version '{version}'" if version is not None else "declares no version"
        raise UnsupportedThemeError(
            f"theme '{name}' is not supported: it {found}, and this program reads only version "
            f"'{THEME_VERSION}' themes (see config/themes/demonstration.yaml for the supported keys)"
        )


def _registry(font_registry: typing.Container[str] | None) -> typing.Container[str]:
    if font_registry is not None:
        return font_registry
    from config.config import FONT_REGISTRY

    return FONT_REGISTRY


# ─── Schema-driven parsing ───────────────────────────────────────────────────

_NO_VALUE = object()
_hints_cache: dict[type, dict[str, Any]] = {}


def _hints(cls: type) -> dict[str, Any]:
    if cls not in _hints_cache:
        _hints_cache[cls] = typing.get_type_hints(cls)
    return _hints_cache[cls]


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _parse(cls: type[DataclassInstance], data: Any, path: str, *, font_registry: typing.Container[str]) -> Any:
    """Build a *cls* from mapping *data*, strictly."""
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        raise ThemeError(f"theme key '{path or '<top level>'}' must be a mapping, not {_describe(data)}")
    fields = {f.name: f for f in dataclasses.fields(cls)}
    unknown = [str(k) for k in data if k not in fields]
    if unknown:
        where = f"inside '{path}'" if path else "at the top level"
        bad = ", ".join(f"'{_join(path, k)}'" for k in unknown)
        verb = "is" if len(unknown) == 1 else "are"
        noun = "key" if len(unknown) == 1 else "keys"
        raise ThemeError(f"theme {noun} {bad} {verb} not supported {where}; valid keys here: {', '.join(fields)}")
    hints = _hints(cls)
    kwargs: dict[str, Any] = {}
    for name, value in data.items():
        key_path = _join(path, name)
        value = _coerce(hints[name], value, key_path, font_registry=font_registry)
        if fields[name].metadata.get("font") and value is not None and value not in font_registry:
            raise ThemeError(f"theme key '{key_path}': font '{value}' is not registered (see the `fonts` command)")
        kwargs[name] = value
    missing = [
        n
        for n, f in fields.items()
        if n not in kwargs and f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    ]
    if missing:
        raise ThemeError(f"theme section '{path or '<top level>'}' is missing required key(s): {', '.join(missing)}")
    try:
        return cls(**kwargs)
    except ValueError as exc:
        raise ThemeError(f"theme section '{path or '<top level>'}': {exc}") from exc


def _describe(value: Any) -> str:
    return f"{type(value).__name__} {value!r}"[:60]


def _coerce(tp: Any, value: Any, path: str, *, font_registry: typing.Container[str]) -> Any:
    """Convert *value* to type *tp* or raise ThemeError naming *path*."""
    origin = get_origin(tp)

    if tp is Any:
        return value
    if tp is type(None):
        if value is None:
            return None
        raise _wrong(path, "null", value)
    if origin in (Union, types.UnionType):
        arms = get_args(tp)
        if value is None:
            if type(None) in arms:
                return None
            raise _wrong(path, _arm_names(arms), value)
        # A mapping meant for a dataclass arm is parsed there, so its errors name the bad inner key.
        if isinstance(value, Mapping):
            for arm in arms:
                if dataclasses.is_dataclass(arm):
                    return _parse(arm, value, path, font_registry=font_registry)
        real = [a for a in arms if a is not type(None)]
        for arm in real:
            # A bare number is text only where text is the sole choice; in `text | list` it is a mistake.
            if arm is str and len(real) > 1 and isinstance(value, (int, float)) and not isinstance(value, bool):
                continue
            try:
                return _coerce(arm, value, path, font_registry=font_registry)
            except ThemeError:
                continue
        raise _wrong(path, _arm_names(arms), value)
    if origin is Literal:
        choices = get_args(tp)
        if any(value == c and type(value) is type(c) for c in choices):
            return value
        raise ThemeError(f"theme key '{path}' must be one of {', '.join(map(str, choices))}, not {value!r}")
    if origin is list:
        (item,) = get_args(tp)
        if not isinstance(value, list):
            raise _wrong(path, "a list", value)
        return [_coerce(item, v, f"{path}[{i}]", font_registry=font_registry) for i, v in enumerate(value)]
    if origin is dict:
        key_t, val_t = get_args(tp)
        if not isinstance(value, Mapping):
            raise _wrong(path, "a mapping", value)
        return {
            str(_coerce(key_t, k, path, font_registry=font_registry)) if key_t is str else k: _coerce(
                val_t, v, _join(path, str(k)), font_registry=font_registry
            )
            for k, v in value.items()
        }
    if dataclasses.is_dataclass(tp):
        return _parse(tp, value, path, font_registry=font_registry)
    if tp is bool:
        if isinstance(value, bool):
            return value
        raise _wrong(path, "true or false", value)
    if tp is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise _wrong(path, "a whole number", value)
    if tp is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        raise _wrong(path, "a number", value)
    if tp is str:
        if isinstance(value, str):
            return value
        # YAML turns 01 / 2026 / 1.5 into numbers; a key that wants text gets its digits.
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        raise _wrong(path, "text", value)
    raise TypeError(f"theme schema: unsupported annotation {tp!r} at '{path}'")  # a schema bug, not a theme error


def _arm_names(arms: tuple[Any, ...]) -> str:
    names = {
        str: "text",
        int: "a whole number",
        float: "a number",
        bool: "true or false",
        list: "a list",
        dict: "a mapping",
    }
    out = []
    for a in arms:
        if a is type(None):
            out.append("null")
        else:
            out.append(names.get(get_origin(a) or a, getattr(a, "__name__", str(a))))
    return " or ".join(out)


def _wrong(path: str, expected: str, value: Any) -> ThemeError:
    return ThemeError(f"theme key '{path}' must be {expected}, not {_describe(value)}")


# ─── Style rules ─────────────────────────────────────────────────────────────


def _check_style_rules(theme: Theme) -> None:
    """Validate what the schema types cannot: selector keys and role references."""
    for i, rule in enumerate(theme.style_rules):
        where = f"style_rules[{i}] ('{rule.name}')"
        _check_rule(rule, where)


def _check_rule(rule: StyleRule, where: str) -> None:
    bad = sorted(set(rule.select) - SELECTOR_KEYS)
    if bad:
        raise ThemeError(
            f"theme key '{where}.select' has unsupported selector(s) {', '.join(bad)}; "
            f"valid selectors: {', '.join(sorted(SELECTOR_KEYS))}"
        )
    targets = [rule.apply_to] if isinstance(rule.apply_to, str) else list(rule.apply_to)
    if not targets:
        raise ThemeError(f"theme key '{where}.apply_to' must name at least one role")
    allowed: set[str] = set()
    for target in targets:
        kind, _, role = target.partition(":")
        kinds = _ROLE_KINDS.get(kind)
        if kinds is None or not role:
            raise ThemeError(
                f"theme key '{where}.apply_to': '{target}' is not a role reference; "
                f"use <kind>:<role> with kind one of {', '.join(_ROLE_KINDS)}"
            )
        spec, holder = kinds
        roles = {f.name for f in dataclasses.fields(holder)}
        if role not in roles:
            raise ThemeError(
                f"theme key '{where}.apply_to': there is no {kind} role '{role}'; roles: {', '.join(sorted(roles))}"
            )
        allowed |= {f.name for f in dataclasses.fields(spec)}
    extra = sorted(set(rule.style) - allowed)
    if extra:
        raise ThemeError(
            f"theme key '{where}.style' has key(s) {', '.join(extra)} that the targeted role does not have; "
            f"valid keys: {', '.join(sorted(allowed))}"
        )


def _check_details_columns(theme: Theme) -> None:
    """A details column must name a field some row carries; ``details.csv.columns`` may be ``exportdata``.

    The details document exists to be complete, so a misspelt field is an error
    naming the valid ones, not a column that stays empty.
    """
    from renderers.details_fields import EXCEPTION_FIELDS, HOLIDAY_FIELDS, event_fields, invalid_fields

    md = theme.details.markdown
    checks = (
        ("details.markdown.columns", md.columns, event_fields()),
        ("details.markdown.exception_columns", md.exception_columns, EXCEPTION_FIELDS),
        ("details.markdown.holiday_columns", md.holiday_columns, HOLIDAY_FIELDS),
        ("details.csv.columns", theme.details.csv.columns, event_fields()),
    )
    for where, value, valid in checks:
        if where == "details.csv.columns" and isinstance(value, str):
            if value.strip().lower() != "exportdata":
                raise ThemeError(f"theme key '{where}' must be 'exportdata' or a list of column entries; got {value!r}")
            continue
        bad = invalid_fields(value, valid)
        if bad:
            raise ThemeError(
                f"theme key '{where}' names unknown field(s): {', '.join(bad)}; valid fields: {', '.join(sorted(valid))}"
            )
