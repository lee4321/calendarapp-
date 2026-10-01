"""The timescale engine: planning rows into cells, ticks and lines, and drawing them."""

from __future__ import annotations

from datetime import date, timedelta

import drawsvg
import pytest

from config.config import CalendarConfig
from config.theme_loader import load_theme
from config.theme_schema import LineSpec, RowColumnFill, RowText, RowTick, TimescaleRow
from renderers import timescale as ts
from shared.db_access import CalendarDB
from shared.orientation import Orientation
from shared.span import Frame, Span

FONT = "OfficinaSans-Book"


def make_theme(**sections):
    data = {"theme": {"name": "t", "version": "3.0"}, "fonts": {"family": FONT}, **sections}
    return load_theme(data, font_registry={FONT})


def make_ctx(theme=None, db=None, measure=lambda text, font, size: len(text) * size * 0.5, **kw):
    return ts.ScaleContext(theme or make_theme(), CalendarConfig(), db=db, measure=measure, **kw)


def days(first: date, n: int, *, weekdays_only: bool = False) -> list[date]:
    out = [first + timedelta(days=i) for i in range(n)]
    return [d for d in out if d.weekday() < 5] if weekdays_only else out


Q1 = days(date(2026, 1, 1), 90)  # Jan 1 - Mar 31
SPAN = Span(Q1, 0, 900)  # 10 points a day


def plan(rows, span=SPAN, ctx=None, **kw):
    return ts.plan_rows(rows, span, ctx or make_ctx(), **kw)


class TestCells:
    def test_month_cells_follow_the_days(self):
        (row,) = plan([TimescaleRow(unit="month", format="MMM")]).rows
        assert [(c.label, c.a, c.b) for c in row.cells] == [("Jan", 0, 310), ("Feb", 310, 590), ("Mar", 590, 900)]
        assert row.kind == "cells"

    def test_show_every_merges_cells(self):
        (row,) = plan([TimescaleRow(unit="date", every=7)]).rows
        # Jan 1 2026 is a Thursday: a merged cell never crosses a Monday, so the first holds Thu-Sun.
        assert (row.cells[0].a, row.cells[0].b) == (0, 40)
        assert (row.cells[1].a, row.cells[1].b) == (40, 110)
        assert len(row.cells) == 14

    def test_quarter_unit(self):
        (row,) = plan([TimescaleRow(unit="quarter")]).rows
        assert [c.label for c in row.cells] == ["Q1"]

    def test_hidden_days_take_no_space(self):
        weekdays = days(date(2026, 5, 4), 14, weekdays_only=True)
        span = Span(weekdays, 0, 100)
        (row,) = plan([TimescaleRow(unit="week", format="W{n}")], span).rows
        assert [(c.label, c.a, c.b) for c in row.cells] == [("W1", 0, 50), ("W2", 50, 100)]

    def test_label_values_cycle(self):
        (row,) = plan([TimescaleRow(unit="month", label_values=["A", "B"])]).rows
        assert [c.label for c in row.cells] == ["A", "B", "A"]

    def test_label_wider_than_its_cell_is_kept_to_be_compressed(self):
        (row,) = plan([TimescaleRow(unit="date", format="dddd")]).rows  # 10 points a day, "Thursday" is far wider
        assert all(c.show_label for c in row.cells)


