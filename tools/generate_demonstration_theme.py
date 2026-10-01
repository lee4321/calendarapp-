"""Write config/themes/demonstration.yaml: every key a theme can set, with its default and allowed values.

The file is generated from the schema (config/theme_schema.py) so it cannot drift:
each field shows its default, a comment from the schema's own notes, and what
values the field accepts.  tests/test_demonstration_theme.py fails when the
committed file differs from this tool's output, or does not load, or leaves a
schema key out.

Regenerate with:  uv run python tools/generate_demonstration_theme.py
"""

from __future__ import annotations

import ast
import dataclasses
import sys
import textwrap
import types
import typing
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from config import theme_schema as schema  # noqa: E402
from config.theme_schema import Theme, ThemeMeta  # noqa: E402

TARGET = REPO / "config" / "themes" / "demonstration.yaml"
SOURCE = Path(schema.__file__)

#: Values to show for a field whose default is "unset", so the file shows a usable example.
EXAMPLES: dict[str, Any] = {
    "watermark.text": "DRAFT",
    "watermark.font_size": 96,
    "today.date": "20260315",
    "fiscal.year_offset": 1,
    "palettes.month_colors": {"01": "lightblue", "02": "lightgreen"},
    "palettes.fiscal_period_colors": {"01": "gold", "02": "khaki"},
    "palettes.group_colors": ["steelblue", "tomato"],
    "durations.icon_background_color": "white",
    "durations.icon_stroke_color": "black",
    "durations.stroke_dasharray": "4 2",
    "durations.dates.font_size": 8,
    "durations.dates.color": "dimgrey",
    "durations.name_color": "black",
    "events.date.font_size": 8,
    "events.marker.stroke_color": "black",
    "timeline.events.box_width": 115,
    "timeline.events.box_height": 16,
    "timeline.events.row_gap": 10,
    "timeline.durations.box_width": 120,
    "timeline.durations.box_height": 14,
    "timeline.durations.icon_column_ratio": 0.15,
    "timeline.labella.min_pos": 20,
    "timeline.labella.max_pos": 1000,
    "pit.label.icon_size": 11,
    "blockplan.band_label_column_ratio": 0.08,
    "blockplan.duration_row_gap": 3,
    "compact_plan.header_bottom_y": 40,
    "candybar.suppress_weekends": True,
    "mini_calendar.month_outline": {"color": "grey", "width": 0.5},
    "mini_calendar.glyphs.day_number": "day-circled",
    "mini_calendar.glyphs.day_number_digits": "digits-superscript",
    "text_mini.glyphs.day_number_digits": "digits-ascii",
    "text_mini.glyphs.week_number_digits": "digits-seven-segment",
    "gantt.columns": None,
    "holidays.icon_color": "dimgrey",
    "holidays.date_font_size": 7,
    "holidays.date_color": "dimgrey",
    "holidays.federal.color": "red",
    "holidays.company.color": "green",
    "holidays.weekend.icon": "moon",
    "holidays.federal.icon": "flag-duotone",
    "holidays.company.icon": "star",
    "icons.event.name": "circle-fill",
    "icons.milestone.name": "diamond-fill",
    "icons.event.stroke_width": 0.5,
    "icons.event.stroke_opacity": 0.8,
    "text.heading.size_by_paper": {"letter": 10, "3x5": 6},
    "excelblockplan.column_width": 3.2,
    "style_rules.select": {"resource_group": "dev", "priority_max": 2},
    "style_rules.style": {"fill": "steelblue", "fill_opacity": 0.8, "stroke": "black"},
    "blockplan.swimlanes": [
        {
            "name": "Engineering",
            "match": {"resource_groups": ["dev"]},
            "split_ratio": 0.5,
            "fill_color": "aliceblue",
            "label_color": "navy",
            "timeline_fill_color": "none",
            "label_align_h": "end",
            "label_align_v": "middle",
        }
    ],
}

