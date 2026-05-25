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
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Synthesize a legacy theme; the parser should reject it with a converter hint."""
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text(yaml.safe_dump({
        "theme": {"name": "legacy", "version": "2.0"},
        "text_styles": {"heading": {"font": "Roboto", "size": 10, "color": "black"}},
    }))
    rc = main([str(legacy)])
    captured = capsys.readouterr()
    assert rc == 2
    err = captured.err
    assert "legacy section" in err
    assert "tools/migrate_theme.py" in err
    assert "--convert" in err


def test_legacy_theme_with_convert_passes(tmp_path: Path) -> None:
    """The same synthetic legacy theme should pass with --convert."""
    legacy = tmp_path / "legacy.yaml"
    legacy.write_text(yaml.safe_dump({
        "theme": {"name": "legacy", "version": "2.0"},
        "text_styles": {"heading": {"font": "Roboto-Regular", "size": 10, "color": "black"}},
    }))
    rc = main([str(legacy), "--convert", "--quiet"])
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


def test_legacy_apply_to_element_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`apply_to: element` rules are no longer valid in themes (post-catalog)."""
    legacy = tmp_path / "stray.yaml"
    legacy.write_text(yaml.safe_dump({
        "theme": {"name": "stray", "version": "3.0"},
        "style_rules": [{
            "name": "bind ec-heading",
            "apply_to": "element",
            "select": {"element": "ec-heading"},
            "style": {"use": "text:heading"},
        }],
    }))
    rc = main([str(legacy)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "element_catalog.yaml" in captured.err
    assert "element_overrides:" in captured.err


def test_no_bundled_theme_contains_stray_element_bindings() -> None:
    """Shipped themes must not author `apply_to: element` rules any more —
    those bindings live in config/element_catalog.yaml.  rc=2 from the
    validator means it tripped that check.
    """
    failures: list[str] = []
    for theme_path in sorted(THEMES_DIR.glob("*.yaml")):
        raw = yaml.safe_load(theme_path.read_text()) or {}
        rules = raw.get("style_rules") or []
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            apply_to = rule.get("apply_to")
            targets = (
                [apply_to] if isinstance(apply_to, str)
                else list(apply_to) if isinstance(apply_to, list)
                else []
            )
            if "element" in targets:
                failures.append(f"{theme_path.name}: style_rules[{i}] is `apply_to: element`")
    assert not failures, "Stray element bindings still in shipped themes:\n" + "\n".join(failures)