class TestStyle:
    def test_row_text_falls_back_to_the_band_label_role(self):
        theme = make_theme(text={"band_label": {"size": 9, "color": "navy"}})
        (row,) = plan([TimescaleRow(unit="month")], ctx=make_ctx(theme)).rows
        assert (row.text.size, row.text.color, row.text.font) == (9, "navy", FONT)

    def test_row_text_overrides_win(self):
        (row,) = plan([TimescaleRow(unit="month", text=RowText(size=6, color="red"))]).rows
        assert (row.text.size, row.text.color) == (6, "red")

    def test_flat_fill_and_opacity(self):
        (row,) = plan([TimescaleRow(unit="month", fill="gold", fill_opacity=0.5)]).rows
        assert {(c.fill, c.fill_opacity) for c in row.cells} == {("gold", 0.5)}

    def test_palette_cycles_over_cells(self):
        (row,) = plan([TimescaleRow(unit="month", fill_palette=["red", "blue"])]).rows
        assert [c.fill for c in row.cells] == ["red", "blue", "red"]

    def test_named_palette_comes_from_the_lookup(self):
        ctx = make_ctx(palette=lambda name: ["a", "b", "c"] if name == "accent" else None)
        (row,) = plan([TimescaleRow(unit="month", fill_palette="accent")], ctx=ctx).rows
        assert [c.fill for c in row.cells] == ["a", "b", "c"]
        with pytest.raises(ValueError, match="palette 'nope' not found"):
            plan([TimescaleRow(unit="month", fill_palette="nope")], ctx=ctx)

    def test_unset_fill_comes_from_the_band_box_role(self):
        theme = make_theme(
            boxes={"band": {"fill": "khaki", "fill_opacity": 0.4, "stroke": "grey", "stroke_width": 0.25}}
        )
        (row,) = plan([TimescaleRow(unit="month")], ctx=make_ctx(theme)).rows
        assert {(c.fill, c.fill_opacity) for c in row.cells} == {("khaki", 0.4)}
        assert (row.border.color, row.border.width) == ("grey", 0.25)

    def test_no_fill_by_default(self):
        (row,) = plan([TimescaleRow(unit="month")]).rows
        assert {c.fill for c in row.cells} == {None}

    def test_row_border_beats_the_box_role(self):
        (row,) = plan([TimescaleRow(unit="month", border=LineSpec(color="red", width=2))]).rows
        assert (row.border.color, row.border.width) == ("red", 2)


class TestStack:
    def test_rows_stack_by_height(self):
        p = plan([TimescaleRow(unit="month", height=12), TimescaleRow(unit="date", height=8)])
        assert [(r.offset, r.height) for r in p.rows] == [(0, 12), (12, 8)]
        assert p.height == 20

    def test_a_tall_stack_scales_down_without_dropping_rows(self):
        p = plan([TimescaleRow(unit="month", height=12), TimescaleRow(unit="week", height=8)], max_height=10)
        assert len(p.rows) == 2
        assert p.height == pytest.approx(10)
        assert p.rows[1].offset == pytest.approx(6)

    def test_narrow_rows_are_dropped(self):
        span = Span(Q1, 0, 90)  # one point a day, below the 3-point minimum
        p = plan([TimescaleRow(unit="date"), TimescaleRow(unit="month")], span)
        assert p.dropped == (0,)
        assert [r.row.unit for r in p.rows] == ["month"]
        assert p.rows[0].offset == 0  # the survivors close up

    def test_the_minimum_is_a_theme_setting(self):
        theme = make_theme(timescale={"min_segment_width": 0})
        span = Span(Q1, 0, 90)
        assert plan([TimescaleRow(unit="date")], span, make_ctx(theme)).dropped == ()


class TestPages:
    PAGE2 = Span(Q1[30:60], 0, 300)  # Jan 31 - Mar 1

    def test_clipped_cells_keep_their_labels_and_are_flagged(self):
        (row,) = plan([TimescaleRow(unit="month", format="MMM")], self.PAGE2, full_days=Q1).rows
        jan, feb, mar = row.cells
        assert (jan.label, jan.continues_before, jan.continues_after) == ("Jan", True, False)
        assert (feb.label, feb.continues_before, feb.continues_after) == ("Feb", False, False)
        assert (mar.label, mar.continues_before) == ("Mar", False) and mar.a == 290  # only Mar 1 is on this page

    def test_grouping_runs_across_pages(self):
        (row,) = plan([TimescaleRow(unit="date", every=7)], self.PAGE2, full_days=Q1).rows
        # Groups of seven counted from Jan 1: one starts Jan 29 and spills onto this page.
        assert row.cells[0].start == Q1[30]
        assert row.cells[0].continues_before

    def test_palette_colours_continue_across_pages(self):
        (row,) = plan(
            [TimescaleRow(unit="month", fill_palette=["red", "blue", "green"])], self.PAGE2, full_days=Q1
        ).rows
        assert [c.fill for c in row.cells] == ["red", "blue", "green"]


