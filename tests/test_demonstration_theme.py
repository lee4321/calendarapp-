"""config/themes/demonstration.yaml shows every key the schema defines, and stays in step with it."""

from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import yaml

from config import theme_schema as schema
from config.theme_loader import load_theme
from tools.generate_demonstration_theme import TARGET, build

DEMO = Path(TARGET)


def test_the_committed_file_is_what_the_generator_writes():
    """Regenerate with: uv run python tools/generate_demonstration_theme.py"""
    assert DEMO.read_text(encoding="utf-8") == build()


def test_the_demonstration_theme_loads():
    assert load_theme("demonstration").theme.name == "Demonstration"


def _missing(cls: type, data: dict, path: str) -> list[str]:
    """Schema keys of *cls* that *data* does not carry, recursively."""
    hints = typing.get_type_hints(cls, vars(schema))
    out: list[str] = []
    for f in dataclasses.fields(cls):  # ty: ignore[invalid-argument-type]
        where = f"{path}.{f.name}" if path else f.name
        if f.name not in data:
            out.append(where)
            continue
        inner = _dataclass_of(hints[f.name])
        value = data[f.name]
        if inner is None or value is None:
            continue
        if isinstance(value, list):
            for i, item in enumerate(value[:1]):
                if isinstance(item, dict):
                    out.extend(_missing(inner, item, f"{where}[{i}]"))
        elif isinstance(value, dict):
            out.extend(_missing(inner, value, where))
    return out


def _dataclass_of(tp: typing.Any) -> type | None:
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return tp
    for arm in typing.get_args(tp):
        found = _dataclass_of(arm)
        if found is not None:
            return found
    return None


def test_every_schema_key_appears():
    data = yaml.safe_load(DEMO.read_text(encoding="utf-8"))
    assert _missing(schema.Theme, data, "") == []
