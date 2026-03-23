"""
Tests for duration bar height and placement with and without notes when
include_notes is enabled.

Covers:
- _place_duration_rect only doubles height when the event has notes.
- _place_duration only selects a two-row slot when BOTH rows are free on every
  duration day, preventing double-height bars from overlapping an already-placed
  single-height bar in the upper row (e.g. "API Design Phase" overlaying
  "PI-7 Release Cycle" as observed in the --includenotes output).
"""

from collections import defaultdict

from config.config import create_calendar_config, setfontsizes
from shared.data_models import Event
from visualizers.weekly.renderer import WeeklyCalendarRenderer


class _CaptureDurationRenderer(WeeklyCalendarRenderer):
    """Renderer that captures rect and text calls instead of drawing them."""

    def __init__(self):
        super().__init__()
        self.rects = []  # list of (x, y, w, h, kwargs)
        self.text_calls = []  # list of text strings (for content checks)
        self.text_events = []  # list of (x, y, text, font_size) for ordering checks
        self.text_draws = []  # list of draw metadata for style assertions

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rects.append((x, y, w, h, kwargs))

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.text_calls.append(text)
        self.text_events.append((x, y, text, font_size))
        self.text_draws.append(
            {
                "x": x,
                "y": y,
                "text": text,
                "font_name": font_name,
                "font_size": font_size,
                "fill": kwargs.get("fill"),
            }
        )

    def _draw_hash_lines(self, *args, **kwargs):
        pass

    def _draw_line(self, *args, **kwargs):
        pass

    def _process_overflow(self, *args, **kwargs):
        pass


def _base_config(include_notes=True):
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.include_notes = include_notes
    config.maxrows = 10
    return config


def _make_rowcoords(config, days, x=0.0, base_y=100.0, w=158.4):
    """Build a minimal rowcoords dict for the given list of day keys."""
    textrowheight = round(config.weekly_name_text_font_size * 1.3, 2)
    rowcoords = defaultdict(dict)
    for day in days:
        y = base_y
        for r in range(config.maxrows):
            texty = y + textrowheight * 0.2
            rowcoords[day][r] = (
                x,
                y,
                w,
                textrowheight,
                x + 2,
                texty,
                x + 1,
                texty,
                False,
            )
            y = round(y - textrowheight, 2)
    return rowcoords


def _mark_row_used(rowcoords, days, rowid):
    """Mark a specific row as used on all given days (simulates a prior placed bar)."""
    for day in days:
        x, y, w, h, tx, ty, ix, iy, _ = rowcoords[day][rowid]
        rowcoords[day][rowid] = (x, y, w, h, tx, ty, ix, iy, True)
    return rowcoords


def _make_event(task_name, start, end, notes=None):
    return Event(
        task_name=task_name,
        start=start,
        end=end,
        notes=notes,
        milestone=False,
        percent_complete=0,
        priority=1,
        datekey=start,
    )


def _get_duration_rect_height(config, event, days):
    """Run _place_duration_rect and return the height of the drawn rect(s)."""
    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)
    textrowheight = round(config.weekly_name_text_font_size * 1.3, 2)

    # Determine rowids the same way _place_duration does
    has_notes = bool(event.notes and str(event.notes).strip())
    if config.include_notes and has_notes:
        rowids = [0, 1]
    else:
        rowids = [0]

    renderer._place_duration_rect(config, event, days, rowcoords, rowids)

    # Filter to only duration rects (lightsteelblue fill), not day box backgrounds
    duration_rects = [r for r in renderer.rects if r[4].get("fill") == "lightsteelblue"]
    assert duration_rects, "No duration rect was drawn"
    return duration_rects[0][3], textrowheight  # (height, single_row_height)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_duration_no_notes_single_height_when_include_notes_enabled():
    """Duration without notes should use single-row height even with include_notes=True."""
    config = _base_config(include_notes=True)
    event = _make_event("Task A", "20260302", "20260304", notes=None)
    days = ["20260302", "20260303", "20260304"]

    height, textrowheight = _get_duration_rect_height(config, event, days)

    assert abs(height - textrowheight) < 0.01, (
        f"Expected single-row height {textrowheight:.2f}, got {height:.2f}"
    )


def test_duration_empty_notes_single_height_when_include_notes_enabled():
    """Duration with empty-string notes should use single-row height."""
    config = _base_config(include_notes=True)
    event = _make_event("Task B", "20260302", "20260304", notes="")
    days = ["20260302", "20260303", "20260304"]

    height, textrowheight = _get_duration_rect_height(config, event, days)

    assert abs(height - textrowheight) < 0.01, (
        f"Expected single-row height {textrowheight:.2f}, got {height:.2f}"
    )