class TestAxisMode:
    ROW = TimescaleRow(unit="month", format="MMM", tick=RowTick(length=6))

    def test_a_row_with_a_tick_facet_becomes_ticks(self):
        (row,) = plan([self.ROW], mode="axis").rows
        assert row.kind == "ticks"
        assert [(t.label, t.along, t.mark) for t in row.ticks] == [
            ("Jan", 0, True),
            ("Feb", 310, True),
            ("Mar", 590, True),
        ]
        assert row.cells == ()

    def test_a_row_without_one_stays_cells_in_axis_mode(self):
        (row,) = plan([TimescaleRow(unit="month")], mode="axis").rows
        assert row.kind == "cells"

    def test_table_mode_ignores_the_tick_facet(self):
        (row,) = plan([self.ROW]).rows
        assert row.kind == "cells" and row.ticks == ()

    def test_label_alignment(self):
        mid = TimescaleRow(unit="month", tick=RowTick(label_align="middle"))
        (row,) = plan([mid], mode="axis").rows
        assert row.ticks[0].label_along == 155
        end = TimescaleRow(unit="month", tick=RowTick(label_align="end"))
        assert plan([end], mode="axis").rows[0].ticks[0].label_along == 310

    def test_a_cut_first_segment_is_labelled_but_has_no_mark(self):
        page2 = Span(Q1[30:60], 0, 300)
        (row,) = plan([self.ROW], page2, full_days=Q1, mode="axis").rows
        jan = row.ticks[0]
        assert (jan.label, jan.mark, jan.label_along) == ("Jan", False, 0)
        assert row.ticks[1].mark

    def test_too_many_labels_are_suppressed(self):
        crowded = TimescaleRow(unit="date", tick=RowTick(max_label_count=10))
        (row,) = plan([crowded], mode="axis").rows
        assert len(row.ticks) == 90 and not any(t.show_label for t in row.ticks)

    def test_labels_can_be_turned_off(self):
        (row,) = plan([TimescaleRow(unit="month", tick=RowTick(show_labels=False))], mode="axis").rows
        assert not any(t.show_label for t in row.ticks)


class TestVlines:
    def test_positions_are_the_segment_starts(self):
        row = TimescaleRow(unit="month", vline=LineSpec(color="red"))
        assert plan([row]).rows[0].vlines == (0, 310, 590)

    def test_no_vline_facet_means_no_positions(self):
        assert plan([TimescaleRow(unit="month")]).rows[0].vlines == ()


class FakeDB(CalendarDB):
    def __init__(self, federal=(), flags=None):
        self.federal, self.flags = set(federal), flags or {}

    def is_government_nonworkday(self, daykey, country=None):
        return daykey in self.federal

    def get_special_days_for_date(self, daykey):
        return []

    def get_holidays_for_date(self, daykey, country=None):
        return self.flags.get(daykey, [])

    def get_palette(self, name):
        return None


class TestHolidays:
    WEEK = days(date(2026, 5, 4), 7)  # Mon 4 .. Sun 10

    def span(self):
        return Span(self.WEEK, 0, 70)

    def ctx(self, **holidays):
        theme = make_theme(holidays=holidays)
        ctx = make_ctx(theme, db=FakeDB())
        ctx.config.weekend_style = 1
        return ctx

    def test_weekend_cells_take_the_weekend_fill(self):
        ctx = self.ctx(weekend={"color": "lightblue", "opacity": 0.2})
        (row,) = ts.plan_rows([TimescaleRow(unit="date")], self.span(), ctx).rows
        fills = [(c.fill, c.fill_opacity) for c in row.cells]
        assert fills[:5] == [(None, 1.0)] * 5
        assert fills[5:] == [("lightblue", 0.2)] * 2

    def test_month_cells_are_not_tinted(self):
        ctx = self.ctx(weekend={"color": "lightblue"})
        (row,) = ts.plan_rows([TimescaleRow(unit="month")], self.span(), ctx).rows
        assert {c.fill for c in row.cells} == {None}

    def test_static_icon_is_drawn_only_where_the_theme_sets_one(self):
        ctx = self.ctx(weekend={"icon": "moon"})
        (row,) = ts.plan_rows([TimescaleRow(unit="dow")], self.span(), ctx).rows
        assert [c.icons for c in row.cells[:5]] == [()] * 5
        assert row.cells[5].icons == (ts.CellIcon("moon"),)

    def test_federal_flags_show_when_the_theme_names_a_federal_icon(self):
        flag = {"icon": "flag-us", "displayname": "Memorial Day", "nonworkday": 1, "country": "US"}
        db = FakeDB(federal={"20260504"}, flags={"20260504": [flag]})
        theme = make_theme(holidays={"federal": {"color": "red", "icon": "flag"}})
        ctx = make_ctx(theme, db=db)
        (row,) = ts.plan_rows([TimescaleRow(unit="date")], self.span(), ctx).rows
        assert row.cells[0].icons == (ts.CellIcon("flag-us"),)
        assert row.cells[0].fill == "red"

    def test_holiday_row_always_shows_the_flags(self):
        flag = {"icon": "flag-us", "displayname": "Memorial Day", "nonworkday": 1, "country": "US"}
        db = FakeDB(federal={"20260504"}, flags={"20260504": [flag]})
        ctx = make_ctx(db=db)
        (row,) = ts.plan_rows([TimescaleRow(unit="holiday")], self.span(), ctx).rows
        assert [c.icons for c in row.cells[:2]] == [(ts.CellIcon("flag-us"),), ()]
        assert all(c.label == "" for c in row.cells)

    def test_icons_can_be_switched_off(self):
        flag = {"icon": "flag-us", "displayname": "x", "nonworkday": 1, "country": "US"}
        db = FakeDB(federal={"20260504"}, flags={"20260504": [flag]})
        ctx = make_ctx(make_theme(holidays={"show_icons": False}), db=db)
        (row,) = ts.plan_rows([TimescaleRow(unit="holiday")], self.span(), ctx).rows
        assert all(c.icons == () for c in row.cells)


