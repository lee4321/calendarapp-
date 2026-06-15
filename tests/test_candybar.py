"""
Tests for the candybar (vertical year-strip) visualization.

Covers the layout (week rows, ISO week numbers, merged month boxes, weekend
suppression, range clipping) and the renderer (day numbers, week numbers,
month-name labels, rotation transform).
"""

from __future__ import annotations

from config.config import create_calendar_config, setfontsizes
from visualizers.candybar.layout import (
    CandybarLayout,
    candybar_suppress_weekends,
    compute_columns,
)
from visualizers.candybar.renderer import CandybarRenderer
from visualizers.factory import VisualizerFactory


def _config(start: str, end: str, **overrides) -> "object":
    cfg = create_calendar_config()
    cfg.pageX = 792.0
    cfg.pageY = 612.0
    cfg.adjustedstart = start
    cfg.adjustedend = end
    cfg.userstart = start
    cfg.userend = end
    # Candybar shows every weekday by default for these structural tests.
    cfg.candybar_suppress_weekends = False
    cfg.weekend_style = 1  # Sunday-start weekend style (includes weekends)
    cfg.candybar_week_start = 1  # Monday/ISO
    for k, v in overrides.items():
        setattr(cfg, k, v)
    setfontsizes(cfg)
    return cfg


# ──────────────────────────────────────────────────────────────────────────
# Layout
# ──────────────────────────────────────────────────────────────────────────

def test_full_year_has_53_week_rows():
    """A full ISO year (2026) spans 53 Monday-start week rows."""
    cfg = _config("20260101", "20261231")
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    week_keys = [k for k in coords if k.startswith("WeekNum_")]
    assert len(week_keys) == 53


def test_iso_week_numbers_match_reference():
    """Week numbers follow the ISO calendar from the Candybar.xlsx reference."""
    cfg = _config("20260101", "20261231")
    layout = CandybarLayout()
    layout.calculate(cfg)
    values = sorted(layout.week_numbers.values())
    # 2026 starts in ISO week 1 and runs through week 53.
    assert values[0] == 1
    assert max(values) == 53


def test_day_cells_hold_in_range_days_only():
    """Out-of-range days at the ends are suppressed (no Cell_ key)."""
    # Range starts Wed 2026-01-07; Mon/Tue of that week must be absent.
    cfg = _config("20260107", "20260110")
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    cells = sorted(k for k in coords if k.startswith("Cell_"))
    assert cells == [
        "Cell_20260107", "Cell_20260108", "Cell_20260109", "Cell_20260110",
    ]


def test_expand_to_week_boundaries_snaps_partial_weeks():
    """The visualizer expands the range to enclosing whole weeks."""
    from visualizers.candybar.visualizer import CandybarVisualizer
    # 2026-02-04 is Wed, 2026-02-10 is Tue (Monday-start weeks).
    cfg = _config("20260204", "20260210")
    CandybarVisualizer._expand_to_week_boundaries(cfg)
    assert cfg.adjustedstart == "20260202"  # back to Monday
    assert cfg.adjustedend == "20260215"    # forward to Sunday


def test_rows_are_full_after_boundary_expansion():
    """After expansion every row is a complete week (no blank end cells)."""
    from visualizers.candybar.visualizer import CandybarVisualizer
    cfg = _config("20260204", "20260210")
    CandybarVisualizer._expand_to_week_boundaries(cfg)
    coords = CandybarLayout().calculate(cfg)
    cells = [k for k in coords if k.startswith("Cell_")]
    weeknums = [k for k in coords if k.startswith("WeekNum_")]
    assert weeknums  # at least one row
    assert len(cells) == 7 * len(weeknums)  # weekends shown → 7 cells/row


def test_month_box_spans_attributed_rows():
    """Each month box height equals (its week-row count) × row height."""
    cfg = _config("20260101", "20260228")
    layout = CandybarLayout()
    coords = layout.calculate(cfg)

    # One row's height, from any day cell.
    cell = next(v for k, v in coords.items() if k.startswith("Cell_"))
    row_h = cell[3]

    jan = next(v for k, v in coords.items() if k.endswith("_202601"))
    feb = next(v for k, v in coords.items() if k.endswith("_202602"))

    # 2026 Jan1–Feb28 spans 9 Monday-start weeks. The Jan26–Feb1 boundary
    # week is attributed to Feb (last visible day rule), giving Jan 4 rows
    # (incl. the Dec29–Jan4 partial week) and Feb 5 rows.
    assert round(jan[3] / row_h) == 4
    assert round(feb[3] / row_h) == 5


