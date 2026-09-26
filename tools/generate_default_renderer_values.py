#!/usr/bin/env python
"""
Regenerate docs/DefaultRendererValues.md: what every visualization draws with
when the active theme does not set a value.

The values are measured, not transcribed.  Each view is run through the normal
``ecalendar.run()`` pipeline with a theme that defines nothing (``theme:``
metadata and an empty ``style_rules:`` list), with the visualizer swapped for a
stub that captures the finished ``CalendarConfig``.  The renderer sources are
then parsed for every style-token read (``self._tk("text:x").get("size")``) and
element-style read (``config.get_text_style("ec-x").font``), and each read's
fallback expression is evaluated against the captured configuration.

Usage:
    uv run python tools/generate_default_renderer_values.py           # rewrite the document
    uv run python tools/generate_default_renderer_values.py --print   # write to stdout
    uv run python tools/generate_default_renderer_values.py --check   # exit 1 when stale

Re-run after changing a renderer's fallbacks, ``setfontsizes()``,
``config/element_catalog_defaults.yaml`` or ``CalendarConfig`` defaults.  The
document quotes source line numbers, so ``--check`` also reports it stale after
unrelated edits that move those lines.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import importlib
import io
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, ClassVar
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOC = ROOT / "docs" / "DefaultRendererValues.md"
SCRIPT = "tools/generate_default_renderer_values.py"

VIEW_DATES: dict[str, tuple[str, str]] = {
    "weekly": ("20260101", "20260331"),
    "mini": ("20260101", "20261231"),
    "mini-icon": ("20260101", "20261231"),
    "candybar": ("20260101", "20261231"),
    "text-mini": ("20260101", "20261231"),
    "timeline": ("20260101", "20261231"),
    "pit": ("20260101", "20261231"),
    "blockplan": ("20260101", "20261231"),
    "gantt": ("20260202", "20260731"),
    "compactplan": ("20260309", "20260424"),
    "excelblockplan": ("20260105", "20260227"),
}
SVG_VIEWS = ("weekly", "mini", "mini-icon", "candybar", "timeline", "pit", "blockplan", "gantt", "compactplan")
# Section order in the document: the SVG views, then the text and workbook outputs.
DOC_VIEWS = (*SVG_VIEWS, "text-mini", "excelblockplan")

PAGE_FILE = "renderers/svg_base.py"
OWN_FILE = {
    "weekly": "visualizers/weekly/renderer.py",
    "mini": "visualizers/mini/renderer.py",
    "mini-icon": "visualizers/mini_icon/renderer.py",
    "candybar": "visualizers/candybar/renderer.py",
    "timeline": "visualizers/timeline/renderer.py",
    "pit": "visualizers/pit/renderer.py",
    "blockplan": "visualizers/blockplan/renderer.py",
    "gantt": "visualizers/gantt/renderer.py",
    "compactplan": "visualizers/compactplan/renderer.py",
    "text-mini": "visualizers/text_mini/renderer.py",
    "excelblockplan": "visualizers/excelblockplan.py",
}
# Views whose drawing goes through the shared mini renderer / details pages.
MINI_FAMILY = ("mini-icon", "candybar")
# Further modules whose config reads count toward a view's settings.
EXTRA_SETTINGS_FILES = {"pit": ("visualizers/pit/layout.py",)}
# Names a renderer binds the CalendarConfig to.
CONFIG_NAMES = frozenset({"config", "cfg", "c"})
RENDERER_CLASSES = {
    "weekly": ("visualizers.weekly.renderer", "WeeklyCalendarRenderer"),
    "mini": ("visualizers.mini.renderer", "MiniCalendarRenderer"),
    "mini-icon": ("visualizers.mini_icon.renderer", "MiniIconRenderer"),
    "candybar": ("visualizers.candybar.renderer", "CandybarRenderer"),
    "timeline": ("visualizers.timeline.renderer", "TimelineRenderer"),
    "pit": ("visualizers.pit.renderer", "PITRenderer"),
    "blockplan": ("visualizers.blockplan.renderer", "BlockPlanRenderer"),
    "gantt": ("visualizers.gantt.renderer", "GanttRenderer"),
    "compactplan": ("visualizers.compactplan.renderer", "CompactPlanRenderer"),
}

TOKEN_FUNCS = frozenset({"_tk", "_resolve_token", "resolve_token", "_resolve_excel_token"})
STYLE_FUNCS = frozenset({"get_text_style", "get_box_style", "get_line_style", "get_icon_style"})
STYLE_PROPS = frozenset(
    {
        "font",
        "size",
        "color",
        "opacity",
        "alignment",
        "fill",
        "fill_opacity",
        "stroke",
        "stroke_width",
        "stroke_opacity",
        "stroke_dasharray",
        "width",
        "dasharray",
        "icon",
        "fill_palette",
    }
)
WRAPPERS = frozenset({"float", "int", "str", "abs"})

EXCEL_FIELDS = (
    "excelblockplan_font",
    "excelblockplan_font_size",
    "excelblockplan_band_row_height",
    "excelblockplan_header_heading_fill_color",
    "excelblockplan_header_label_color",
    "excelblockplan_header_label_align_h",
    "excelblockplan_timeband_fill_color",
    "excelblockplan_timeband_fill_palette",
    "excelblockplan_timeband_label_color",
    "excelblockplan_federal_holiday_fill_color",
    "excelblockplan_company_holiday_fill_color",
    "excelblockplan_weekend_fill_color",
    "excelblockplan_vertical_line_color",
    "excelblockplan_vertical_line_width",
    "excelblockplan_top_time_bands",
    "excelblockplan_vertical_lines",
)
# excelblockplan token reads fall back to _read_band_settings() keys.
EXCEL_TOKEN_SETTINGS = {
    ("text:heading", "color"): "header_label_color",
    ("text:band_label", "color"): "timeband_label_color",
    ("box:band", "fill"): "timeband_fill_color",
    ("box:vline", "stroke"): "vline_color",
    ("box:vline", "stroke_width"): "vline_width",
}
STYLE_SUMMARY_PROPS = {
    "text": ("font", "size", "color", "opacity"),
    "box": ("fill", "fill_opacity", "stroke", "stroke_width"),
    "line": ("color", "width", "opacity", "dasharray"),
    "icon": ("icon", "color", "size"),
}


@dataclasses.dataclass
class Read:
    """One property read of a style token or element style in a renderer."""

    kind: str  # "token" | "style"
    name: str  # "text:event_name" or "ec-event-name"
    prop: str
    file: str
    line: int
    chain: str  # the enclosing fallback expression, as source
    condition: bool  # the read is only tested (``is not None``), not used as a value
    style_kind: str = ""
    tokvars: dict[str, str] = dataclasses.field(default_factory=dict)
    stylevars: dict[str, tuple[str, str]] = dataclasses.field(default_factory=dict)
    value: Any = None
    evaluable: bool = False


# ── Capture ──────────────────────────────────────────────────────────────────


def _write_theme(directory: Path, name: str, data: dict[str, Any]) -> Path:
    path = directory / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def capture_configs(theme: Path) -> dict[str, Any]:
    """Run every view through ecalendar.run() and keep the config handed to the renderer."""
    import ecalendar
    import visualizers.excelblockplan as excelblockplan
    from visualizers.base import VisualizationResult

    captured: dict[str, Any] = {}

    class _Stub:
        supported_options: ClassVar[list[str]] = []

        def __init__(self, view: str) -> None:
            self.view = view

        def validate_config(self, config: Any) -> list[str]:
            return []

        def generate(self, config: Any, db: Any) -> VisualizationResult:
            captured[self.view] = config
            return VisualizationResult(output_path="")

    class _Factory:
        @staticmethod
        def create(view: str) -> _Stub:
            return _Stub(view)

    def _capture_excel(config: Any, db: Any, out_path: Path) -> None:
        captured["excelblockplan"] = config

    with (
        mock.patch.object(ecalendar, "VisualizerFactory", _Factory),
        mock.patch.object(excelblockplan, "generate_excel_blockplan", _capture_excel),
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        for view, (start, end) in VIEW_DATES.items():
            ecalendar.run(["ecalendar.py", view, start, end, "-th", str(theme), "--quiet"])
    missing = sorted(set(VIEW_DATES) - set(captured))
    if missing:
        raise SystemExit(f"{SCRIPT}: could not capture the config for {missing}")
    return captured


def element_styles() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Catalog entries, then every ec-* style a theme that defines no tokens gets."""
    from config.config import CalendarConfig
    from config.element_catalog import load_catalog

    catalog = load_catalog()
    config = CalendarConfig()
    getters = {
        "text": config.get_text_style,
        "box": config.get_box_style,
        "line": config.get_line_style,
        "icon": config.get_icon_style,
    }
    return catalog, {ec: _plain(getters[entry.kind](ec)) for ec, entry in catalog.items()}


