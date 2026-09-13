"""The ``excelblockplan:`` theme section styles the excelblockplan workbook.

It replaced the ``excelheader:`` section when the excelheader command was
removed.  A theme still using the old name is rejected with a pointer to the
new one, and tools/migrate_theme.py renames it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config import theme_engine, unified_theme
from config.config import CalendarConfig
from config.theme_engine import ThemeEngine
from tools.migrate_theme import convert_theme

_THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"
_META = {"theme": {"name": "Excel", "version": "3.0"}}


def _engine_for(tmp_path: Path, data: dict) -> ThemeEngine:
    path = tmp_path / "excel.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    engine = ThemeEngine()
    engine.load(str(path))
    return engine


def test_section_keys_reach_the_config(tmp_path):
    data = {
        **_META,
        "time_bands": {"month": {"unit": "month", "label": "Month"}},
        "excelblockplan": {
            "font_name": "Arial",
            "font_size": 11,
            "header_label_align_h": "left",
            "weekend_fill_color": "#DDDDDD",
            "top_bands": ["month"],
        },
    }
    config = _engine_for(tmp_path, data).apply(CalendarConfig())

    assert config.excelblockplan_font == "Arial"
    assert config.excelblockplan_font_size == 11
    assert config.excelblockplan_header_label_align_h == "left"
    assert config.excelblockplan_weekend_fill_color == "#DDDDDD"
    assert [b["label"] for b in config.excelblockplan_top_time_bands] == ["Month"]


def test_heading_labels_default_to_right_aligned():
    assert CalendarConfig().excelblockplan_header_label_align_h == "right"


def test_theme_engine_rejects_the_old_section_name(tmp_path):
    engine = _engine_for(tmp_path, {**_META, "excelheader": {"font_size": 9}})
    with pytest.raises(theme_engine.ThemeError, match="excelblockplan"):
        engine.apply(CalendarConfig())


def test_unified_parser_names_the_replacement_section():
    with pytest.raises(unified_theme.ThemeError, match="renamed to 'excelblockplan'"):
        unified_theme.parse_theme({**_META, "excelheader": {}})
    unified_theme.parse_theme({**_META, "excelblockplan": {}})


def test_migration_renames_the_section():
    converted = convert_theme(
        {**_META, "excelheader": {"font_name": "Calibri", "font_size": 9}}
    )
    assert "excelheader" not in converted
    assert converted["excelblockplan"]["font_name"] == "Calibri"


@pytest.mark.parametrize("name", ["basic", "SAMPLE", "TJX"])
def test_shipped_themes_use_the_new_section_name(name):
    raw = yaml.safe_load((_THEMES_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    assert "excelheader" not in raw
    assert "excelblockplan" in raw
