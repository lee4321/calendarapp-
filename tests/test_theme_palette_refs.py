"""
``palette:NAME:INDEX`` references inside a theme's ``style_rules`` must be
resolved before rendering, like the ones in plain config fields.

The unified theme keeps each rule's style as the YAML wrote it, and
``_resolve_palette_overrides`` used to rewrite only CalendarConfig's string
fields, so a token such as ``color: palette:Blues:6`` reached the SVG
verbatim (an invalid color).  These tests pin the resolution of define-token
styles, apply_to rule styles (including list-valued fills), and the
ThemeStyles CSS built from them — and that the cached YAML is not mutated.
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
import yaml

from config.palette_resolver import _resolve_palette_overrides, _resolve_theme_palette_refs
from config.unified_theme import parse_theme
from shared.db_access import CalendarDB

if TYPE_CHECKING:
    from config.config import CalendarConfig

REPO_ROOT = Path(__file__).resolve().parent.parent
PALETTE = "Blues"


class _StubDB:
    colors: tuple[str, ...] = ("#000001", "#000002", "#000003", "#000004")

    def get_palette(self, name: str) -> list[str] | None:
        return list(self.colors) if name.lower() == "blues" else None

    def sample_palette_n(self, name: str, n: int) -> list[str] | None:
        colors = self.get_palette(name)
        return [colors[i % len(colors)] for i in range(n)] if colors else None


STUB_DB = cast("CalendarDB", _StubDB())


def _theme_only_config(theme: object) -> CalendarConfig:
    return cast("CalendarConfig", SimpleNamespace(theme=theme, theme_styles=None))


def _raw_theme() -> dict:
    return {
        "style_rules": [
            {"name": "define text:heading", "define": "text", "as": "heading", "style": {"color": "palette:Blues:1"}},
            {
                "name": "define box:cell",
                "define": "box",
                "as": "cell",
                "style": {"fill": "palette:Blues:0", "stroke": "black"},
            },
            {
                "name": "event fill",
                "apply_to": ["box:event", "box:duration"],
                "select": {"resource_group": "A"},
                "style": {"fill": "palette:Blues:2"},
            },
            {
                "name": "sprint vline",
                "apply_to": "box:vline",
                "select": {"band": "Sprint"},
                "style": {"fill": ["palette:Blues:3", "none"]},
            },
        ]
    }


def _palette_theme(path: Path) -> None:
    """basic.yaml with every style_rules color/fill/stroke replaced by palette refs."""
    raw = yaml.safe_load((REPO_ROOT / "config" / "themes" / "basic.yaml").read_text())
    for i, rule in enumerate(raw["style_rules"]):
        style = rule.get("style") or {}
        for key in ("color", "fill", "stroke"):
            if isinstance(style.get(key), str) and style[key] != "none":
                style[key] = f"palette:{PALETTE}:{i % 9}"
    raw["style_rules"].append(
        {
            "name": "event fill from palette",
            "apply_to": ["box:event", "box:duration"],
            "style": {"fill": f"palette:{PALETTE}:7"},
        }
    )
    path.write_text(yaml.safe_dump(raw, sort_keys=False))


def test_style_rule_refs_resolve_without_mutating_the_yaml() -> None:
    raw = _raw_theme()
    pristine = copy.deepcopy(raw)
    theme = parse_theme(raw)
    _resolve_theme_palette_refs(_theme_only_config(theme), STUB_DB)

    assert theme.resolve_token("text:heading")["color"] == "#000002"
    assert theme.resolve_token("box:cell") == {"fill": "#000001", "stroke": "black"}
    [event_rule] = theme.find_rules("box:event", {"resource_group": "A"})
    assert event_rule.style["fill"] == "#000003"
    [vline_rule] = theme.find_rules("box:vline", {"band": "Sprint"})
    assert vline_rule.style["fill"] == ["#000004", "none"]
    # The raw list each visualizer's StyleEngine reads is resolved too.
    raw_styles = [r["style"] for r in theme.sections["style_rules"]]
    assert raw_styles[2] == {"fill": "#000003"}
    assert raw_styles[3] == {"fill": ["#000004", "none"]}
    assert raw == pristine, "the parsed YAML dicts must not be edited in place"


def test_unknown_palette_leaves_the_reference() -> None:
    theme = parse_theme(
        {"style_rules": [{"name": "t", "define": "line", "as": "grid", "style": {"color": "palette:Nope:1"}}]}
    )
    _resolve_theme_palette_refs(_theme_only_config(theme), STUB_DB)
    assert theme.resolve_token("line:grid")["color"] == "palette:Nope:1"


def test_theme_styles_css_is_resolved(tmp_path: Path) -> None:
    from config.config import CalendarConfig
    from config.theme_engine import ThemeEngine

    theme_path = tmp_path / "palette_refs.yaml"
    _palette_theme(theme_path)
    config = CalendarConfig()
    engine = ThemeEngine()
    engine.load(str(theme_path))
    engine.apply(config)
    assert "palette:" in config.theme_styles.css

    _resolve_palette_overrides(config, STUB_DB)

    assert "palette:" not in config.theme_styles.css
    assert any(c in config.theme_styles.css for c in _StubDB.colors)


@pytest.mark.parametrize("subcommand", ["weekly", "compactplan", "timeline"])
def test_rendered_svg_has_no_palette_refs(subcommand: str, tmp_path: Path) -> None:
    palette = CalendarDB(str(REPO_ROOT / "calendar.db")).get_palette(PALETTE)
    if not palette:
        pytest.skip(f"calendar.db has no {PALETTE!r} palette")
    theme_path = tmp_path / "palette_refs.yaml"
    _palette_theme(theme_path)
    stem = f"_palette_refs_{subcommand}"
    run_folder = REPO_ROOT / "output" / stem
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    cmd = [
        sys.executable,
        str(REPO_ROOT / "ecalendar.py"),
        subcommand,
        "20260309",
        "20260424",
        "--theme",
        str(theme_path),
        "--outputfile",
        f"{stem}.svg",
        "--quiet",
    ]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        svg = (run_folder / f"{stem}.svg").read_text(encoding="utf-8")
        assert "palette:" not in svg
        assert any(c.lower() in svg.lower() for c in palette), "no resolved palette color reached the SVG"
    finally:
        shutil.rmtree(run_folder, ignore_errors=True)
