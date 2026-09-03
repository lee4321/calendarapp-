"""Every shipped theme pins a uniform timeline callout box width.

`timeline_event_box_width` is `None` by default, and the layout then sizes
each callout from its own text — so a timeline's boxes came out all different
widths, one per title length. Pinning the width in the theme is what makes the
row read as a row. These tests fail if a theme drops the key or sets it to
something the layout would ignore (`None`, 0, negative), which would silently
restore the ragged look.
"""

from __future__ import annotations

from pathlib import Path

import arrow
import pytest

from config.config import CalendarConfig, create_calendar_config, setfontsizes
from config.theme_engine import ThemeEngine
from shared.data_models import Event
from shared.orientation import Orientation, Side
from visualizers.timeline.renderer import TimelineRenderer

THEMES_DIR = Path(__file__).resolve().parent.parent / "config" / "themes"
THEME_FILES = sorted(THEMES_DIR.glob("*.yaml"))


def test_the_theme_directory_was_found():
    """A glob that matched nothing would make every test below vacuous."""
    assert len(THEME_FILES) >= 5


@pytest.mark.parametrize("theme_path", THEME_FILES, ids=lambda p: p.name)
def test_every_theme_sets_a_usable_event_box_width(theme_path: Path):
    config = CalendarConfig()
    engine = ThemeEngine()
    engine.load(theme_path.stem)
    engine.apply(config)

    width = config.timeline_event_box_width
    assert width is not None, (
        f"{theme_path.name} leaves timeline_events.box_width unset, so its "
        "callout boxes are sized per event and come out ragged."
    )
    assert width > 0, f"{theme_path.name} sets a non-positive box_width: {width}"


@pytest.mark.parametrize("theme_path", THEME_FILES, ids=lambda p: p.name)
def test_every_theme_lays_out_callouts_at_one_width(theme_path: Path, tmp_path):
    """End to end: the configured width is the width the boxes actually get."""
    config = create_calendar_config()
    config.pageX, config.pageY = 792.0, 1224.0
    config = setfontsizes(config)
    config.outputfile = str(tmp_path / "t.svg")
    engine = ThemeEngine()
    engine.load(theme_path.stem)
    engine.apply(config)

    renderer = TimelineRenderer()
    renderer._page_width, renderer._page_height = config.pageX, config.pageY
    callouts = renderer._layout_callouts(
        config,
        [
            Event(task_name="A", start="20260105", end="20260105"),
            Event(task_name="A considerably longer milestone name",
                  start="20260220", end="20260220",
                  notes="with a notes line trailing after it"),
            Event(task_name="C", start="20260410", end="20260410"),
        ],
        arrow.get("20260101", "YYYYMMDD"),
        arrow.get("20260630", "YYYYMMDD"),
        axis_origin=(60.0, 400.0),
        axis_length=670.0,
        orientation=Orientation.HORIZONTAL,
        side=Side.PRIMARY,
    )

    widths = {round(c.box_width, 2) for c in callouts}
    assert widths == {round(float(config.timeline_event_box_width), 2)}, (
        f"{theme_path.name} produced callout widths {sorted(widths)}"
    )