def test_month_boxes_are_contiguous_and_non_overlapping():
    """Stacked month boxes tile the strip with no gaps or overlap."""
    cfg = _config("20260101", "20261231")
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    boxes = sorted(
        (v for k, v in coords.items() if k.startswith("MonthBox_")),
        key=lambda b: b[1],  # SVG y (top-down)
    )
    assert len(boxes) == 12
    for upper, lower in zip(boxes, boxes[1:]):
        # bottom edge of the upper box meets the top edge of the next
        assert abs((upper[1] + upper[3]) - lower[1]) < 0.01


def test_boundary_week_attributed_to_new_month():
    """The Jan 27–Feb 2 week is labeled Feb (last visible day rule)."""
    cfg = _config("20260101", "20260228")
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    # Feb 1 (Sun) and Jan 27 (Tue) live in the same week row.
    jan27 = coords["Cell_20260127"]
    feb01 = coords["Cell_20260201"]
    assert jan27[1] == feb01[1]  # same row (same SVG y)
    feb_box = next(v for k, v in coords.items() if k.endswith("_202602"))
    # The shared row's top must fall within the Feb box's vertical span.
    assert feb_box[1] <= feb01[1] + 0.01


# ──────────────────────────────────────────────────────────────────────────
# Box width
# ──────────────────────────────────────────────────────────────────────────

def test_day_cells_are_square_by_default():
    """Default day cells have width == height (square)."""
    cfg = _config("20260101", "20260131")
    coords = CandybarLayout().calculate(cfg)
    cell = next(v for k, v in coords.items() if k.startswith("Cell_"))
    assert abs(cell[2] - cell[3]) < 0.01


def test_cell_width_override_sets_absolute_width():
    """candybar_cell_width fixes the day-cell width independent of height."""
    cfg = _config("20260101", "20260131", candybar_cell_width=20.0)
    coords = CandybarLayout().calculate(cfg)
    cell = next(v for k, v in coords.items() if k.startswith("Cell_"))
    assert abs(cell[2] - 20.0) < 0.01


def test_column_ratios_scale_weeknum_and_month_widths():
    """Week-number and month-box widths follow the configured ratios."""
    cfg = _config(
        "20260101", "20260131",
        candybar_cell_width=10.0,
        candybar_weeknum_col_ratio=0.5,
        candybar_month_col_ratio=2.0,
    )
    cols = compute_columns(cfg, 0.0, 10.0)
    assert abs(cols.day_col_w - 10.0) < 0.01
    assert abs(cols.wn_w - 5.0) < 0.01
    assert abs(cols.month_w - 20.0) < 0.01


# ──────────────────────────────────────────────────────────────────────────
# Weekend suppression
# ──────────────────────────────────────────────────────────────────────────

def test_suppress_weekends_drops_saturday_sunday():
    cfg = _config("20260105", "20260111", candybar_suppress_weekends=True)
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    cells = sorted(k for k in coords if k.startswith("Cell_"))
    # Mon–Fri only (Jan 5–9); Sat 10 / Sun 11 dropped.
    assert cells == [
        "Cell_20260105", "Cell_20260106", "Cell_20260107",
        "Cell_20260108", "Cell_20260109",
    ]


def test_weekends_shown_by_default_regardless_of_weekend_style():
    """Candybar shows weekends by default and does not inherit weekend_style."""
    cfg = _config("20260105", "20260111")
    cfg.candybar_suppress_weekends = None
    cfg.weekend_style = 0  # workweek style must NOT suppress candybar weekends
    assert candybar_suppress_weekends(cfg) is False

    cfg.weekend_style = 1
    assert candybar_suppress_weekends(cfg) is False


def test_explicit_flag_suppresses_weekends():
    """Weekends are dropped only when the flag is explicitly set."""
    cfg = _config("20260105", "20260111")
    cfg.weekend_style = 1
    cfg.candybar_suppress_weekends = True
    assert candybar_suppress_weekends(cfg) is True


def test_leading_weekend_only_week_is_dropped():
    """A start date on a suppressed weekend must not yield a blank first row."""
    # 2026-02-01 is a Sunday; with weekends suppressed the Jan26–Feb1 week
    # (ISO week 5) has no visible in-range day and must be omitted.
    cfg = _config("20260201", "20260715", candybar_suppress_weekends=True)
    layout = CandybarLayout()
    layout.calculate(cfg)
    first_weeks = [v for _, v in sorted(layout.week_numbers.items())][:1]
    assert first_weeks == [6]


def test_trailing_weekend_only_week_is_dropped():
    """An end date on a suppressed weekend must not yield a blank last row."""
    # 2026-02-08 is a Sunday; the Feb2–8 week's only in-range weekday is none
    # beyond Feb 7? Feb 7 is Sat (suppressed), so end on Sun-> last visible day
    # must come from an earlier week. Use a Saturday end to exercise trailing.
    cfg = _config("20260202", "20260207", candybar_suppress_weekends=True)
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    cells = sorted(k for k in coords if k.startswith("Cell_"))
    # Mon Feb2 – Fri Feb6 only; Sat Feb7 suppressed, no blank trailing row.
    assert cells == [
        "Cell_20260202", "Cell_20260203", "Cell_20260204",
        "Cell_20260205", "Cell_20260206",
    ]
    assert len(layout.week_numbers) == 1


