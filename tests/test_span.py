"""Span, Frame, pagination and segment clipping."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from shared.orientation import Orientation, Side
from shared.span import Frame, Span, clip_segments, paginate


def days(first: date, n: int, *, weekdays_only: bool = False) -> list[date]:
    out = [first + timedelta(days=i) for i in range(n)]
    return [d for d in out if d.weekday() < 5] if weekdays_only else out


MON = date(2026, 5, 4)


class TestSpan:
    def test_each_day_owns_an_equal_cell(self):
        span = Span(days(MON, 5), 100, 200)
        assert span.day_width == 20
        assert span.start(MON) == 100
        assert span.end(MON) == 120
        assert span.center(MON + timedelta(days=2)) == 150
        assert span.end(span.last) == 200

    def test_hidden_days_own_no_cell(self):
        span = Span(days(MON, 14, weekdays_only=True), 0, 100)  # two working weeks
        assert len(span) == 10
        assert span.start(date(2026, 5, 11)) == 50  # second Monday follows the first Friday

    def test_hidden_day_snaps_forward(self):
        span = Span(days(MON, 14, weekdays_only=True), 0, 100)
        saturday = date(2026, 5, 9)
        assert span.snap_forward(saturday) == date(2026, 5, 11)
        assert span.start(saturday) == span.start(date(2026, 5, 11))

    def test_days_outside_clamp(self):
        span = Span(days(MON, 5), 0, 50)
        assert span.start(MON - timedelta(days=3)) == 0
        assert span.start(MON + timedelta(days=30)) == 40  # the last cell

    def test_extent_covers_only_visible_days_of_a_segment(self):
        span = Span(days(MON, 14, weekdays_only=True), 0, 100)
        # Wed 6 May through Tue 12 May exclusive: Wed, Thu, Fri, Mon (the weekend is hidden)
        assert span.extent(date(2026, 5, 6), date(2026, 5, 12)) == (20, 60)
        assert span.extent(date(2026, 5, 9), date(2026, 5, 11)) is None  # the weekend alone

    def test_position_is_none_outside_the_span(self):
        span = Span(days(MON, 5), 0, 50)
        assert span.position(MON - timedelta(days=1)) is None
        assert span.position(MON) == 5
        assert span.position(MON + timedelta(days=9)) is None

    def test_a_hidden_today_still_gets_a_position(self):
        """A Saturday "today" lands on Monday's cell instead of vanishing."""
        span = Span(days(MON, 14, weekdays_only=True), 0, 100)
        assert span.position(date(2026, 5, 9)) == span.center(date(2026, 5, 11))

    def test_needs_ordered_days(self):
        with pytest.raises(ValueError, match="at least one"):
            Span([], 0, 1)
        with pytest.raises(ValueError, match="increasing"):
            Span([MON, MON], 0, 1)


class TestFrame:
    def test_horizontal_runs_along_x(self):
        frame = Frame(Span(days(MON, 5), 0, 50), Orientation.HORIZONTAL, cross=30)
        assert frame.xy(12, 30) == (12, 30)
        assert frame.rect(10, 20, 30, 5) == (10, 30, 20, 5)
        assert frame.sign(Side.PRIMARY) == -1  # above
        assert frame.sign(Side.SECONDARY) == 1

    def test_vertical_runs_along_y(self):
        frame = Frame(Span(days(MON, 5), 0, 50), Orientation.VERTICAL, cross=30)
        assert frame.xy(12, 30) == (30, 12)
        assert frame.rect(10, 20, 30, 5) == (30, 10, 5, 20)
        assert frame.sign(Side.PRIMARY) == 1  # right
        assert frame.sign(Side.SECONDARY) == -1

    def test_both_needs_splitting_first(self):
        with pytest.raises(ValueError, match="concrete side"):
            Frame(Span(days(MON, 5), 0, 50)).sign(Side.BOTH)


