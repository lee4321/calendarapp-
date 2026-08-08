"""Every band a shipped theme references must exist in its own catalog.

Visualizers name bands (`blockplan.top_bands`, `compact_plan.bands`,
`gantt.top_bands`, …) and the theme's top-level `time_bands:` catalog
defines them. A reference to a band that was renamed or removed is only a
warning at run time — the band is silently dropped and the chart renders
short a row — so nothing failed when `default.yaml`'s catalog was rewritten
and `pi`, `sprint` and `week` disappeared out from under three visualizers.

These tests close that gap by driving the real `ThemeEngine`, so they stay
honest if the resolution rules change.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"
THEME_FILES = sorted(THEMES_DIR.glob("*.yaml"))

#: Substring the engine logs when a placement names a band it cannot find.
_UNKNOWN = "unknown time_band"


def test_the_theme_directory_was_found():
    """A glob that matched nothing would make every test below vacuous."""
    assert len(THEME_FILES) >= 5


@pytest.mark.parametrize("theme_path", THEME_FILES, ids=lambda p: p.name)
def test_every_band_reference_resolves(theme_path: Path, caplog):
    engine = ThemeEngine()
    config = CalendarConfig()

    with caplog.at_level(logging.WARNING):
        engine.load(theme_path.stem)
        engine.apply(config)

    unknown = [
        record.getMessage()
        for record in caplog.records
        if _UNKNOWN in record.getMessage()
    ]
    assert not unknown, (
        f"{theme_path.name} references bands its time_bands catalog does not "
        "define:\n  " + "\n  ".join(sorted(set(unknown)))
    )


@pytest.mark.parametrize("theme_path", THEME_FILES, ids=lambda p: p.name)
def test_a_theme_that_names_bands_ships_a_catalog(theme_path: Path):
    """The failure mode that bit us: references with nowhere to resolve."""
    raw = yaml.safe_load(theme_path.read_text()) or {}
    catalog = raw.get("time_bands") or {}

    named: list[str] = []
    for section, key, _field in ThemeEngine._BAND_PLACEMENTS:
        placements = (raw.get(section) or {}).get(key)
        if not isinstance(placements, list):
            continue
        for entry in placements:
            if isinstance(entry, str):
                named.append(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("band"), str):
                named.append(entry["band"])

    if named:
        assert catalog, (
            f"{theme_path.name} names bands {sorted(set(named))} but has no "
            "time_bands catalog"
        )
        missing = sorted({name for name in named if name not in catalog})
        assert not missing, f"{theme_path.name}: {missing} not in its catalog"


def test_the_guard_catches_a_dangling_reference(tmp_path, caplog):
    """Prove the guard fails when a reference really is broken."""
    broken = yaml.safe_load((THEMES_DIR / "basic.yaml").read_text())
    broken.setdefault("compact_plan", {})["bands"] = ["no_such_band"]
    path = THEMES_DIR / "_guard_probe.yaml"
    path.write_text(yaml.safe_dump(broken, sort_keys=False))

    try:
        with caplog.at_level(logging.WARNING):
            engine = ThemeEngine()
            engine.load(path.stem)
            engine.apply(CalendarConfig())
        assert any(_UNKNOWN in r.getMessage() for r in caplog.records)
    finally:
        path.unlink()


def test_inline_band_definitions_need_no_catalog_entry(caplog):
    """A placement carrying `unit:` defines itself and must not warn."""
    config = CalendarConfig()
    config.gantt_top_time_bands = [{"label": "Inline", "unit": "month"}]

    with caplog.at_level(logging.WARNING):
        ThemeEngine().apply(config)

    assert not [r for r in caplog.records if _UNKNOWN in r.getMessage()]