def test_duration_whitespace_notes_single_height():
    """Duration with whitespace-only notes should use single-row height."""
    config = _base_config(include_notes=True)
    event = _make_event("Task C", "20260302", "20260304", notes="   ")
    days = ["20260302", "20260303", "20260304"]

    height, textrowheight = _get_duration_rect_height(config, event, days)

    assert abs(height - textrowheight) < 0.01, (
        f"Expected single-row height {textrowheight:.2f}, got {height:.2f}"
    )


def test_duration_with_notes_double_height():
    """Duration with actual notes should use double-row height when include_notes=True."""
    config = _base_config(include_notes=True)
    event = _make_event("Task D", "20260302", "20260304", notes="Some note text")
    days = ["20260302", "20260303", "20260304"]

    height, textrowheight = _get_duration_rect_height(config, event, days)

    assert abs(height - textrowheight * 2) < 0.01, (
        f"Expected double-row height {textrowheight * 2:.2f}, got {height:.2f}"
    )


def test_duration_with_notes_include_notes_disabled_single_height():
    """Duration with notes but include_notes=False should use single-row height."""
    config = _base_config(include_notes=False)
    event = _make_event("Task E", "20260302", "20260304", notes="Some note text")
    days = ["20260302", "20260303", "20260304"]

    height, textrowheight = _get_duration_rect_height(config, event, days)

    assert abs(height - textrowheight) < 0.01, (
        f"Expected single-row height {textrowheight:.2f}, got {height:.2f}"
    )


