"""Tests for tools/validate_theme.py — the CLI theme validator (design §11.2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# Make tools/ importable as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.validate_theme import main  # noqa: E402

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"


def test_basic_yaml_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([str(THEMES_DIR / "basic.yaml")])
    captured = capsys.readouterr()
    assert rc == 0
    assert "satisfies every requested visualizer" in captured.out


def test_sample_yaml_passes() -> None:
    rc = main([str(THEMES_DIR / "SAMPLE.yaml"), "--quiet"])
    assert rc == 0


def test_legacy_theme_without_convert_fails_with_hint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main([str(THEMES_DIR / "default.yaml")])
    captured = capsys.readouterr()
    assert rc == 2
    err = captured.err
    assert "legacy section" in err
    assert "tools/migrate_theme.py" in err
    assert "--convert" in err


def test_legacy_theme_with_convert_passes() -> None:
    rc = main([str(THEMES_DIR / "default.yaml"), "--convert", "--quiet"])
    assert rc == 0


def test_missing_keys_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text(yaml.safe_dump({
        "theme": {"name": "broken", "version": "3.0"},
        "style_rules": [],
    }))
    rc = main([str(broken), "--visualizer", "mini"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "missing key" in captured.out
    # The example snippet is paste-ready
    assert "add to your theme:" in captured.out


def test_unknown_visualizer_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theme = tmp_path / "x.yaml"
    theme.write_text(yaml.safe_dump({"theme": {"name": "x", "version": "3.0"}}))
    rc = main([str(theme), "--visualizer", "not-a-real-viz"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "unknown visualizer" in captured.err


def test_nonexistent_file_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["/tmp/this-path-does-not-exist-99999.yaml"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "theme file not found" in captured.err
