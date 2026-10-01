"""
Element catalog loader.

The catalog (config/element_catalog.yaml) maps every ec-* CSS class produced
by the renderers to the style token (text:<name>, box:<name>, line:<name>,
icon:<name>) that supplies its visual style.  It is the single source of
truth for those bindings — themes no longer need to repeat them.

Roles are defined only in the theme and the schema defaults (``config/theme_schema.py``);
the catalog says which role styles which element.

Two functions matter to callers:

* :func:`load_catalog` returns the parsed catalog as a dict of
  :class:`CatalogEntry` records.  Cached after first call.

:func:`iter_required_tokens` answers "which tokens does a theme have to
``define:`` to cover a given visualizer?" — used by the validator and by
documentation generators.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_CATALOG_PATH: Path = Path(__file__).resolve().parent / "element_catalog.yaml"

_VALID_KINDS: frozenset[str] = frozenset({"text", "box", "line", "icon"})


def _role_names() -> dict[str, frozenset[str]]:
    import dataclasses

    from config.theme_schema import BoxRoles, IconRoles, LineRoles, TextRoles

    return {
        kind: frozenset(f.name for f in dataclasses.fields(cls))
        for kind, cls in (("text", TextRoles), ("box", BoxRoles), ("line", LineRoles), ("icon", IconRoles))
    }


_ROLES = _role_names()


@dataclass(frozen=True)
class CatalogEntry:
    """One row of element_catalog.yaml."""

    class_name: str  # "ec-heading"
    kind: str  # "text" | "box" | "line" | "icon"
    token: str  # token name within the kind ("heading")
    scope: tuple[str, ...]  # visualizers that emit this class
    description: str = ""


_catalog_cache: dict[str, CatalogEntry] | None = None
_modifiers_cache: tuple[str, ...] | None = None


def load_catalog() -> dict[str, CatalogEntry]:
    """Return the parsed catalog as ``{ec-class: CatalogEntry}``.

    Cached on first call.  Validates that every entry's ``kind`` is one of
    text/box/line/icon and that its token is a role of the schema.
    """
    global _catalog_cache, _modifiers_cache
    if _catalog_cache is not None:
        return _catalog_cache

    raw = yaml.safe_load(_CATALOG_PATH.read_text()) or {}
    elements = raw.get("elements") or {}
    if not isinstance(elements, dict):
        raise ValueError(f"{_CATALOG_PATH}: top-level 'elements' must be a mapping")

    catalog: dict[str, CatalogEntry] = {}
    for class_name, body in elements.items():
        if not isinstance(class_name, str) or not class_name.startswith("ec-"):
            raise ValueError(f"{_CATALOG_PATH}: element key {class_name!r} must start with 'ec-'")
        if not isinstance(body, dict):
            raise ValueError(f"{_CATALOG_PATH}: {class_name}: entry must be a mapping")
        kind = body.get("kind")
        token = body.get("token")
        if kind not in _VALID_KINDS:
            raise ValueError(f"{_CATALOG_PATH}: {class_name}: kind must be one of {sorted(_VALID_KINDS)}, got {kind!r}")
        if not isinstance(token, str) or not token:
            raise ValueError(f"{_CATALOG_PATH}: {class_name}: token must be a non-empty string")
        if token not in _ROLES.get(kind, ()):
            raise ValueError(
                f"{_CATALOG_PATH}: {class_name} references {kind}:{token}, which is not a role of the schema"
            )
        scope = body.get("scope") or []
        if isinstance(scope, str):
            scope_t = (scope,)
        elif isinstance(scope, list):
            scope_t = tuple(str(s) for s in scope)
        else:
            raise ValueError(f"{_CATALOG_PATH}: {class_name}: scope must be a string or list")
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
    return [e for e in catalog.values() if "all" in e.scope or visualizer in e.scope]


def _reset_caches_for_testing() -> None:
    """Test hook: force the next load to re-read the YAML files."""
    global _catalog_cache, _modifiers_cache
    _catalog_cache = None
    _modifiers_cache = None


__all__ = [
    "CatalogEntry",
    "entries_for_visualizer",
    "iter_required_tokens",
    "load_catalog",
    "modifier_classes",
]