def test_place_duration_no_notes_marks_one_row():
    """_place_duration marks only one row used when event has no notes."""
    config = _base_config(include_notes=True)
    event = _make_event("Task F", "20260302", "20260304", notes=None)
    days = ["20260302", "20260303", "20260304"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    rowcoords, had_overflow = renderer._place_duration(
        config, days, rowcoords, event, days[0]
    )

    assert not had_overflow
    # Only row 0 should be used; row 1 should remain free on all days
    for day in days:
        _, _, _, _, _, _, _, _, used0 = rowcoords[day][0]
        _, _, _, _, _, _, _, _, used1 = rowcoords[day][1]
        assert used0, f"Row 0 should be marked used on {day}"
        assert not used1, f"Row 1 should remain free on {day} when event has no notes"


def test_place_duration_with_notes_marks_two_rows():
    """_place_duration marks two rows used when event has notes."""
    config = _base_config(include_notes=True)
    event = _make_event("Task G", "20260302", "20260304", notes="Sprint notes")
    days = ["20260302", "20260303", "20260304"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    rowcoords, had_overflow = renderer._place_duration(
        config, days, rowcoords, event, days[0]
    )

    assert not had_overflow
    # Both rows 0 and 1 should be used on all days
    for day in days:
        _, _, _, _, _, _, _, _, used0 = rowcoords[day][0]
        _, _, _, _, _, _, _, _, used1 = rowcoords[day][1]
        assert used0, f"Row 0 should be marked used on {day}"
        assert used1, f"Row 1 should be marked used on {day} when event has notes"


def test_duration_with_notes_renders_notes_text_on_bar():
    """
    When a duration event has notes and include_notes=True, the notes text
    must be drawn on the bar in addition to the task name.

    Previously the bar was doubled in height but the notes line was never
    rendered, leaving the lower half of the bar empty.
    """
    config = _base_config(include_notes=True)
    event = _make_event(
        "Sprint 10", "20260302", "20260304", notes="Sprint goal: auth module"
    )
    days = ["20260302", "20260303", "20260304"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    # Use rowids [0, 1] — both rows free
    renderer._place_duration_rect(config, event, days, rowcoords, [0, 1])

    # Task name must appear
    assert any("Sprint 10" in t for t in renderer.text_calls), (
        "Task name 'Sprint 10' was not rendered on the duration bar"
    )
    # Notes text must also appear
    assert any("Sprint goal" in t for t in renderer.text_calls), (
        "Notes text was not rendered on the duration bar even though event has notes"
    )


def test_duration_with_notes_task_name_above_notes_text():
    """
    The task name must be rendered in the upper half of a double-height bar and
    the notes text in the lower half.

    In SVG coordinates (Y increases downward) the task name must have a smaller
    Y value than the notes — i.e. name_ty < notes_ty.

    Previously the coordinates were swapped: the task name was drawn at the
    lower row's Y (visually below) and the notes at the upper row's Y (above),
    making notes appear above the event name.
    """
    config = _base_config(include_notes=True)
    event = _make_event(
        "Sprint 10", "20260302", "20260304", notes="Sprint goal: auth module"
    )
    days = ["20260302", "20260303", "20260304"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    # _make_rowcoords builds rows with Y decreasing per row (row 0 is topmost
    # in the test grid: Y=base_y, row 1 is Y=base_y-textrowheight, etc.)
    # That matches real _day_box_coords: row 0 has the highest PDF Y and is
    # therefore rendered at the smallest SVG Y (topmost on screen).
    renderer._place_duration_rect(config, event, days, rowcoords, [0, 1])

    # Find the Y positions of the task name call and the notes call
    name_events = [
        (y, fs) for _, y, txt, fs in renderer.text_events if "Sprint 10" in txt
    ]
    notes_events = [
        (y, fs) for _, y, txt, fs in renderer.text_events if "Sprint goal" in txt
    ]

    assert name_events, "Task name text was not rendered"
    assert notes_events, "Notes text was not rendered"

    name_y = name_events[0][0]
    notes_y = notes_events[0][0]

    # rowcoords uses PDF-space Y (increases upward), so the topmost row has the
    # LARGER Y value.  The task name must be in the upper (larger-Y) row and
    # notes in the lower (smaller-Y) row.
    assert name_y > notes_y, (
        f"Task name Y ({name_y:.2f}) must be greater than notes Y ({notes_y:.2f}) "
        f"in PDF-space coordinates so the name appears above the notes on screen"
    )


def test_duration_without_notes_does_not_render_notes_text():
    """Duration bars with no notes must not render any notes text."""
    config = _base_config(include_notes=True)
    event = _make_event("PI-7 Release Cycle", "20260302", "20260304", notes=None)
    days = ["20260302", "20260303", "20260304"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    renderer._place_duration_rect(config, event, days, rowcoords, [0])

    # Only the task name; no second text call for notes
    assert len(renderer.text_calls) == 1, (
        f"Expected exactly 1 text call (task name), got {len(renderer.text_calls)}: "
        f"{renderer.text_calls}"
    )


def test_duration_with_notes_uses_duration_specific_fonts_and_colors():
    """Duration name/notes should use duration-specific font and color fields."""
    config = _base_config(include_notes=True)
    config.weekly_name_text_font_name = "RobotoCondensed-Bold"
    config.weekly_name_text_font_color = "darkgreen"
    config.weekly_notes_text_font_name = "JuliaMono-RegularItalic"
    config.weekly_notes_text_font_color = "red"
    event = _make_event(
        "Sprint 10", "20260302", "20260304", notes="Sprint goal: auth module"
    )
    days = ["20260302", "20260303", "20260304"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)
    renderer._place_duration_rect(config, event, days, rowcoords, [0, 1])

    name_draw = next((d for d in renderer.text_draws if "Sprint 10" in d["text"]), None)
    notes_draw = next(
        (d for d in renderer.text_draws if "Sprint goal" in d["text"]), None
    )

    assert name_draw is not None, "Duration name text was not rendered"
    assert notes_draw is not None, "Duration notes text was not rendered"
    assert name_draw["font_name"] == "RobotoCondensed-Bold"
    assert name_draw["fill"] == "darkgreen"
    assert notes_draw["font_name"] == "JuliaMono-RegularItalic"
    assert notes_draw["fill"] == "red"


def test_event_notes_use_event_notes_font_and_color():
    """Event notes should use weekly_notes_text_* style fields, not weekly_name_text_*."""
    config = _base_config(include_notes=True)
    config.weekly_name_text_font_name = "RobotoCondensed-Regular"
    config.weekly_name_text_font_color = "darkslategrey"
    config.weekly_notes_text_font_name = "JuliaMono-RegularItalic"
    config.weekly_notes_text_font_color = "red"
    day = "20260303"
    event = _make_event("Build API", day, day, notes="Owner: platform team")

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, [day])
    rowcoords, had_overflow = renderer._place_event_and_notes(
        config, rowcoords, event, day
    )

    assert not had_overflow

    name_draw = next((d for d in renderer.text_draws if "Build API" in d["text"]), None)
    notes_draw = next(
        (d for d in renderer.text_draws if "Owner: platform team" in d["text"]), None
    )

    assert name_draw is not None, "Event name text was not rendered"
    assert notes_draw is not None, "Event notes text was not rendered"
    assert name_draw["font_name"] == "RobotoCondensed-Regular"
    assert name_draw["fill"] == "darkslategrey"
    assert notes_draw["font_name"] == "JuliaMono-RegularItalic"
    assert notes_draw["fill"] == "red"


def test_place_duration_with_notes_skips_pair_when_upper_row_occupied():
    """
    Regression test for "API Design Phase" overlaying "PI-7 Release Cycle".

    When include_notes=True and an event has notes, _place_duration must not
    select a two-row slot [rowid-1, rowid] unless BOTH rows are free on every
    duration day.  Previously it only checked that rowid was free, letting it
    blindly use rowid-1 even when that row was already occupied by another bar.

    Setup: row 0 is already occupied (simulating a prior bar like PI-7 Release
    Cycle).  The event-with-notes should land at rows [1, 2], not [0, 1].
    """
    config = _base_config(include_notes=True)
    event = _make_event(
        "API Design Phase", "20260304", "20260306", notes="Design notes"
    )
    days = ["20260304", "20260305", "20260306"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    # Simulate a previously placed bar occupying row 0 on all days (PI-7 Release Cycle)
    rowcoords = _mark_row_used(rowcoords, days, 0)

    rowcoords, had_overflow = renderer._place_duration(
        config, days, rowcoords, event, days[0]
    )

    assert not had_overflow, "Should place without overflow when rows 1 & 2 are free"

    # Row 0 should still be occupied by the prior bar, undisturbed
    for day in days:
        _, _, _, _, _, _, _, _, used0 = rowcoords[day][0]
        assert used0, f"Row 0 (prior bar) should remain used on {day}"

    # Rows 1 and 2 should now be consumed by the new event
    for day in days:
        _, _, _, _, _, _, _, _, used1 = rowcoords[day][1]
        _, _, _, _, _, _, _, _, used2 = rowcoords[day][2]
        assert used1, f"Row 1 should be marked used on {day}"
        assert used2, f"Row 2 should be marked used on {day}"


def test_place_duration_with_notes_does_not_overlap_occupied_upper_row():
    """
    The drawn rect for a notes-duration must not visually overlap a
    pre-occupied row.

    Row 0 is pre-occupied (simulating PI-7 Release Cycle).  When a second
    event with notes is placed, it must select rows [1, 2].  In SVG
    coordinates (Y increasing downward) the rect's base Y comes from the
    higher-numbered row (row 2), and H*2 expands upward to cover row 1 as
    well.  The key invariant is that the rect must not start at or above
    row 0's Y value (which would paint over the pre-existing bar).
    """
    config = _base_config(include_notes=True)
    event = _make_event("New Bar", "20260309", "20260311", notes="Has notes")
    days = ["20260309", "20260310", "20260311"]

    renderer = _CaptureDurationRenderer()
    rowcoords = _make_rowcoords(config, days)

    # Record row 0's Y and row 2's Y before marking row 0 as used.
    # Row 0 is the topmost slot (highest Y in our coords); row 2 is two below it.
    row0_y = rowcoords[days[0]][0][1]
    row2_y = rowcoords[days[0]][2][1]
    textrowheight = round(config.weekly_name_text_font_size * 1.3, 2)

    rowcoords = _mark_row_used(rowcoords, days, 0)

    renderer._place_duration(config, days, rowcoords, event, days[0])

    duration_rects = [r for r in renderer.rects if r[4].get("fill") == "lightsteelblue"]
    assert duration_rects, "Expected at least one duration rect to be drawn"

    drawn_y = duration_rects[0][1]
    drawn_h = duration_rects[0][3]

    # The rect must not start at row 0's Y (that would overlay the prior bar)
    assert abs(drawn_y - row0_y) > 0.01, (
        f"Bar started at row 0's Y ({drawn_y:.2f}), overlapping the pre-occupied row"
    )
    # The rect should start at row 2's Y (the base of the [1,2] pair)
    assert abs(drawn_y - row2_y) < 0.01, (
        f"Bar should start at row 2's Y ({row2_y:.2f}), got {drawn_y:.2f}"
    )
    # Height should be exactly 2× textrowheight
    assert abs(drawn_h - textrowheight * 2) < 0.01, (
        f"Bar height should be 2× textrowheight ({textrowheight * 2:.2f}), got {drawn_h:.2f}"
    )
