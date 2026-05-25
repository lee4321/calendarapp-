"""
Element catalog loader.

The catalog (config/element_catalog.yaml) maps every ec-* CSS class produced
by the renderers to the style token (text:<name>, box:<name>, line:<name>,
icon:<name>) that supplies its visual style.  It is the single source of
truth for those bindings — themes no longer need to repeat them.

Two functions matter to callers:

* :func:`load_catalog` returns the parsed catalog as a dict of
  :class:`CatalogEntry` records.  Cached after first call.
* :func:`load_default_tokens` returns the fallback ``{kind: {name: dict}}``
  used when a theme omits a token referenced by the catalog.  Cached.

:func:`iter_required_tokens` answers "which tokens does a theme have to
``define:`` to cover a given visualizer?" — used by the validator and by
documentation generators.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

_CATALOG_PATH: Path = Path(__file__).resolve().parent / "element_catalog.yaml"
_DEFAULTS_PATH: Path = Path(__file__).resolve().parent / "element_catalog_defaults.yaml"

_VALID_KINDS: frozenset[str] = frozenset({"text", "box", "line", "icon"})


@dataclass(frozen=True)
class CatalogEntry:
    """One row of element_catalog.yaml."""

    class_name: str                # "ec-heading"
    kind: str                      # "text" | "box" | "line" | "icon"
    token: str                     # token name within the kind ("heading")
    scope: tuple[str, ...]         # visualizers that emit this class
    description: str = ""

    @property
    def token_ref(self) -> str:
        """Return the ``kind:name`` form (matches ``style.use`` syntax)."""
        return f"{self.kind}:{self.token}"


_catalog_cache: dict[str, CatalogEntry] | None = None
_defaults_cache: dict[str, dict[str, dict]] | None = None
_modifiers_cache: tuple[str, ...] | None = None


def load_catalog() -> dict[str, CatalogEntry]:
    """Return the parsed catalog as ``{ec-class: CatalogEntry}``.

    Cached on first call.  Validates that every entry's ``kind`` is one of
    text/box/line/icon and that every (kind, token) pair has a fallback
    definition in element_catalog_defaults.yaml.
    """
    global _catalog_cache, _modifiers_cache
    if _catalog_cache is not None:
        return _catalog_cache

    raw = yaml.safe_load(_CATALOG_PATH.read_text()) or {}
    elements = raw.get("elements") or {}
    if not isinstance(elements, dict):
        raise ValueError(
            f"{_CATALOG_PATH}: top-level 'elements' must be a mapping"
        )

    defaults = load_default_tokens()
    catalog: dict[str, CatalogEntry] = {}
    for class_name, body in elements.items():
        if not isinstance(class_name, str) or not class_name.startswith("ec-"):
            raise ValueError(
                f"{_CATALOG_PATH}: element key {class_name!r} must start with 'ec-'"
            )
        if not isinstance(body, dict):
            raise ValueError(
                f"{_CATALOG_PATH}: {class_name}: entry must be a mapping"
            )
        kind = body.get("kind")
        token = body.get("token")
        if kind not in _VALID_KINDS:
            raise ValueError(
                f"{_CATALOG_PATH}: {class_name}: kind must be one of {sorted(_VALID_KINDS)}, "
                f"got {kind!r}"
            )
        if not isinstance(token, str) or not token:
            raise ValueError(
                f"{_CATALOG_PATH}: {class_name}: token must be a non-empty string"
            )
        if token not in defaults.get(kind, {}):
            raise ValueError(
                f"{_CATALOG_PATH}: {class_name} references {kind}:{token} but no "
                f"fallback is defined in element_catalog_defaults.yaml"
            )
        scope = body.get("scope") or []
        if isinstance(scope, str):
            scope_t = (scope,)
        elif isinstance(scope, list):
            scope_t = tuple(str(s) for s in scope)
        else:
            raise ValueError(
                f"{_CATALOG_PATH}: {class_name}: scope must be a string or list"
            )
        description = str(body.get("description") or "")
        catalog[class_name] = CatalogEntry(
            class_name=class_name,
            kind=kind,
            token=token,
            scope=scope_t,
            description=description,
        )

    mods = raw.get("modifiers") or []
    _modifiers_cache = tuple(str(m) for m in mods) if isinstance(mods, list) else ()

    _catalog_cache = catalog
    return catalog


def load_default_tokens() -> dict[str, dict[str, dict]]:
    """Return fallback tokens as ``{kind: {name: style_dict}}``.  Cached."""
    global _defaults_cache
    if _defaults_cache is not None:
        return _defaults_cache
    raw = yaml.safe_load(_DEFAULTS_PATH.read_text()) or {}
    result: dict[str, dict[str, dict]] = {}
    for kind in _VALID_KINDS:
        section = raw.get(kind) or {}
        if not isinstance(section, dict):
            raise ValueError(
                f"{_DEFAULTS_PATH}: section {kind!r} must be a mapping"
            )
        kind_tokens: dict[str, dict] = {}
        for name, body in section.items():
            if not isinstance(body, dict):
                raise ValueError(
                    f"{_DEFAULTS_PATH}: {kind}:{name}: style body must be a mapping"
                )
            kind_tokens[str(name)] = dict(body)
        result[kind] = kind_tokens
    _defaults_cache = result
    return result


def modifier_classes() -> tuple[str, ...]:
    """Return the list of modifier classes (ec-holiday, ec-current-day, ...)."""
    load_catalog()  # populates _modifiers_cache
    return _modifiers_cache or ()


def iter_required_tokens(visualizer: str | None = None) -> set[tuple[str, str]]:
    """Return the set of ``(kind, token_name)`` pairs the given visualizer needs.

    With ``visualizer=None``, returns the union across every visualizer.
    A catalog entry whose ``scope`` includes ``"all"`` matches every
    visualizer.
    """
    catalog = load_catalog()
    required: set[tuple[str, str]] = set()
    for entry in catalog.values():
        if visualizer is None or "all" in entry.scope or visualizer in entry.scope:
            required.add((entry.kind, entry.token))
    return required


def entries_for_visualizer(visualizer: str | None = None) -> list[CatalogEntry]:
    """Return catalog entries whose scope matches ``visualizer``."""
    catalog = load_catalog()
    if visualizer is None:
        return list(catalog.values())
    return [
        e for e in catalog.values()
        if "all" in e.scope or visualizer in e.scope
    ]


def _reset_caches_for_testing() -> None:
    """Test hook: force the next load to re-read the YAML files."""
    global _catalog_cache, _defaults_cache, _modifiers_cache
    _catalog_cache = None
    _defaults_cache = None
    _modifiers_cache = None


__all__ = [
    "CatalogEntry",
    "entries_for_visualizer",
    "iter_required_tokens",
    "load_catalog",
    "load_default_tokens",
    "modifier_classes",
]
