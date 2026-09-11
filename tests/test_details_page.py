"""
Tests for the shared companion details page.

The gantt details page and the weekly overflow report are the same page
with different content, written by
:class:`renderers.details_page.DetailsPageWriter`.  What is tested here
is the page itself -- banding, alignment, pagination, chrome -- rather
than either caller's rows.
"""

from __future__ import annotations

from config.config import create_calendar_config, setfontsizes
from renderers.details_page import DetailsColumn, DetailsPageWriter
from shared.date_utils import calc_calendar_range
from visualizers.weekly.layout import WeeklyCalendarLayout
from visualizers.weekly.renderer import WeeklyCalendarRenderer

_COLUMNS = [DetailsColumn("Name", 0.6), DetailsColumn("Count", 0.4, align="right")]


class _Recording(WeeklyCalendarRenderer):
    """Captures the draw calls the writer makes."""

    def __init__(self):
        super().__init__()
        self.rects: list[dict] = []
        self.texts: list[dict] = []

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rects.append({"x": x, "y": y, "w": w, "h": h, **kwargs})
        return super()._draw_rect(x, y, w, h, **kwargs)

    def _draw_text(self, x, y, text, font, size, **kwargs):
        self.texts.append({"x": x, "y": y, "text": text, **kwargs})
        return super()._draw_text(x, y, text, font, size, **kwargs)


def _config(tmp_path, **overrides):
    cfg = create_calendar_config()
    cfg.pageX = 792.0
    cfg.pageY = 612.0
    calc_calendar_range(cfg, "20260401", "20260630")
    cfg.outputfile = str(tmp_path / "page.svg")
    setfontsizes(cfg)
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _write(cfg, rows: int, columns=None) -> tuple[_Recording, int]:
    columns = _COLUMNS if columns is None else columns
    coords = WeeklyCalendarLayout().calculate(cfg)
    renderer = _Recording()
    renderer._drawing = renderer._create_drawing(cfg)
    from renderers.details_page import numbered_page_path

    writer = DetailsPageWriter(
        renderer, cfg, coords,
        lambda n: numbered_page_path(cfg.outputfile, n),
        "Title",
    )
    writer.section("Section", columns)
    for n in range(rows):
        writer.row([f"Row {n}", str(n)], columns)
    return renderer, writer.finish()


def _bands(renderer: _Recording) -> list[dict]:
    return [r for r in renderer.rects if r.get("css_class") == "ec-row-band"]


def _stub_row_band(cfg, **style) -> None:
    """Pin what ``ec-row-band`` resolves to, without a whole theme."""
    from config.styles import BoxStyle

    box = BoxStyle(**style)
    cfg.get_box_style = lambda ec: box if ec == "ec-row-band" else BoxStyle()


def test_rows_are_banded_by_default(tmp_path):
    """Every other row is tinted, so a wide row reads across."""
    renderer, _ = _write(_config(tmp_path), rows=6)

    assert len(_bands(renderer)) == 3


def test_a_theme_turns_banding_off_by_painting_it_none(tmp_path):
    """``ec-row-band`` is the switch, the same one the gantt chart's own
    task table reads."""
    cfg = _config(tmp_path)
    _stub_row_band(cfg, fill="none")
    renderer, _ = _write(cfg, rows=6)

    assert _bands(renderer) == []


def test_band_color_and_opacity_come_from_the_element_style(tmp_path):
    cfg = _config(tmp_path)
    _stub_row_band(cfg, fill="navy", fill_opacity=0.4)
    renderer, _ = _write(cfg, rows=2)

    band = _bands(renderer)[0]
    assert band["fill"] == "navy"
    assert band["fill_opacity"] == 0.4


def test_a_band_covers_its_own_row(tmp_path):
    """The tint sits behind the row's text, not the row above or below."""
    renderer, _ = _write(_config(tmp_path), rows=4)

    band = _bands(renderer)[0]
    baselines = [t["y"] for t in renderer.texts if t["text"] == "Row 1"]
    assert baselines, "the banded row was not drawn"
    assert band["y"] <= baselines[0] <= band["y"] + band["h"]


def test_every_page_opens_on_an_unbanded_row(tmp_path):
    """A break mid-table must not put the stripe on the other foot."""
    cfg = _config(tmp_path)
    renderer, pages = _write(cfg, rows=120)
    assert pages > 1

    # The first row of page 2 is drawn after that page's column header.
    headers = [i for i, t in enumerate(renderer.texts) if t["text"] == "Name"]
    assert len(headers) == pages
    first_row_y = next(
        t["y"] for t in renderer.texts[headers[1]:] if t["text"].startswith("Row ")
    )
    page2_bands = [b for b in _bands(renderer) if b["y"] >= first_row_y]
    assert all(b["y"] > first_row_y for b in page2_bands)


def test_a_right_aligned_column_is_anchored_to_its_right_edge(tmp_path):
    """Column alignment carries over from the caller's column model."""
    renderer, _ = _write(_config(tmp_path), rows=1)

    counts = [t for t in renderer.texts if t["text"] == "0"]
    assert counts and counts[0].get("anchor") == "end"
    names = [t for t in renderer.texts if t["text"] == "Row 0"]
    assert names and names[0].get("anchor") == "start"


def test_shrink_to_content_crops_the_page(tmp_path):
    """``--shrink`` reaches the companion page, as it does the calendar."""
    cfg = _config(tmp_path, shrink_to_content=True)
    renderer, _ = _write(cfg, rows=4)

    assert renderer._drawing.height < cfg.pageY


def test_the_body_size_scales_with_the_page(tmp_path):
    """The listing reads its size from text:details_body, not text:body:
    the gantt chart's task table reads text:body and its rows are a fixed
    gantt_row_height, so that token has to stay small."""
    small = _config(tmp_path)
    large = create_calendar_config()
    large.pageX, large.pageY = 1920.0, 1080.0
    calc_calendar_range(large, "20260401", "20260630")
    large.outputfile = str(tmp_path / "large.svg")
    setfontsizes(large)

    assert large.details_body_font_size > small.details_body_font_size



def test_a_row_mark_is_painted_inside_its_cell(tmp_path):
    """A mark -- a key's swatch, say -- gets its cell's padded bounds and
    the row's baseline, so it sits in the row it keys."""
    cfg = _config(tmp_path)
    coords = WeeklyCalendarLayout().calculate(cfg)
    renderer = _Recording()
    renderer._drawing = renderer._create_drawing(cfg)
    from renderers.details_page import numbered_page_path

    writer = DetailsPageWriter(
        renderer, cfg, coords,
        lambda n: numbered_page_path(cfg.outputfile, n),
        "Title",
    )
    writer.section("Section", _COLUMNS)
    calls: list[tuple[float, float, float, float]] = []
    writer.row(["Row", "1"], _COLUMNS, mark=(1, lambda *args: calls.append(args)))
    writer.finish()

    (x, baseline, width, size), = calls
    row_text = next(t for t in renderer.texts if t["text"] == "Row")
    cell_left = writer.left + writer.width * _COLUMNS[0].width
    assert cell_left < x < cell_left + writer.width * _COLUMNS[1].width
    assert x + width <= writer.right
    assert baseline == row_text["y"]
    assert size == writer.body_size