class TestClipSegments:
    PAGE = days(date(2026, 5, 11), 7)  # Mon 11 .. Sun 17

    def test_whole_segment_comes_back_whole(self):
        (piece,) = clip_segments([(date(2026, 5, 12), date(2026, 5, 14), "Tue-Wed")], self.PAGE)
        assert (piece.start, piece.end_exclusive) == (date(2026, 5, 12), date(2026, 5, 14))
        assert not piece.continues_before and not piece.continues_after

    def test_long_segment_is_cut_at_both_edges_with_its_label(self):
        (piece,) = clip_segments([(date(2026, 4, 1), date(2026, 7, 1), "Q2")], self.PAGE)
        assert (piece.start, piece.end_exclusive, piece.label) == (date(2026, 5, 11), date(2026, 5, 18), "Q2")
        assert piece.continues_before and piece.continues_after

    def test_segments_off_the_page_are_dropped(self):
        assert clip_segments([(date(2026, 6, 1), date(2026, 6, 8), "later")], self.PAGE) == []


class TestPaginate:
    def month_row(self, ds):
        """Segments for calendar months over *ds*."""
        out, start = [], ds[0]
        for d in ds[1:] + [ds[-1] + timedelta(days=1)]:
            if d.month != start.month:
                out.append((start, d))
                start = d
        return out

    def test_one_page_when_it_fits(self):
        ds = days(date(2026, 5, 1), 20)
        assert paginate(ds, 31) == [ds]

    def test_plain_split_without_rows(self):
        ds = days(date(2026, 5, 1), 25)
        assert [len(p) for p in paginate(ds, 10)] == [10, 10, 5]

    def test_break_moves_earlier_to_keep_a_month_whole(self):
        ds = days(date(2026, 1, 1), 59)  # Jan + Feb
        month = self.month_row(ds)
        pages = paginate(ds, 40, [month])
        assert [len(p) for p in pages] == [31, 28]
        assert pages[1][0] == date(2026, 2, 1)

    def test_every_page_stays_within_capacity(self):
        ds = days(date(2026, 1, 1), 200)
        pages = paginate(ds, 45, [self.month_row(ds)])
        assert all(len(p) <= 45 for p in pages)
        assert [d for p in pages for d in p] == ds

    def test_a_row_with_a_segment_longer_than_a_page_is_ignored(self):
        ds = days(date(2026, 1, 1), 100)
        quarter = [(date(2026, 1, 1), date(2026, 4, 11))]  # 100 days, longer than a page
        assert [len(p) for p in paginate(ds, 40, [quarter])] == [40, 40, 20]

    def test_finer_rows_win_when_breaks_conflict(self):
        ds = days(date(2026, 1, 1), 90)
        week = [(ds[i], ds[min(i + 7, 89)] if i + 7 < 90 else ds[-1] + timedelta(days=1)) for i in range(0, 90, 7)]
        pages = paginate(ds, 30, [week, self.month_row(ds)])
        # Weeks are finer: every break lands on a week boundary (index multiple of 7).
        starts = [ds.index(p[0]) for p in pages[1:]]
        assert all(s % 7 == 0 for s in starts)

    def test_capacity_must_be_positive(self):
        with pytest.raises(ValueError):
            paginate(days(MON, 3), 0)


class TestIndexedAccess:
    WEEKDAYS = days(date(2026, 5, 4), 14, weekdays_only=True)  # two working weeks

    def span(self):
        return Span(self.WEEKDAYS, 100, 200)

    def test_indexes_snap_either_way_over_hidden_days(self):
        span, saturday = self.span(), date(2026, 5, 9)
        assert span.index_at_or_after(saturday) == 5  # the next Monday
        assert span.index_at_or_before(saturday) == 4  # the Friday before
        assert span.index_at_or_after(date(2026, 6, 1)) is None
        assert span.index_at_or_before(date(2026, 5, 1)) is None

    def test_cells_by_index(self):
        span = self.span()
        assert span.left_of(0) == 100 and span.left_of(5) == 150
        assert span.center_of(0) == 105

    def test_visibility(self):
        span = self.span()
        assert span.is_visible(date(2026, 5, 8)) and not span.is_visible(date(2026, 5, 9))

    def test_boundary_is_the_edge_before_a_day(self):
        span = self.span()
        assert span.boundary(date(2026, 5, 4)) == 100
        assert span.boundary(date(2026, 5, 9)) == 150  # a hidden day sits where the next visible one starts
        assert span.boundary(date(2026, 5, 11)) == 150
        assert span.boundary(date(2026, 6, 1)) == 200  # past the end: the far edge
        assert span.boundary(date(2026, 1, 1)) == 100
