"""
Compact Activities Plan layout calculation.

Calculates coordinates for the compactplan visualization, including
header/footer blocks and the main content area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from visualizers.base import BaseLayout, CoordinateDict

if TYPE_CHECKING:
    from config.config import CalendarConfig


class CompactPlanLayout(BaseLayout):
    """Layout calculator for compact activities plan visualization."""

    def calculate(self, config: "CalendarConfig") -> CoordinateDict:
        """Calculate coordinates for compactplan rendering."""
        coord: CoordinateDict = {}

        margins = self._calculate_margins(config)
        hf = self._calculate_header_footer(config, margins)

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
        content_h = (
            margins["usable_height"] - hf["header_height"] - hf["footer_height"]
        )

        coord["CompactPlanArea"] = (
            round(content_x, 2),
            round(content_y, 2),
            round(content_w, 2),
            round(content_h, 2),
        )

        return self._to_svg_coords(coord, config.pageY)
