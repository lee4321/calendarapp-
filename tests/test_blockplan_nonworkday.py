"""Tests for blockplan non-workday fill rules on date/dow timebands."""

from __future__ import annotations

from pathlib import Path

from band_helpers import set_bands, set_fields, update_theme
from fakes import FakeCalendarDB

from config.config import CalendarConfig, create_calendar_config, setfontsizes
from visualizers.blockplan.layout import BlockPlanLayout
from visualizers.blockplan.renderer import BlockPlanRenderer


class _NonworkDB(FakeCalendarDB):
    """Stub DB where 2026-02-16 is a US federal holiday (Presidents' Day)."""

    HOLIDAY = "20260216"

    def get_palette(self, name):
        return None

    def is_nonworkday(self, daykey, country=None):
        return daykey == _NonworkDB.HOLIDAY

    def is_government_nonworkday(self, daykey, country=None):
        return daykey == _NonworkDB.HOLIDAY

    def get_special_days_for_date(self, daykey):
        return []

    def resolve_color_name(self, name):
        return name


class _Capture(BlockPlanRenderer):
    def __init__(self):
        super().__init__()
        self.rects: list[dict] = []

    def _draw_text(self, *a, **kw):
        return None

    def _draw_rect(self, x, y, w, h, **kwargs):
        self.rects.append({"x": x, "y": y, "w": w, "h": h, **kwargs})
        super()._draw_rect(x, y, w, h, **kwargs)

    def _draw_line(self, *a, **kw):
        return None


def _cfg(output: Path) -> CalendarConfig:
    c = create_calendar_config()
    c.pageX, c.pageY = 792.0, 1224.0
    c = setfontsizes(c)
    c.weekend_style = 1  # show weekends so Sat/Sun columns exist
    c.userstart = "20260209"  # Mon
    c.userend = "20260220"  # Fri
    c.adjustedstart = "20260209"
    c.adjustedend = "20260220"
    c.outputfile = str(output)
    set_bands(c, primary=[{"label": "Day", "unit": "date", "date_format": "D", "show_every": 1}])
    set_bands(c, secondary=[])
    set_fields(c, blockplan_swimlanes=[{"name": "Lane", "match": {}}])
    return c


def test_nonworkday_fills_come_from_the_theme_holidays(tmp_path):
    """The theme's holidays fills tint the holiday and weekend cells."""
    cfg = _cfg(tmp_path / "bp.svg")
    update_theme(cfg, holidays={"federal": {"color": "#FF0000"}, "weekend": {"color": "#CCCCCC"}})
    coords = BlockPlanLayout().calculate(cfg)

    r = _Capture()
    r.render(cfg, coords, events=[], db=_NonworkDB())

    band_rects = [rc for rc in r.rects if rc.get("css_class") == "ec-band-cell"]
    # Weekend cells should have grey fill
    assert any(rc.get("fill") == "#CCCCCC" for rc in band_rects), "expected weekend cells to be filled with #CCCCCC"
    # Federal holiday cell should have red fill
    assert any(rc.get("fill") == "#FF0000" for rc in band_rects), (
        "expected federal holiday cell to be filled with #FF0000"
    )


def test_no_fill_when_nothing_configured(tmp_path):
    """Without nonworkday config, weekend cells keep the default band fill."""
    cfg = _cfg(tmp_path / "bp3.svg")
    coords = BlockPlanLayout().calculate(cfg)

    r = _Capture()
    r.render(cfg, coords, events=[], db=_NonworkDB())

    band_rects = [rc for rc in r.rects if rc.get("css_class") == "ec-band-cell"]
    # No cell should be red or grey since we didn't configure those
    for rc in band_rects:
        assert rc.get("fill") not in {"#FF0000", "#CCCCCC"}