#: Short notes for fields the schema leaves undocumented.
NOTES: dict[str, str] = {
    "theme.name": "Shown in the run's details document and the theme listing.",
    "theme.version": "Must be '3.0'; any other version stops the run with 'not supported'.",
}


# ─── Reading the schema's own notes ──────────────────────────────────────────


def _notes() -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """Class docstrings and the ``#:`` comment lines above each field."""
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()
    tree = ast.parse(text)
    docs: dict[str, str] = {}
    fields: dict[tuple[str, str], str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        docs[node.name] = (ast.get_docstring(node) or "").strip()
        for item in node.body:
            if not (isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)):
                continue
            above: list[str] = []
            row = item.lineno - 2
            while row >= 0 and lines[row].strip().startswith("#:"):
                above.insert(0, lines[row].strip()[2:].strip())
                row -= 1
            if above:
                fields[(node.name, item.target.id)] = " ".join(above)
    return docs, fields


DOCS, FIELD_NOTES = _notes()


# ─── Describing a type ───────────────────────────────────────────────────────


def _describe(tp: Any) -> str:
    origin = get_origin(tp)
    if origin is Literal:
        return "one of: " + " | ".join(str(a) for a in get_args(tp))
    if origin in (Union, types.UnionType):
        arms = [a for a in get_args(tp) if a is not type(None)]
        parts = [_describe(a) for a in arms]
        text = " or ".join(dict.fromkeys(parts))
        return text + (" (may be left unset)" if len(arms) != len(get_args(tp)) else "")
    if origin is list:
        (item,) = get_args(tp) or (Any,)
        return f"a list of {_describe(item)}"
    if origin is dict:
        return "a mapping"
    if tp is bool:
        return "true | false"
    if tp is int:
        return "a whole number"
    if tp is float:
        return "a number"
    if tp is str:
        return "text"
    if dataclasses.is_dataclass(tp):
        return "a block"
    if tp is Any:
        return "any value"
    return str(tp)


# ─── Emitting YAML ───────────────────────────────────────────────────────────


def _scalar(value: Any) -> str:
    return (
        yaml.safe_dump(value, default_flow_style=True, width=10_000, allow_unicode=True)
        .strip()
        .removesuffix("\n...")
        .strip()
    )


def _example_for(path: str, default: Any) -> Any:
    return EXAMPLES.get(path, default)


def _instance_of(tp: Any) -> Any | None:
    """A default instance of the dataclass inside an optional/list type, else None."""
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        for arm in get_args(tp):
            inst = _instance_of(arm)
            if inst is not None:
                return inst
        return None
    if origin is list:
        (item,) = get_args(tp) or (Any,)
        return _instance_of(item)
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return _make(tp)
    return None


def _make(cls: type) -> Any:
    """A default instance, supplying the required fields with a sample."""
    required = {
        schema.TimescaleRow: {"unit": "month"},
        schema.StyleRule: {"name": "example rule", "apply_to": "box:duration"},
        schema.GanttColumn: {"field": "name"},
        ThemeMeta: {"name": "Demonstration"},
        Theme: {"theme": ThemeMeta(name="Demonstration")},
    }
    return cls(**required.get(cls, {}))


def _hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls, vars(schema))


def emit_block(obj: Any, indent: int, path: str, out: list[str]) -> None:
    cls = type(obj)
    hints = _hints(cls)
    pad = " " * indent
    for f in dataclasses.fields(cls):
        tp = hints[f.name]
        key_path = f"{path}.{f.name}" if path else f.name
        value = getattr(obj, f.name)
        note = NOTES.get(key_path) or FIELD_NOTES.get((cls.__name__, f.name)) or ""
        accepts = _describe(tp)
        for line in textwrap.wrap(note, 96):
            out.append(f"{pad}# {line}")
        if accepts != "a block":
            out.append(f"{pad}# [{accepts}]")
        _emit_field(f.name, tp, value, indent, key_path, out)


