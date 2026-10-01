"""Both Gantt band stacks accept any number of time bands.

`gantt.top_bands` and `gantt.bottom_bands` are plain lists, and neither
the layout nor the renderer caps their length. What is bounded is the
*height* they may take together: past `MAX_CHROME_SHARE` of the content
height every chrome row scales down proportionally, so the task body
survives rather than a band being dropped.
"""

from __future__ import annotations

import pytest
from test_gantt_marks import render, task

from config.config import CalendarConfig

_PAGE = (792.0, 612.0)


def bands(count: int, row_height: float = 10.0, unit: str = "month") -> list[dict]:
    return [{"label": f"B{index}", "unit": unit, "row_height": row_height} for index in range(count)]


@pytest.fixture
def config() -> CalendarConfig:
    config = CalendarConfig()
    config.pageX, config.pageY = _PAGE
    return config


# ── Layout ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("setting", "anchor"), [("start", "start"), ("middle", "middle"), ("end", "end")])
def test_band_headings_follow_the_timescale_alignment(setting, anchor):
    renderer = render(
        [task()],
        theme_sections={"timescale": {"heading_align": setting}},
        gantt_top_time_bands=[{"label": "Month", "unit": "month", "row_height": 8}],
        gantt_bottom_time_bands=[],
    )

    (heading,) = [t for t in renderer.texts if t.get("css_class") == "ec-heading"]
    assert heading["anchor"] == anchor
