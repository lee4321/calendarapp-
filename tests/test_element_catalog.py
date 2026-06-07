"""Tests for the built-in element catalog (config/element_catalog.yaml)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import element_catalog


@pytest.fixture(autouse=True)
def _reset_catalog_caches():
    """Reload the catalog from disk for each test (in case a test mutates it)."""
    element_catalog._reset_caches_for_testing()
    yield
    element_catalog._reset_caches_for_testing()


def test_catalog_loads_with_expected_kinds() -> None:
    catalog = element_catalog.load_catalog()
    assert catalog, "catalog must contain entries"
    for class_name, entry in catalog.items():
        assert class_name.startswith("ec-"), class_name
        assert entry.kind in {"text", "box", "line", "icon"}, entry.kind
        assert entry.token, class_name


def test_every_token_referenced_has_a_default() -> None:
    catalog = element_catalog.load_catalog()
    defaults = element_catalog.load_default_tokens()
    for entry in catalog.values():
        assert entry.token in defaults[entry.kind], (
            f"{entry.class_name} references {entry.kind}:{entry.token} but the "
            "fallback is not declared in element_catalog_defaults.yaml"
        )


# Discovered ec-* classes that are modifiers, not standalone elements.
# Modifier classes are validated against the catalog's modifiers: list.
_KNOWN_NON_ELEMENT_CLASSES: set[str] = {
    "ec-adjacent",
    "ec-current-day",
    "ec-holiday",
    "ec-nonworkday",
    # PIT group wrapper + callout side modifiers (also in catalog modifiers:).
    "ec-pit-axis-group",
    "ec-pit-side-primary",
    "ec-pit-side-secondary",
}


def _grep_ec_classes() -> set[str]:
    """Return every `ec-*` literal that appears in renderer / visualizer code."""
    pattern = re.compile(r'"(ec-[a-z][a-z0-9-]*)"')
    seen: set[str] = set()
    for sub in ("visualizers", "renderers"):
        root = REPO_ROOT / sub
        for path in root.rglob("*.py"):
            for line in path.read_text().splitlines():
                for m in pattern.finditer(line):
                    seen.add(m.group(1))
    return seen


def test_every_ec_class_in_renderers_appears_in_catalog() -> None:
    """A new `ec-*` literal in a renderer must come with a catalog entry."""
    catalog = element_catalog.load_catalog()
    modifiers = set(element_catalog.modifier_classes())
    code_classes = _grep_ec_classes()
    missing = code_classes - set(catalog) - modifiers - _KNOWN_NON_ELEMENT_CLASSES
    assert not missing, (
        "These ec-* classes are used in code but not declared in "
        "config/element_catalog.yaml (or modifiers / known-non-element):\n  "
        + "\n  ".join(sorted(missing))
    )


def test_required_tokens_filters_by_visualizer() -> None:
    weekly = element_catalog.iter_required_tokens("weekly")
    timeline = element_catalog.iter_required_tokens("timeline")
    assert weekly, "weekly should require at least one token"
    assert timeline, "timeline should require at least one token"
    # day_number is a weekly token; callout is a timeline token.
    assert ("text", "day_number") in weekly
    assert ("box", "callout") in timeline
    # The "all" scope rule means heading is required by both.
    assert ("text", "heading") in weekly
    assert ("text", "heading") in timeline


def test_entries_for_visualizer() -> None:
    weekly = {e.class_name for e in element_catalog.entries_for_visualizer("weekly")}
    assert "ec-day-number" in weekly
    assert "ec-heading" in weekly  # scope: all
    # ec-callout-box is timeline-only.
    assert "ec-callout-box" not in weekly


def test_modifier_classes_present() -> None:
    mods = set(element_catalog.modifier_classes())
    assert mods, "modifiers list must be populated"
    assert mods.issubset(_KNOWN_NON_ELEMENT_CLASSES | {"ec-current-day"})