def _emit_field(name: str, tp: Any, value: Any, indent: int, path: str, out: list[str]) -> None:
    pad = " " * indent
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out.append(f"{pad}{name}:")
        emit_block(value, indent + 2, path, out)
        return
    if value is None:
        sample = _instance_of(tp)
        if sample is not None:
            out.append(f"{pad}{name}:  # unset by default; the block below shows its keys")
            emit_block(sample, indent + 2, path, out)
            return
        shown = _example_for(path, None)
        out.append(f"{pad}{name}: {_scalar(shown)}")
        return
    if isinstance(value, list) and value and dataclasses.is_dataclass(value[0]):
        out.append(f"{pad}{name}:")
        for item in value:
            _emit_list_item(item, indent + 2, path, out)
        return
    if isinstance(value, list) and not value:
        item_tp = (get_args(_strip_optional(tp)) or (Any,))[0]
        sample = _instance_of(item_tp)
        if sample is not None:
            out.append(f"{pad}{name}:")
            _emit_list_item(sample, indent + 2, path, out)
            return
        shown = _example_for(path, value)
        out.append(f"{pad}{name}: {_scalar(shown)}")
        return
    if isinstance(value, dict) and not value:
        out.append(f"{pad}{name}: {_scalar(_example_for(path, value))}")
        return
    out.append(f"{pad}{name}: {_scalar(_example_for(path, value))}")


def _strip_optional(tp: Any) -> Any:
    if get_origin(tp) in (Union, types.UnionType):
        arms = [a for a in get_args(tp) if a is not type(None)]
        return arms[0] if len(arms) == 1 else tp
    return tp


def _emit_list_item(item: Any, indent: int, path: str, out: list[str]) -> None:
    """One ``- `` item of a list of blocks, every key on its own line."""
    block: list[str] = []
    emit_block(item, indent + 2, path, block)
    lead = 0
    while lead < len(block) and block[lead].lstrip().startswith("#"):
        lead += 1
    if lead == len(block):
        out.append(" " * indent + "- {}")
        return
    out.extend(" " * indent + line.lstrip() for line in block[:lead])
    out.append(" " * indent + "- " + block[lead].lstrip())
    out.extend(block[lead + 1 :])


HEADER = """\
# The demonstration theme: every key a version-3.0 theme can set, with its default
# value and the values it accepts.
#
# GENERATED from config/theme_schema.py by tools/generate_demonstration_theme.py; edit the
# schema, not this file.  Each key is preceded by a note from the schema (where it has one)
# and the values it accepts in [brackets].  A key shown as `null` is unset by default; the
# keys of an optional block are listed under it.  Any key may be left out of a theme: the
# value shown here is what a theme that omits it gets.
#
# Sections: theme, fonts, text, boxes, icons, lines, palettes, timescale, today, holidays,
# shading, week_numbers, fiscal, events, durations, continuation, overflow, watermark, layout,
# details, style_rules, then one structure block per view.
#
# Timescale rows: `unit` is one of date | dow | week | month | quarter | year | fiscal_quarter |
# fiscal_period | interval | countdown | countup | holiday | icon.  `primary` rows sit above the
# content (right of a vertical axis), `secondary` rows below (left); every view draws them.
# Style rules: `apply_to` is `<kind>:<role>` (kind text | box | line | icon) or a list of them;
# `select` picks events or days by any of:
#   {selectors}.

"""


def build() -> str:
    theme = _make(Theme)
    out: list[str] = []
    emit_block(theme, 0, "", out)
    selectors = "\n#   ".join(textwrap.wrap(", ".join(sorted(schema.SELECTOR_KEYS)), 90))
    return HEADER.format(selectors=selectors) + "\n".join(out) + "\n"


def main() -> int:
    TARGET.write_text(build(), encoding="utf-8")
    print(f"wrote {TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