class Recorder:
    """Stands in for a renderer: records what would be drawn."""

    def __init__(self):
        self.drawing = drawsvg.Drawing(200, 200)
        self.rects, self.texts, self.icons = [], [], []

    def _draw_cell_icons(self, icons, x, w, y, h, size, **kw):
        self.icons.append((icons, x, w, y, h, size))

    def _draw_rect(self, x, y, w, h, **kw):
        self.rects.append((x, y, w, h, kw))

    def _draw_text(self, x, y, text, font, size, **kw):
        self.texts.append((x, y, text, size, kw))


class TestDraw:
    def test_cells_are_rects_with_centred_labels(self):
        p = plan([TimescaleRow(unit="month", format="MMM", fill="gold", height=12)])
        rec = Recorder()
        ts.draw_cells(rec, p, Frame(SPAN), cross0=50)
        assert [(x, y, w, h) for x, y, w, h, _ in rec.rects] == [
            (0, 50, 310, 12),
            (310, 50, 280, 12),
            (590, 50, 310, 12),
        ]
        assert rec.rects[0][4]["fill"] == "gold"
        assert [t[2] for t in rec.texts] == ["Jan", "Feb", "Mar"]
        assert rec.texts[0][0] == 155  # centred on the cell
        assert rec.texts[0][4]["anchor"] == "middle"

    def test_second_row_sits_below_the_first(self):
        p = plan([TimescaleRow(unit="month", height=12), TimescaleRow(unit="week", height=8)])
        rec = Recorder()
        ts.draw_cells(rec, p, Frame(SPAN), cross0=0)
        assert {y for _, y, _, h, _ in rec.rects if h == 8} == {12}

    def test_a_stack_can_grow_the_other_way(self):
        p = plan([TimescaleRow(unit="month", height=12), TimescaleRow(unit="week", height=8)])
        rec = Recorder()
        ts.draw_cells(rec, p, Frame(SPAN), cross0=100, sign=-1)
        assert sorted({(y, h) for _, y, _, h, _ in rec.rects}) == [(80, 8), (88, 12)]

    def test_vertical_frames_swap_axes_and_rotate_labels(self):
        span = Span(Q1, 0, 900)
        p = plan([TimescaleRow(unit="month", format="MMM", height=12)], span)
        rec = Recorder()
        ts.draw_cells(rec, p, Frame(span, Orientation.VERTICAL), cross0=40)
        x, y, w, h, _ = rec.rects[0]
        assert (x, y, w, h) == (40, 0, 12, 310)
        assert "rotate(-90" in rec.texts[0][4]["transform"]

    def test_headings_go_in_the_label_column(self):
        p = plan(
            [TimescaleRow(unit="month", label="Month", height=12), TimescaleRow(unit="date", label="Date", height=8)]
        )
        rec = Recorder()
        ts.draw_headings(rec, p, x=0, width=40, cross0=0, align="end")
        assert [t[2] for t in rec.texts] == ["Month", "Date"]
        assert all(t[0] == 34 and t[4]["anchor"] == "end" and t[4]["max_width"] == 28 for t in rec.texts)  # 6 point pad

    def test_headings_get_a_cell_when_given_a_box(self):
        p = plan([TimescaleRow(unit="month", label="Month", height=12)])
        rec = Recorder()
        ts.draw_headings(rec, p, x=0, width=40, cross0=5, box=make_theme().boxes.header)
        assert [(x, y, w, h) for x, y, w, h, _ in rec.rects] == [(0, 5, 40, 12)]
        assert rec.rects[0][4]["css_class"] == "ec-heading-cell"

    def test_ticks_run_from_the_axis_outward_with_labels_past_them(self):
        p = plan([TimescaleRow(unit="month", format="MMM", tick=RowTick(length=6, label_gap=2))], mode="axis")
        rec = Recorder()
        frame = Frame(SPAN, cross=100)
        ts.draw_ticks(rec, p, frame, make_theme().lines, sign=-1)  # primary side: up the page
        svg = rec.drawing.as_svg()
        assert svg.count('class="ec-axis-tick"') == 3
        assert "M 0 100 L 0 94" in svg
        assert [t[2] for t in rec.texts] == ["Jan", "Feb", "Mar"]
        assert all(t[1] < 94 for t in rec.texts)  # labels beyond the tick ends

    def test_vlines_span_the_content_area(self):
        p = plan([TimescaleRow(unit="month", vline=LineSpec(color="red"))])
        rec = Recorder()
        ts.draw_vlines(rec, p, Frame(SPAN), cross_lo=10, cross_hi=200)
        svg = rec.drawing.as_svg()
        assert svg.count('class="ec-vline"') == 3
        assert "M 310 10 L 310 200" in svg

    def test_icon_cells_draw_their_icons_instead_of_a_label(self):
        flag = {"icon": "flag-us", "displayname": "x", "nonworkday": 1, "country": "US"}
        db = FakeDB(federal={"20260504"}, flags={"20260504": [flag]})
        week = days(date(2026, 5, 4), 3)
        span = Span(week, 0, 30)
        p = ts.plan_rows([TimescaleRow(unit="holiday", height=10)], span, make_ctx(db=db))
        rec = Recorder()
        ts.draw_cells(rec, p, Frame(span), cross0=0)
        assert rec.icons == [([("flag-us", None)], 0.0, 10.0, 0, 10.0, 6.5)]
        assert rec.texts == []


