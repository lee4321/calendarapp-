"""Tests for FONT_REGISTRY — the fonts/ scan behind get_font_path()."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.config import FONT_REGISTRY, get_font_path

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


def test_every_font_file_is_registered() -> None:
    """Every TTF/OTF under fonts/ must be reachable by name.

    The scan used a case-sensitive `*.ttf` glob, which silently skipped
    `TECHNCL.TTF` — the file shipped but no theme could reference it.
    """
    on_disk = {
        p.stem
        for p in FONTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".ttf", ".otf")
    }
    assert on_disk - set(FONT_REGISTRY) == set()


def test_uppercase_extension_is_registered() -> None:
    """Guards the case-insensitive glob specifically."""
    uppercase = [
        p for p in FONTS_DIR.iterdir()
        if p.is_file() and p.suffix in (".TTF", ".OTF")
    ]
    if not uppercase:
        pytest.skip("no uppercase-extension font files in fonts/")
    for path in uppercase:
        assert get_font_path(path.stem) == f"fonts/{path.name}"


def test_every_registered_path_exists() -> None:
    missing = [name for name, rel in FONT_REGISTRY.items() if not Path(rel).exists()]
    assert not missing, f"FONT_REGISTRY points at missing files: {missing}"


def test_unknown_font_raises_key_error() -> None:
    with pytest.raises(KeyError, match="not found in FONT_REGISTRY"):
        get_font_path("NotoSans-Condensed")


def test_empty_font_name_returns_empty_string() -> None:
    assert get_font_path("") == ""
