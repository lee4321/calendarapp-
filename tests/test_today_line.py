"""The shared today mark: one line across the content, one label, in every view."""

from __future__ import annotations

import re
from datetime import date, timedelta

import drawsvg

from config.theme_loader import load_theme
from renderers.today_line import draw_today
from shared.orientation import Orientation
from shared.span import Frame, Span

FONT = "OfficinaSans-Book"
DAYS = [date(2026, 2, 2) + timedelta(days=i) for i in range(10)]  # Mon 2 Feb .. Wed 11 Feb


def theme(**today):
    data = {"theme": {"name": "t", "version": "3.0"}, "fonts": {"family": FONT}, "today": today}
    return load_theme(data, font_registry={FONT})


class Recorder:
    def __init__(self):
        self.drawing = drawsvg.Drawing(200, 200)
        self.texts = []

    def _draw_text(self, x, y, text, font, size, **kw):
        self.texts.append((x, y, text, size, kw))

    def lines(self):
        svg = self.drawing.as_svg()
        pat = r'<path d="M ([\d.-]+) ([\d.-]+) L ([\d.-]+) ([\d.-]+)"[^>]*class="ec-today-line"'
        return [tuple(map(float, m)) for m in re.findall(pat, svg)]


def draw(spec, *, frame=None, clock=lambda: date(2026, 2, 5)):
    rec = Recorder()
    frame = frame or Frame(Span(DAYS, 100, 200))
    drawn = draw_today(rec, spec, frame, 20, 120, clock=clock)
    return rec, drawn


def test_the_line_crosses_the_content_at_the_centre_of_todays_cell():
    rec, drawn = draw(theme())
    assert drawn == date(2026, 2, 5)
    assert rec.lines() == [(135.0, 20.0, 135.0, 120.0)]  # Thursday is the 4th cell: 100 + 3.5 * 10


def test_a_pinned_date_beats_the_clock():
    rec, drawn = draw(theme(date="20260209"))
    assert drawn == date(2026, 2, 9)
    assert rec.lines()[0][0] == 175.0


def test_today_can_be_switched_off():
    rec, drawn = draw(theme(show=False))
    assert drawn is None and rec.lines() == [] and rec.texts == []


def test_outside_the_range_draws_nothing():
    rec, drawn = draw(theme(), clock=lambda: date(2027, 1, 1))
    assert drawn is None and rec.lines() == []


def test_a_hidden_day_is_marked_on_the_next_visible_one():
    weekdays = [d for d in DAYS if d.weekday() < 5]
    rec, _ = draw(theme(), frame=Frame(Span(weekdays, 100, 180)), clock=lambda: date(2026, 2, 7))  # a Saturday
    assert rec.lines()[0][0] == 100 + 5.5 * 10  # Monday the 9th, the sixth cell


def test_the_label_sits_right_of_the_line_at_the_chosen_end():
    rec, _ = draw(theme(label="Now", label_position="end", label_offset=4))
    (x, _y, text, _size, kw) = rec.texts[0]
    assert text == "Now" and x > 135 and kw["anchor"] == "start" and kw["css_class"] == "ec-today-label"
    start, _ = draw(theme(label_position="start"))
    end, _ = draw(theme(label_position="end"))
    assert start.texts[0][1] < end.texts[0][1]


def test_an_empty_label_draws_no_text():
    rec, _ = draw(theme(label=""))
    assert rec.texts == []


def test_a_vertical_axis_gets_a_horizontal_line():
    rec, _ = draw(theme(), frame=Frame(Span(DAYS, 100, 200), Orientation.VERTICAL))
    assert rec.lines() == [(20.0, 135.0, 120.0, 135.0)]


class TestExtent:
    """length and direction, in terms of the axis's sides (axis at 70, content 20..120)."""

    def frame(self, orientation=Orientation.HORIZONTAL):
        return Frame(Span(DAYS, 100, 200), orientation, cross=70)

    def lines(self, orientation=Orientation.HORIZONTAL, **today):
        rec, _ = draw(theme(**today), frame=self.frame(orientation))
        return rec.lines()[0]

    def test_whole_area_by_default(self):
        assert self.lines() == (135.0, 20.0, 135.0, 120.0)

    def test_a_length_straddles_the_axis(self):
        assert self.lines(length=40) == (135.0, 50.0, 135.0, 90.0)

    def test_primary_is_above_a_horizontal_axis(self):
        assert self.lines(direction="primary") == (135.0, 20.0, 135.0, 70.0)
        assert self.lines(direction="secondary") == (135.0, 70.0, 135.0, 120.0)
        assert self.lines(direction="primary", length=30) == (135.0, 40.0, 135.0, 70.0)

    def test_primary_is_right_of_a_vertical_axis(self):
        assert self.lines(Orientation.VERTICAL, direction="primary") == (70.0, 135.0, 120.0, 135.0)
        assert self.lines(Orientation.VERTICAL, direction="secondary", length=30) == (40.0, 135.0, 70.0, 135.0)

    def test_a_long_length_is_clamped_to_the_content(self):
        assert self.lines(length=1000) == (135.0, 20.0, 135.0, 120.0)