class TestColumnFills:
    def test_a_flat_fill_shades_every_segment(self):
        row = TimescaleRow(unit="month", vfill=RowColumnFill(fill="gold", fill_opacity=0.2))
        assert plan([row]).rows[0].vfills == ((0, 310, "gold", 0.2), (310, 590, "gold", 0.2), (590, 900, "gold", 0.2))

    def test_a_palette_cycles_over_the_segments(self):
        row = TimescaleRow(unit="month", vfill=RowColumnFill(fill_palette=["red", "blue"]))
        assert [f[2] for f in plan([row]).rows[0].vfills] == ["red", "blue", "red"]

    def test_a_vfill_with_no_colour_draws_nothing(self):
        assert plan([TimescaleRow(unit="month", vfill=RowColumnFill())]).rows[0].vfills == ()

    def test_no_facet_no_fills(self):
        assert plan([TimescaleRow(unit="month")]).rows[0].vfills == ()

    def test_fills_are_rects_across_the_content_area(self):
        p = plan([TimescaleRow(unit="month", vfill=RowColumnFill(fill="gold", fill_opacity=0.3))])
        rec = Recorder()
        ts.draw_vfills(rec, p, Frame(SPAN), cross_lo=20, cross_hi=120)
        assert [(x, y, w, h) for x, y, w, h, _ in rec.rects] == [
            (0, 20, 310, 100),
            (310, 20, 280, 100),
            (590, 20, 310, 100),
        ]
        assert rec.rects[0][4]["fill"] == "gold" and rec.rects[0][4]["css_class"] == "ec-vline-fill"


class TestRowSegments:
    def test_segments_are_whole_range_cells_finest_row_first(self):
        rows = [TimescaleRow(unit="month"), TimescaleRow(unit="date")]
        segs = ts.row_segments(rows, Q1, make_ctx())
        assert len(segs[0]) == 90  # the date row is finest
        assert segs[1][0] == (date(2026, 1, 1), date(2026, 2, 1))