def test_header_labels_reflect_weekend_suppression():
    cfg = _config("20260105", "20260111", candybar_suppress_weekends=True)
    cols = compute_columns(cfg, 0.0, 100.0)
    assert cols.day_labels == ["Mon", "Tue", "Wed", "Thu", "Fri"]

    cfg.candybar_suppress_weekends = False
    cols = compute_columns(cfg, 0.0, 100.0)
    assert cols.day_labels == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ──────────────────────────────────────────────────────────────────────────
# Renderer
# ──────────────────────────────────────────────────────────────────────────

class _CaptureRenderer(CandybarRenderer):
    """Records text draws and their transforms instead of emitting SVG."""

    def __init__(self):
        super().__init__()
        self.texts: list[dict] = []
        self.rects: list[dict] = []

    def _draw_text(self, x, y, text, font_name, font_size, **kwargs):
        self.texts.append({"text": text, "transform": kwargs.get("transform")})

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rects.append({"x": x, "y": y, "w": w, "h": h, **kwargs})

    def _draw_circle(self, *args, **kwargs):
        pass

    def _draw_icon_svg(self, *args, **kwargs):
        return False

    def _draw_mini_svg_pattern(self, *args, **kwargs):
        pass


class _FakeDB:
    """Minimal CalendarDB stand-in for renderer unit tests."""

    def get_holidays_for_date(self, daykey, country):
        return []

    def get_special_days_for_date(self, daykey):
        return []

    def get_all_patterns(self):
        return {}

    def get_all_icons(self):
        return {}


def _render(cfg) -> _CaptureRenderer:
    layout = CandybarLayout()
    coords = layout.calculate(cfg)
    r = _CaptureRenderer()
    r.set_week_numbers(layout.week_numbers)
    r._config = cfg
    r._load_icon_svg_cache = lambda db: None  # skip DB icon load
    r._render_content(cfg, coords, [], _FakeDB())
    return r


def test_renderer_draws_day_numbers_week_numbers_and_months():
    cfg = _config("20260101", "20260131")
    r = _render(cfg)
    texts = [t["text"] for t in r.texts]
    assert "Jan" in texts        # month-box label
    assert "15" in texts         # a day number
    assert any(t.startswith("W") and t[1:].isdigit() for t in texts)  # week number
    assert "Mon" in texts        # header label


def test_month_label_rotation_emits_transform():
    cfg = _config("20260101", "20260131", candybar_month_rotation=-90)
    r = _render(cfg)
    jan = next(t for t in r.texts if t["text"] == "Jan")
    assert jan["transform"] is not None
    assert "rotate(-90" in jan["transform"]


def test_no_rotation_emits_no_transform():
    cfg = _config("20260101", "20260131", candybar_month_rotation=0)
    r = _render(cfg)
    jan = next(t for t in r.texts if t["text"] == "Jan")
    assert jan["transform"] is None


# ──────────────────────────────────────────────────────────────────────────
# Base shading (weekends + month banding)
# ──────────────────────────────────────────────────────────────────────────

def test_weekend_fill_shades_only_weekend_cells():
    # One full ISO week, weekends shown.
    cfg = _config("20260105", "20260111", candybar_weekend_fill="aliceblue")
    r = _render(cfg)
    weekend_rects = [rc for rc in r.rects if rc.get("css_class") == "ec-weekend"]
    # Sat Jan 10 + Sun Jan 11 only.
    assert len(weekend_rects) == 2
    assert all(rc.get("fill") == "aliceblue" for rc in weekend_rects)


def test_no_weekend_fill_by_default():
    cfg = _config("20260105", "20260111")
    r = _render(cfg)
    assert not [rc for rc in r.rects if rc.get("css_class") == "ec-weekend"]


def test_month_shading_bands_alternate_months():
    # Default cycle ["none", "gainsboro"] keyed by (year*12+month) % 2:
    # 2026-01 -> gainsboro (shaded), 2026-02 -> none (unshaded).
    cfg = _config("20260105", "20260211", candybar_month_shading=True)
    r = _render(cfg)
    bands = [rc for rc in r.rects if rc.get("css_class") == "ec-month-band"]
    assert bands
    assert all(rc.get("fill") == "gainsboro" for rc in bands)


def test_no_month_shading_by_default():
    cfg = _config("20260105", "20260211")
    r = _render(cfg)
    assert not [rc for rc in r.rects if rc.get("css_class") == "ec-month-band"]


# ──────────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────────

def test_candybar_registered_in_factory():
    assert "candybar" in VisualizerFactory.available_types()
    assert VisualizerFactory.create("candybar").name == "candybar"
