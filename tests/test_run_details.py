"""Run details: render record, icon files, details document and event CSV."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime

import pytest
import yaml

from config.config import CalendarConfig
from config.theme_engine import ThemeEngine, ThemeError
from importers.import_events import normalize_row
from renderers.details_record import (
    DRAWN_NO,
    DRAWN_PARTIAL,
    DRAWN_YES,
    KIND_OVERFLOW,
    DetailsRecord,
    IconUse,
    mark,
    role_for_class,
    split_reference,
)
from renderers.event_csv import RENDER_COLUMNS, build_event_csv
from renderers.icon_export import export_icons, icon_filename
from renderers.markdown_details import build_markdown, escape_cell
from renderers.run_details import write_run_details
from shared.run_paths import RunPaths

_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>'


def _row(name: str, start: str, end: str | None = None, **extra) -> dict:
    return {"Task_Name": name, "Start": start, "End": end or start, **extra}


def _record() -> DetailsRecord:
    record = DetailsRecord(
        "weekly",
        [
            _row("Kickoff | plan", "20260105", Milestone=1, ID=1, Resource_Group="Eng", WBS="1"),
            _row("Build", "20260106", "20260110", ID=2, WBS="1.1", Notes="line one\nline two"),
            _row("Unplaced", "20260107", ID=3),
        ],
    )
    kickoff, build, _unplaced = record.events
    record.record_icon(IconUse("diamond-fill", "#1f77b4", "milestone"), kickoff)
    kickoff.mark_drawn()
    record.record_icon(mark("bar", "gold"), build)
    record.record_icon(IconUse("arrow-right", None, "continuation_after"), build)
    build.assigned_color = "gold"
    build.color_source = "theme"
    build.mark_drawn(DRAWN_PARTIAL)
    record.record_icon(IconUse("flag-us", None, "holiday"), "New Year's Day")
    record.record_icon(IconUse("warningtriangle", "red", "overflow"))
    record.add_color("gold", "Duration bar", "theme")
    record.add_exception(KIND_OVERFLOW, "Unplaced", "20260107", start="20260107", end="20260107")
    return record


def _config(**overrides) -> CalendarConfig:
    config = CalendarConfig()
    config.adjustedstart = "20260105"
    config.adjustedend = "20260111"
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


# ── Record ───────────────────────────────────────────────────────────────────


def test_record_keys_events_once_and_tracks_drawn_state():
    record = _record()
    kickoff, build, unplaced = record.events
    assert record.note_for(_row("Kickoff | plan", "20260105", ID=1)) is kickoff
    assert (kickoff.drawn, build.drawn, unplaced.drawn) == (DRAWN_YES, DRAWN_PARTIAL, DRAWN_NO)
    # A later "yes" never upgrades a partial draw.
    build.mark_drawn()
    assert build.drawn == DRAWN_PARTIAL
    assert [n.category for n in record.events] == ["milestone", "duration", "event"]


def test_marker_leads_with_marks_and_synthesizes_a_swatch():
    record = _record()
    kickoff, build, _ = record.events
    assert record.marker_for(build)[0] == mark("bar", "gold")
    kickoff.assigned_color = "#123456"
    assert record.marker_for(kickoff) == [mark("swatch", "#123456"), IconUse("diamond-fill", "#1f77b4", "milestone")]


def test_exception_count_and_reference_split():
    record = _record()
    assert record.exception_count(record.events[2]) == 1
    assert split_reference("circle-7: depends on X") == ("circle-7", "depends on X")
    assert split_reference("plain words: here") == ("", "plain words: here")


def test_role_for_class():
    assert role_for_class("ec-milestone-marker") == "milestone"
    assert role_for_class("ec-weekend-icon") == "weekend"
    assert role_for_class(None) == "icon"


# ── Icon files ───────────────────────────────────────────────────────────────


def test_icon_files_are_uniform_and_stay_in_the_icons_folder(tmp_path):
    paths = RunPaths.for_output("chart.svg", root=tmp_path)
    uses = [IconUse("diamond-fill", "#1f77b4", "milestone"), mark("flag", "red"), IconUse("../../evil", None, "x")]
    written = export_icons(uses, paths, 16, lambda name: _ICON)
    files = sorted(paths.icons_dir.iterdir())
    assert len(files) == 3
    for file in files:
        head = file.read_text()
        assert 'width="16" height="16" viewBox="0 0 16 16"' in head
        assert file.parent == paths.icons_dir
    assert written[uses[0]] == "icons/diamond-fill--1f77b4.svg"
    assert icon_filename(uses[2]) == "evil--native.svg"


def test_unresolvable_icons_are_left_out(tmp_path):
    paths = RunPaths.for_output("chart.svg", root=tmp_path)
    assert export_icons([IconUse("nope", None, "x")], paths, 16, lambda name: None) == {}


# ── Markdown ─────────────────────────────────────────────────────────────────


def _markdown(tmp_path, **overrides) -> tuple[str, RunPaths]:
    record = _record()
    config = _config(**overrides)
    paths = RunPaths.for_output("chart.svg", root=tmp_path)
    holidays = [
        {"date": "2026-01-01", "name": "New Year's Day", "raw_name": "New Year's Day", "kind": "Federal Holiday"}
    ]
    icon_paths = export_icons(record.all_icon_uses(), paths, 16, lambda name: _ICON)
    text = build_markdown(record, config, paths, holidays, icon_paths, generated=datetime(2026, 9, 14, 12, 0))
    return text, paths


def test_document_sections_and_icon_links_resolve(tmp_path):
    text, paths = _markdown(tmp_path)
    for heading in ("## Events", "## Color Key", "## Icons & Symbols", "## Exceptions", "## Holidays & Special Days"):
        assert heading in text
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert links
    for link in links:
        assert (paths.folder / link).is_file(), link
    referenced = {link for link in links}
    for file in paths.icons_dir.iterdir():
        assert f"icons/{file.name}" in referenced
    assert "Did not fit in its day" in text
    assert "- **Generated:** 2026-09-14 12:00" in text


def test_cells_are_escaped_aligned_and_indented(tmp_path):
    text, _ = _markdown(tmp_path)
    assert "Kickoff \\| plan" in text
    assert "line one<br>line two" in text
    assert "| ---: |" in text or "---: |" in text
    assert "&nbsp;&nbsp;Build" in text


def test_group_by_and_color_rank_sort(tmp_path):
    text, _ = _markdown(tmp_path, details_md_group_by="category", details_md_sort=["color_rank", "start_date"])
    assert "### milestone" in text and "### duration" in text
    grouped, _ = _markdown(tmp_path, details_md_sort=["color_rank", "start_date"])
    events = grouped.split("## Events", 1)[1].split("## Color Key", 1)[0]
    assert events.index("Build") < events.index("Kickoff")


def test_icon_mode_name_and_empty_exceptions(tmp_path):
    record = DetailsRecord("gantt", [_row("A", "20260105")])
    config = _config(details_md_icon_mode="name")
    record.record_icon(IconUse("check", None, "event"), record.events[0])
    text = build_markdown(record, config, RunPaths.for_output("c.svg", root=tmp_path), [], {})
    assert "`check`" in text
    assert "Every item was drawn as scheduled." in text


def test_escape_cell_handles_html_and_pipes():
    assert escape_cell("a|b<c>&d") == "a\\|b&lt;c&gt;&amp;d"


# ── CSV ──────────────────────────────────────────────────────────────────────


def test_csv_round_trips_through_the_importer_with_render_columns():
    rows = list(csv.DictReader(io.StringIO(build_event_csv(_record(), _config()))))
    assert [r["task_name"] for r in rows] == ["Kickoff | plan", "Build", "Unplaced"]
    assert set(RENDER_COLUMNS) <= set(rows[0])
    build = rows[1]
    assert build["assigned_color"] == "gold"
    assert build["icons"] == "bar;arrow-right"
    assert build["drawn"] == DRAWN_PARTIAL
    mapped = normalize_row(rows[0])
    assert mapped["name"] == "Kickoff | plan"
    assert not set(RENDER_COLUMNS) & set(mapped)


def test_csv_without_render_columns_and_with_explicit_columns():
    plain = build_event_csv(_record(), _config(details_csv_render_columns=False))
    assert "assigned_color" not in plain.splitlines()[0]
    explicit = build_event_csv(
        _record(),
        _config(details_csv_columns=[{"field": "name", "header": "Task"}, {"field": "marker", "header": "Key"}]),
    )
    header, first = explicit.splitlines()[:2]
    assert header.startswith("Task,Key,")
    assert first.startswith("Kickoff | plan,diamond-fill,")


# ── Writer and theme ─────────────────────────────────────────────────────────


def test_write_run_details_honours_each_switch(tmp_path):
    paths = RunPaths.for_output("chart.svg", root=tmp_path)
    config = _config(include_details_icons=False, include_details_csv=False)
    written = write_run_details(_record(), config, None, paths)
    assert written == [paths.markdown]
    assert not paths.icons_dir.exists()
    assert "`diamond-fill #1f77b4`" not in paths.markdown.read_text()


def _theme_with_details(tmp_path, details: dict):
    base = yaml.safe_load((ThemeEngine.BUILTIN_THEMES_DIR / "basic.yaml").read_text())
    base["details"] = details
    path = tmp_path / "t.yaml"
    path.write_text(yaml.safe_dump(base))
    engine = ThemeEngine()
    engine.load(str(path))
    return engine


def test_unknown_details_field_is_a_theme_error(tmp_path):
    engine = _theme_with_details(tmp_path, {"markdown": {"columns": [{"field": "nmae"}]}})
    with pytest.raises(ThemeError, match="nmae"):
        engine.apply(CalendarConfig())


def test_gantt_columns_paste_into_details_columns(tmp_path):
    engine = _theme_with_details(tmp_path, {"markdown": {"columns": CalendarConfig().gantt_columns}})
    config = engine.apply(CalendarConfig())
    assert config.details_md_columns == CalendarConfig().gantt_columns


def test_csv_columns_string_must_be_exportdata(tmp_path):
    engine = _theme_with_details(tmp_path, {"csv": {"columns": "everything"}})
    with pytest.raises(ThemeError, match="exportdata"):
        engine.apply(CalendarConfig())
