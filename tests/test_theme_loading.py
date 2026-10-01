"""Choosing and loading the run's theme."""

from __future__ import annotations

import pytest

from cli.config_assembly import load_run_theme
from config.config import create_calendar_config
from config.theme_loader import ThemeError, UnsupportedThemeError, list_builtin_themes


def test_the_builtin_themes_include_default_and_the_demonstration():
    assert {"default", "demonstration"} <= set(list_builtin_themes())


def test_no_theme_name_loads_the_default():
    config = create_calendar_config()
    load_run_theme(config, None)
    assert config.theme_v3.theme.name == "Default"


def test_a_theme_file_path_loads(tmp_path):
    path = tmp_path / "mine.yaml"
    path.write_text("theme: {name: Mine, version: '3.0'}\nlayout: {margin: {top: 12, left: '0.5in'}}\n")
    config = create_calendar_config()
    load_run_theme(config, str(path))
    assert config.theme_v3.theme.name == "Mine"
    assert (config.margin_top, config.margin_left) == (12.0, 36.0)
    assert config.include_margin is True


def test_an_unknown_theme_names_the_ones_that_exist():
    with pytest.raises(ThemeError, match="default"):
        load_run_theme(create_calendar_config(), "no-such-theme")


def test_a_theme_of_another_version_is_not_supported(tmp_path):
    path = tmp_path / "old.yaml"
    path.write_text("theme: {name: Old, version: '2.0'}\n")
    with pytest.raises(UnsupportedThemeError, match="not supported"):
        load_run_theme(create_calendar_config(), str(path))


def test_an_unknown_key_names_its_path(tmp_path):
    path = tmp_path / "typo.yaml"
    path.write_text("theme: {name: Typo, version: '3.0'}\ncandybar: {row_hight: 12}\n")
    with pytest.raises(ThemeError, match=r"candybar\.row_hight"):
        load_run_theme(create_calendar_config(), str(path))
