"""
PIT layout calculation.

Computes the page-level coordinate dictionary for the PIT visualizer.
Mirrors `visualizers/timeline/layout.py` — margins, header/footer blocks
via the shared three-column helper, and a single ``PITArea`` rectangle
holding the content region. The renderer is responsible for sub-laying
out the axis, markers, leaders, label boxes, dates, and today line
inside the PITArea.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from visualizers.base import BaseLayout, CoordinateDict

if TYPE_CHECKING:
    from config.config import CalendarConfig


class PITLayout(BaseLayout):
    """Layout calculator for PIT visualization."""

    def calculate(self, config: "CalendarConfig") -> CoordinateDict:
        """Calculate coordinates for PIT rendering."""
        coord: CoordinateDict = {}

        margins = self._calculate_margins(config)
        hf = self._calculate_header_footer(config, margins)

        # Header coordinates
        if config.include_header and hf["header_height"] > 0:
            header_y = config.pageY - margins["top"] - hf["header_height"]
            coord.update(
                self._generate_three_column_coords(
                    margins["left"],
                    config.pageX,
                    header_y,
                    hf["header_height"],
                    "Header",
                    margins["right"],
                )
            )

        # Footer coordinates
        if config.include_footer and hf["footer_height"] > 0:
            coord.update(
                self._generate_three_column_coords(
                    margins["left"],
                    config.pageX,
                    margins["bottom"],
                    hf["footer_height"],
                    "Footer",
                    margins["right"],
                )
            )

        content_x = margins["left"]
        content_y = margins["bottom"] + hf["footer_height"]
        content_w = margins["usable_width"]
        content_h = margins["usable_height"] - hf["header_height"] - hf["footer_height"]

        coord["PITArea"] = (
            round(content_x, 2),
            round(content_y, 2),
            round(content_w, 2),
            round(content_h, 2),
        )

        return self._to_svg_coords(coord, config.pageY)