# ── Static extraction ────────────────────────────────────────────────────────


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        if isinstance(node.func, ast.Name):
            return node.func.id
    return None


def _token_of(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and _call_name(node) in TOKEN_FUNCS:
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and ":" in arg.value:
                return arg.value
    return None


def _style_of(node: ast.AST) -> tuple[str, str] | None:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in STYLE_FUNCS
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return node.func.attr.split("_")[1], node.args[0].value
    return None


def extract_reads(relative: str) -> list[Read]:
    """Every token / element-style property read in one source file."""
    source = (ROOT / relative).read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

    def enclosing(node: ast.AST) -> tuple[str, bool]:
        cur = node
        while True:
            parent = parents.get(cur)
            if (isinstance(parent, ast.Call) and _call_name(parent) in WRAPPERS and cur in parent.args) or isinstance(
                parent, (ast.BoolOp, ast.IfExp, ast.Compare, ast.UnaryOp, ast.NamedExpr)
            ):
                cur = parent
            else:
                break
        text = ast.get_source_segment(source, cur) or ""
        return " ".join(text.split()), isinstance(cur, (ast.Compare, ast.UnaryOp))

    reads: list[Read] = []
    seen: set[tuple[int, int]] = set()
    for func in (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        tokvars: dict[str, str] = {}
        stylevars: dict[str, tuple[str, str]] = {}
        for node in ast.walk(func):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                token = _token_of(node.value)
                style = _style_of(node.value)
                if token:
                    tokvars[node.targets[0].id] = token
                elif style:
                    stylevars[node.targets[0].id] = style
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                base = node.func.value
                token = _token_of(base) or (tokvars.get(base.id) if isinstance(base, ast.Name) else None)
                if token and (node.lineno, node.col_offset) not in seen:
                    seen.add((node.lineno, node.col_offset))
                    chain, condition = enclosing(node)
                    reads.append(
                        Read("token", token, node.args[0].value, relative, node.lineno, chain, condition,
                             tokvars=dict(tokvars), stylevars=dict(stylevars))
                    )  # fmt: skip
            if isinstance(node, ast.Attribute) and node.attr in STYLE_PROPS:
                base = node.value
                style = _style_of(base) or (stylevars.get(base.id) if isinstance(base, ast.Name) else None)
                if style and (node.lineno, node.col_offset) not in seen:
                    seen.add((node.lineno, node.col_offset))
                    chain, condition = enclosing(node)
                    reads.append(
                        Read("style", style[1], node.attr, relative, node.lineno, chain, condition, style[0],
                             tokvars=dict(tokvars), stylevars=dict(stylevars))
                    )  # fmt: skip
    return reads


# ── Evaluation ───────────────────────────────────────────────────────────────


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in dataclasses.asdict(value).items() if k != "size_rules"}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


class _TokenSource:
    """Stands in for ``self`` so ``self._tk("…")`` in a fallback expression resolves."""

    def __init__(self, config: Any, context: dict[str, str]) -> None:
        self._config = config
        self._context = context

    def _tk(self, token: str) -> dict[str, Any]:
        return resolve_token(self._config, token, self._context)


def resolve_token(config: Any, token: str, context: dict[str, str]) -> dict[str, Any]:
    theme = config.theme
    return theme.resolve_token(token, context) if theme is not None else {}


def token_context(view: str, config: Any) -> dict[str, str]:
    context = {"papersize": str(config.papersize)}
    if view in RENDERER_CLASSES:
        module_name, class_name = RENDERER_CLASSES[view]
        cls = getattr(importlib.import_module(module_name), class_name)
        context["visualizer"] = getattr(cls, "TOKEN_VISUALIZER", view)
    return context


def evaluate(reads: list[Read], config: Any, context: dict[str, str]) -> list[Read]:
    getters = {
        "text": config.get_text_style,
        "box": config.get_box_style,
        "line": config.get_line_style,
        "icon": config.get_icon_style,
    }
    evaluated = []
    for read in reads:
        module = importlib.import_module(read.file.removesuffix(".py").replace("/", "."))
        namespace = dict(vars(module))
        namespace["config"] = config
        namespace["self"] = _TokenSource(config, context)
        for name, token in read.tokvars.items():
            namespace[name] = resolve_token(config, token, context)
        for name, (kind, ec) in read.stylevars.items():
            namespace[name] = getters[kind](ec)
        try:
            value, evaluable = _plain(eval(read.chain, namespace)), not read.condition
        except Exception:
            value, evaluable = None, False
        evaluated.append(dataclasses.replace(read, value=value, evaluable=evaluable))
    return evaluated


def settings_files(view: str) -> list[str]:
    """Source files whose config reads make up a view's settings table."""
    files = [OWN_FILE[view], PAGE_FILE]
    if view in MINI_FAMILY:
        files.append(OWN_FILE["mini"])
    files.extend(f for f in EXTRA_SETTINGS_FILES.get(view, ()) if (ROOT / f).exists())
    return files


def settings_read(view: str, files: list[str], config: Any) -> list[dict[str, Any]]:
    """Theme-settable config fields the view's files read, with the captured value."""
    from config.config import CalendarConfig
    from config.theme_engine import THEME_TO_CONFIG_MAP

    keys_by_field: dict[str, list[str]] = defaultdict(list)
    for (section, key), field in THEME_TO_CONFIG_MAP.items():
        keys_by_field[field].append(f"{section}.{key}")
    if view == "excelblockplan":
        names = set(EXCEL_FIELDS)
    else:
        names = set()
        for relative in files:
            for node in ast.walk(ast.parse((ROOT / relative).read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in CONFIG_NAMES
                ):
                    names.add(node.attr)
                elif (
                    _call_name(node) == "getattr"
                    and isinstance(node, ast.Call)
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in ("config", "cfg")
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                ):
                    names.add(node.args[1].value)
    fields = {f.name for f in dataclasses.fields(CalendarConfig)}
    rows = []
    for name in sorted(names & fields):
        keys = keys_by_field.get(name, [])
        if keys or name.startswith(("pit_", "theme_pit_")):
            rows.append({"field": name, "theme_keys": keys, "value": _plain(getattr(config, name))})
    return rows


# ── Markdown ─────────────────────────────────────────────────────────────────


def _fmt(value: Any) -> str:
    if value is None:
        return "*unset*"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, float):
        return f"`{round(value, 2):g}`"
    if isinstance(value, int):
        return f"`{value}`"
    if isinstance(value, list):
        if not value:
            return "`[]`"
        if all(isinstance(item, dict) for item in value):
            names = [str(i.get("label") or i.get("name") or i.get("key") or i.get("band") or "?") for i in value]
            shown = ", ".join(names[:6]) + (", …" if len(names) > 6 else "")
            return f"{len(value)} {'entry' if len(value) == 1 else 'entries'}: `{shown}`"
        if len(value) > 6:
            return f"{len(value)} items: `" + ", ".join(str(item) for item in value[:4]) + ", …`"
        return "`[" + ", ".join(str(item) for item in value) + "]`"
    if isinstance(value, dict):
        if len(value) > 4:
            return f"{len(value)} entries (see `config/config.py`)"
        return "`{" + ", ".join(f"{k}: {v}" for k, v in value.items()) + "}`"
    text = str(value)
    return f"`{text}`" if text else '`""`'


def _code(source: str, limit: int = 150) -> str:
    text = " ".join(source.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "`" + text.replace("|", "\\|") + "`"


def _group(reads: list[Read]) -> dict[tuple[str, str, str], list[Read]]:
    groups: dict[tuple[str, str, str], list[Read]] = defaultdict(list)
    for read in reads:
        groups[(read.kind, read.name, read.prop)].append(read)
    return groups


def _default_cell(reads: list[Read]) -> str:
    values: list[Any] = []
    seen: set[str] = set()
    for read in reads:
        if read.evaluable:
            key = json.dumps(read.value, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                values.append(read.value)
    if not values:
        if all(read.condition for read in reads):
            return "*see source (used in a condition)*"
        return "*depends on the item being drawn*"
    cell = " / ".join(_fmt(v) for v in values)
    if len(values) > 1:
        cell += " (differs by call site)"
    if any(not read.evaluable and not read.condition for read in reads):
        cell += "; some call sites depend on the item"
    return cell


def _best_chain(reads: list[Read]) -> str:
    resolving = [read for read in reads if read.evaluable and read.value is not None]
    pool = resolving or [read for read in reads if not read.condition] or reads
    return max((read.chain for read in pool), key=len)


def _source_cell(reads: list[Read]) -> str:
    locations = sorted({(read.file, read.line) for read in reads})
    shown = [f"`{Path(f).parent.name}/{Path(f).name}:{line}`" for f, line in locations[:3]]
    extra = f" +{len(locations) - 3}" if len(locations) > 3 else ""
    return ", ".join(shown) + extra


def _token_table(reads: list[Read], computed: set[tuple[str, str | None]], visualizer: str | None) -> list[str]:
    groups = _group([read for read in reads if read.kind == "token"])
    if not groups:
        return ["*This view reads no style tokens.*", ""]
    lines = [
        "| Token | Property | Default | Resolution order (first value that is set wins) | Source |",
        "|---|---|---|---|---|",
    ]
    for (_, token, prop), group in sorted(groups.items()):
        cell = _default_cell(group)
        if prop == "size" and ((token, visualizer) in computed or (token, None) in computed):
            cell += " ¹"
        lines.append(f"| `{token}` | `{prop}` | {cell} | {_code(_best_chain(group))} | {_source_cell(group)} |")
    return [*lines, ""]


def _element_table(reads: list[Read]) -> list[str]:
    groups = _group([read for read in reads if read.kind == "style" and ".get(" not in read.chain])
    if not groups:
        return []
    lines = ["| Element | Property | Default | Resolution order | Source |", "|---|---|---|---|---|"]
    for (_, ec, prop), group in sorted(groups.items()):
        lines.append(
            f"| `{ec}` | `{prop}` | {_default_cell(group)} | {_code(_best_chain(group))} | {_source_cell(group)} |"
        )
    return [*lines, ""]


def _settings_table(rows: list[dict[str, Any]], title: str) -> list[str]:
    if not rows:
        return []
    lines = [
        f"<details><summary>{title} ({len(rows)})</summary>",
        "",
        "| Theme key | Config field | Default |",
        "|---|---|---|",
    ]
    for row in rows:
        keys = ", ".join(f"`{k}`" for k in row["theme_keys"]) or (
            "`pit:` block" if row["field"].startswith(("pit_", "theme_pit_")) else "—"
        )
        lines.append(f"| {keys} | `{row['field']}` | {_fmt(row['value'])} |")
    return [*lines, "", "</details>", ""]


def _style_summary(kind: str, style: dict[str, Any]) -> str:
    parts = []
    for prop in STYLE_SUMMARY_PROPS[kind]:
        value = style.get(prop)
        if value is not None:
            parts.append(f"{prop} {round(value, 2) if isinstance(value, float) else value}")
    return ("`" + ", ".join(parts) + "`") if parts else "*unset*"


def build_document() -> str:
    from config.config import _HEURISTIC_TOKEN_FIELDS, CalendarConfig
    from visualizers.excelblockplan import _read_band_settings

    os.chdir(ROOT)  # font paths are relative to the repository root
    with tempfile.TemporaryDirectory() as tmp:
        blank = _write_theme(Path(tmp), "blank", {"theme": {"name": "blank", "version": "3.0"}, "style_rules": []})
        configs = capture_configs(blank)
        catalog, defaults = element_styles()

    reads_by_file = {relative: extract_reads(relative) for relative in {*OWN_FILE.values(), PAGE_FILE}}
    contexts = {view: token_context(view, configs[view]) for view in VIEW_DATES}

    def view_reads(view: str, relative: str) -> list[Read]:
        return evaluate(reads_by_file[relative], configs[view], contexts[view])

    computed = {(token, visualizer) for token, visualizer, _ in _HEURISTIC_TOKEN_FIELDS}
    shared_fields = set.intersection(
        *({row["field"] for row in settings_read(v, settings_files(v), configs[v])} for v in SVG_VIEWS)
    )
    page = configs["weekly"]

    out: list[str] = []
    add = out.append
    add("# Default Renderer Values")
    add("")
    add(
        "What each visualization draws with when the active theme does not set a value. The values are read out of "
        "the renderers themselves: every view is run through the normal `ecalendar.py` pipeline with a theme that "
        "defines nothing (`theme:` metadata and an empty `style_rules:` list), and the style lookups found in the "
        "drawing code are evaluated against the resulting configuration. Where a lookup's fallback depends on the "
        "event or band being drawn, the table says so instead of giving a value."
    )
    add("")
    add(
        f"Generated by `{SCRIPT}`; regenerate it after changing a renderer's fallbacks rather than editing it by hand "
        "(`--check` reports whether it is stale)."
    )
    add("")
    add(
        f"- **Page:** the default paper, `{page.papersize}` ({page.pageX:g} × {page.pageY:g} pt, landscape). "
        "Font sizes marked ¹ are computed from the page height, so they differ on other paper sizes."
    )
    add("- **Units:** sizes, widths and offsets are in points; opacities run from 0 to 1.")
    add(
        "- **Source** columns give `file:line` in the code this document was generated from; the resolution order "
        "is the part to rely on."
    )
    add(
        "- For the theme keys themselves, and their `CalendarConfig` defaults, see the "
        "[Complete Theme Key Reference](USER_GUIDE.md#complete-theme-key-reference) in the user guide."
    )
    add("")
    add("## How a missing value is resolved")
    add("")
    add("A theme can leave a value unset at three different levels, and each falls back differently.")
    add("")
    add(
        "1. **Style tokens** (`text:event_name`, `box:duration`, `line:grid`, …). The drawing code asks the theme "
        "for the token and, when the theme doesn't define it (or doesn't set that property), walks a fallback chain "
        "written into the renderer: usually a legacy `config.*` field, an element style, or a literal. The "
        "*Resolution order* column shows that chain as code; the first value that is set wins. These chains differ "
        "from view to view, which is why one token can default to different values in different visualizations."
    )
    add(
        "2. **Element styles** (`ec-*` CSS classes). Looked up through the built-in element catalog "
        "(`config/element_catalog.yaml`) and always drawn from tokens: a token the theme doesn't define — or every "
        "token, when no theme or a theme without `style_rules:` is used — comes from "
        "`config/element_catalog_defaults.yaml`. The [appendix](#appendix-element-style-defaults) lists them."
    )
    add(
        "3. **Settings** (geometry, formats, palettes, symbols). A theme key maps to a `CalendarConfig` field; unset, "
        "the field keeps its default. Each view's settings are listed at the end of its section."
    )
    add("")
    add(
        "Defining a token is therefore not the same as leaving it out: a `define:` rule replaces the whole fallback "
        "chain for every view that reads the token, even when it copies the catalog default's values. See "
        "[What the required keys do](USER_GUIDE.md#what-the-required-keys-do)."
    )
    add("")
    add("### Computed text sizes ¹")
    add("")
    add(
        "After the theme loads, `setfontsizes()` (`config/config.py`) computes these sizes from the page height and "
        "injects them as the token's `size` for the named visualizer, unless the theme already sets a size. Values "
        f"shown are for `{page.papersize}`."
    )
    add("")
    add("| Token | Visualizer | Size | Computed into |")
    add("|---|---|---|---|")
    for token, visualizer, field in _HEURISTIC_TOKEN_FIELDS:
        config = configs.get(visualizer or "weekly", page)
        label = f"`{visualizer}`" if visualizer else "all"
        add(f"| `{token}` | {label} | {_fmt(getattr(config, field, None))} | `{field}` |")
    add("")

    add("## Shared by every SVG view")
    add("")
    add("### Page chrome")
    add("")
    add("Background, header/footer labels and watermark, drawn by the common SVG base renderer.")
    add("")
    page_reads = view_reads("weekly", PAGE_FILE)
    if any(read.kind == "token" for read in page_reads):
        out.extend(_token_table(page_reads, computed, None))
    out.extend(_element_table(page_reads))
    shared_rows = [
        row for row in settings_read("weekly", settings_files("weekly"), page) if row["field"] in shared_fields
    ]
    out.extend(_settings_table(shared_rows, "Settings every SVG view reads"))
    mini_groups = _group(view_reads("mini", OWN_FILE["mini"]))
    for view in DOC_VIEWS:
        config = configs[view]
        add(f"## {view}")
        add("")
        if view == "text-mini":
            add("Plain-text output: no fonts, colours or style tokens. Everything comes from settings.")
            add("")
            out.extend(_settings_table(settings_read(view, [OWN_FILE[view]], config), "Settings"))
            continue
        if view == "excelblockplan":
            band_settings = _read_band_settings(CalendarConfig())
            add(
                "The workbook reads four style tokens; each falls back to the per-band value first, then to the "
                "`excelblockplan:` settings below."
            )
            add("")
            add("| Token | Property | Default | Resolution order | Source |")
            add("|---|---|---|---|---|")
            for read in sorted(extract_reads(OWN_FILE[view]), key=lambda r: (r.name, r.prop)):
                default = band_settings[EXCEL_TOKEN_SETTINGS[(read.name, read.prop)]]
                add(
                    f"| `{read.name}` | `{read.prop}` | {_fmt(default)} | {_code(read.chain)} | {_source_cell([read])} |"
                )
            add("")
            out.extend(_settings_table(settings_read(view, [], CalendarConfig()), "Settings"))
            add(
                "Unset federal/company holiday fills fall back to `colors.federal_holiday.color` / "
                "`colors.company_holiday.color`, then to `#FFE4E1` / `#FFFACD`."
            )
            add("")
            continue
        own = view_reads(view, OWN_FILE[view])
        if view in MINI_FAMILY:
            add(
                "Draws its day grid with the mini renderer, so everything under [mini](#mini) applies. The tables "
                f"list what the {view} renderer reads on top of that, plus any mini value that comes out different here."
            )
            add("")
            for key, group in _group(view_reads(view, OWN_FILE["mini"])).items():
                if key in mini_groups and _default_cell(group) != _default_cell(mini_groups[key]):
                    own.extend(group)
        visualizer = contexts[view].get("visualizer")
        if view == "pit":
            add("PIT reads no style tokens: its colours, sizes and geometry come from the `pit:` settings below.")
            add("")
        else:
            out.extend(_token_table(own, computed, visualizer))
        out.extend(_element_table(own))
        rows = [row for row in settings_read(view, settings_files(view), config) if row["field"] not in shared_fields]
        out.extend(_settings_table(rows, "Settings"))

    add("## Appendix: element style defaults")
    add("")
    add(
        "Every `ec-*` class in the element catalog, with the token it is bound to and the style it gets when the "
        "theme does not define that token (`config/element_catalog_defaults.yaml`)."
    )
    add("")
    add("| Element | Token | Default |")
    add("|---|---|---|")
    for ec in sorted(catalog):
        entry = catalog[ec]
        add(f"| `{ec}` | `{entry.kind}:{entry.token}` | {_style_summary(entry.kind, defaults[ec])} |")
    return "\n".join(out).rstrip("\n") + "\n"


def main() -> int:
    text = build_document()

    if "--print" in sys.argv:
        print(text, end="")
        return 0

    if "--check" in sys.argv:
        if DOC.exists() and DOC.read_text(encoding="utf-8") == text:
            print("DefaultRendererValues.md is up to date.")
            return 0
        print(f"DefaultRendererValues.md is stale — regenerate with:\n  uv run python {SCRIPT}", file=sys.stderr)
        return 1

    DOC.write_text(text, encoding="utf-8")
    rows = sum(1 for line in text.splitlines() if line.startswith("| `"))
    print(f"Wrote {DOC.relative_to(ROOT)}: {len(text.splitlines())} lines, {rows} table rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
