"""
Base SVG renderer with shared functionality.

Provides common SVG rendering operations used across all visualization types.
Uses drawsvg library for SVG generation.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import arrow
import drawsvg

from renderers.glyph_cache import text_to_svg_group
from renderers.text_utils import shrinktext, string_width

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict, VisualizationResult


logger = logging.getLogger(__name__)

_NONE_COLORS = {"", "none", "transparent"}


def _is_none_color(color: str | None) -> bool:
    """Return True if the color string means 'no color' (transparent/invisible)."""
    return color is None or str(color).strip().lower() in _NONE_COLORS


def _r(v: float, n: int = 2) -> float:
    """Round a numeric value for cleaner SVG output."""
    return round(v, n)


class BaseSVGRenderer(ABC):
    """
    Base class for SVG rendering with shared functionality.

    Provides common operations like drawing setup, font embedding,
    watermarks, and header/footer rendering.
    """

    def __init__(self):
        """Initialize the renderer."""
        self._drawing: drawsvg.Drawing | None = None
        self._page_height: float = 0
        self._page_width: float = 0
        self._content_bbox_svg: tuple[float, float, float, float] | None = None
        self._icon_svg_map: dict[str, str] = {}

    # =========================================================================
    # Drawing helper methods
    # =========================================================================

    def _draw_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill: str = "none",
        stroke: str = "none",
        fill_opacity: float = 1.0,
        stroke_opacity: float = 1.0,
        stroke_width: float = 1,
        rx: float = 0,
        stroke_dasharray: str | None = None,
    ):
        """
        Draw a rectangle in SVG coordinates.

        Args:
            x, y: Top-left corner in SVG coordinates (origin top-left, Y-down)
            w, h: Width and height
            fill: Fill color
            stroke: Stroke color
            fill_opacity: Fill opacity (0-1)
            stroke_opacity: Stroke opacity (0-1)
            stroke_width: Stroke width in points
            rx: Corner radius for rounded rectangles
            stroke_dasharray: SVG stroke-dasharray value (e.g. "5,3"); None disables dashing
        """
        if _is_none_color(fill) and _is_none_color(stroke):
            return
        extra = {}
        if stroke_dasharray:
            extra["stroke_dasharray"] = stroke_dasharray
        rect = drawsvg.Rectangle(
            _r(x),
            _r(y),
            _r(w),
            _r(h),
            fill=fill,
            stroke=stroke,
            fill_opacity=fill_opacity,
            stroke_opacity=stroke_opacity,
            stroke_width=_r(stroke_width),
            rx=_r(rx),
            ry=_r(rx),
            **extra,
        )
        self._drawing.append(rect)

    def _draw_text(
        self,
        x: float,
        y: float,
        text: str,
        font_name: str,
        font_size: float,
        *,
        fill: str = "black",
        fill_opacity: float = 1.0,
        anchor: str = "start",
        max_width: float | None = None,
        transform: str | None = None,
    ):
        """
        Draw text as SVG paths at a given baseline position.

        Each character is converted to glyph outlines using fonttools.
        No font embedding is needed.

        Args:
            x, y: Baseline position in SVG coordinates (origin top-left, Y-down)
            text: Text string to render
            font_name: Font family name (must be in FONT_REGISTRY)
            font_size: Font size in points
            fill: Text color
            fill_opacity: Text opacity (0-1)
            anchor: Text alignment - 'start', 'middle', or 'end'
            max_width: Optional width cap in points; if exceeded, text is
                horizontally scaled (X only) to fit.
            transform: Optional SVG transform attribute applied to the text group
        """
        if not text or _is_none_color(fill):
            return

        from config.config import get_font_path

        try:
            font_path = get_font_path(font_name)
        except KeyError:
            logger.warning("Font '%s' not in FONT_REGISTRY", font_name)
            return
        if not font_path:
            return

        combined_transform = transform
        if max_width is not None and max_width > 0:
            measured = string_width(text, font_path, font_size)
            if measured > max_width and measured > 0:
                scale_x = max_width / measured
                fit_transform = (
                    f"translate({_r(x)} {_r(y)}) scale({scale_x:.6f} 1) translate({_r(-x)} {_r(-y)})"
                )
                combined_transform = (
                    f"{transform} {fit_transform}".strip()
                    if transform
                    else fit_transform
                )
        svg_markup = text_to_svg_group(
            text,
            font_path,
            font_size,
            x,
            y,
            fill=fill,
            fill_opacity=fill_opacity,
            anchor=anchor,
        )
        if svg_markup:
            if combined_transform:
                svg_markup = f'<g transform="{combined_transform}">{svg_markup}</g>'
            self._drawing.append(drawsvg.Raw(svg_markup))

    def _draw_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        stroke: str = "black",
        stroke_width: float = 1,
        stroke_opacity: float = 1.0,
        stroke_dasharray: str | None = None,
    ):
        """
        Draw a line in SVG coordinates.

        Args:
            x1, y1, x2, y2: Endpoints in SVG coordinates (origin top-left, Y-down)
            stroke: Line color
            stroke_width: Line width in points
            stroke_opacity: Line opacity (0-1)
            stroke_dasharray: SVG stroke-dasharray value (e.g. "5,3"); None disables dashing
        """
        if _is_none_color(stroke):
            return
        extra = {}
        if stroke_dasharray:
            extra["stroke_dasharray"] = stroke_dasharray
        line = drawsvg.Line(
            _r(x1),
            _r(y1),
            _r(x2),
            _r(y2),
            stroke=stroke,
            stroke_width=_r(stroke_width),
            stroke_opacity=stroke_opacity,
            **extra,
        )
        self._drawing.append(line)

    def _draw_lines(
        self,
        line_list: list[tuple[float, float, float, float]],
        *,
        stroke: str = "black",
        stroke_width: float = 0.5,
        stroke_opacity: float = 1.0,
        stroke_dasharray: str | None = None,
    ):
        """
        Draw multiple line segments in a group in SVG coordinates.

        Args:
            line_list: List of (x1, y1, x2, y2) tuples in SVG coordinates (Y-down)
            stroke: Line color
            stroke_width: Line width in points
            stroke_opacity: Line opacity (0-1)
            stroke_dasharray: SVG stroke-dasharray value (e.g. "5,3"); None disables dashing
        """
        if not line_list or _is_none_color(stroke):
            return
        extra = {}
        if stroke_dasharray:
            extra["stroke_dasharray"] = stroke_dasharray
        group = drawsvg.Group(
            stroke=stroke,
            stroke_width=_r(stroke_width),
            stroke_opacity=stroke_opacity,
            fill="none",
            **extra,
        )
        for x1, y1, x2, y2 in line_list:
            group.append(drawsvg.Line(_r(x1), _r(y1), _r(x2), _r(y2)))
        self._drawing.append(group)

    def _draw_image(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        path: str,
        *,
        transform: str | None = None,
    ):
        """
        Draw an embedded image in SVG coordinates.

        Args:
            x, y: Top-left corner in SVG coordinates (origin top-left, Y-down)
            w, h: Width and height
            path: Path to the image file
            transform: Optional SVG transform attribute
        """
        extra = {}
        if transform:
            extra["transform"] = transform
        img = drawsvg.Image(
            _r(x),
            _r(y),
            _r(w),
            _r(h),
            path=path,
            embed=True,
            **extra,
        )
        self._drawing.append(img)

    # =========================================================================
    # Template method workflow
    # =========================================================================

    def render(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> "VisualizationResult":
        """
        Template method for SVG rendering workflow.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            events: Filtered event list
            db: Database access instance

        Returns:
            Result containing output path and statistics
        """
        from visualizers.base import VisualizationResult

        # Setup
        self._page_height = config.pageY
        self._page_width = config.pageX
        self._drawing = self._create_drawing(config)
        self._content_bbox_svg = None

        # Add metadata
        self._add_desc(config)

        if config.shrink_to_content:
            self._shrink_drawing_to_content(coordinates)

        # Render watermarks (under content)
        if config.watermark:
            self._render_text_watermark(config)
        if config.imagemark:
            self._render_image_watermark(config)

        # Render common elements (headers, footers)
        self._render_decorations(config, coordinates)

        # Render visualization-specific content
        overflow_count, overflow_entries = self._render_content(
            config, coordinates, events, db
        )

        # Save main SVG
        self._drawing.save_svg(config.outputfile)

        # Render overflow page if requested and entries exist
        page_count = 1
        if config.include_overflow and overflow_entries:
            self._render_overflow_svg(config, coordinates, overflow_entries)
            page_count = 2

        return VisualizationResult(
            output_path=config.outputfile,
            page_count=page_count,
            event_count=len(events),
            overflow_count=overflow_count,
        )

    # =========================================================================
    # Drawing creation and metadata
    # =========================================================================

    def _create_drawing(self, config: CalendarConfig) -> drawsvg.Drawing:
        """
        Create SVG drawing with page dimensions.

        Args:
            config: Calendar configuration

        Returns:
            Configured Drawing instance
        """
        drawing = drawsvg.Drawing(config.pageX, config.pageY)

        # Set title
        start_str = str(config.adjustedstart)
        end_str = str(config.adjustedend)
        title = f"{config.doc_title} for dates {start_str} to {end_str}"
        drawing.append_title(title)

        return drawing

    def _shrink_drawing_to_content(self, coordinates: CoordinateDict) -> None:
        """Adjust SVG width/height/viewBox to tightly fit the content bounding box.

        Iterates the coordinate dict (SVG space: origin top-left, Y-down) to
        find the exact extent of all rendered elements, then updates the drawing
        so the SVG displays only that region.
        """
        if not coordinates:
            return

        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")

        for x, y, w, h in coordinates.values():
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)

        if min_x == float("inf"):
            return

        self._content_bbox_svg = (min_x, min_y, max_x, max_y)
        content_w = _r(max_x - min_x)
        content_h = _r(max_y - min_y)
        # Coordinates are already SVG-native; min_y is the SVG viewBox top edge.
        self._drawing.view_box = (
            _r(min_x),
            _r(min_y),
            content_w,
            content_h,
        )
        self._drawing.width = content_w
        self._drawing.height = content_h

    def _add_desc(self, config: CalendarConfig):
        """
        Add a <desc> element with calendar metadata for provenance.

        Args:
            config: Calendar configuration
        """
        now = arrow.now()
        desc_lines = [
            f"Created: {now.format('YYYY-MM-DD HH:mm:ss')}",
            f"Author: {config.doc_author}",
            f"Date range: {config.adjustedstart} to {config.adjustedend}",
            f"Paper size: {config.papersize} ({config.orientation})",
            f"Page dimensions: {config.pageX} x {config.pageY} pts",
        ]
        if config.command_line:
            desc_lines.append(f"Command: {config.command_line}")

        desc_text = "\n".join(desc_lines)
        desc_elem = drawsvg.Raw(f"<desc>{desc_text}</desc>")
        self._drawing.append(desc_elem)

    # =========================================================================
    # Watermarks
    # =========================================================================

    def _watermark_bounds(
        self, config: CalendarConfig
    ) -> tuple[float, float, float, float]:
        """Return (left, top, width, height) in SVG coordinates for watermark layout."""
        if config.shrink_to_content and self._content_bbox_svg is not None:
            min_x, min_y, max_x, max_y = self._content_bbox_svg
            return min_x, min_y, max_x - min_x, max_y - min_y
        return 0.0, 0.0, config.pageX, config.pageY

    def _render_text_watermark(self, config: CalendarConfig):
        """
        Render text watermark centered on page.

        Args:
            config: Calendar configuration with watermark settings
        """
        if not config.watermark:
            return

        from config.config import get_font_path

        font_path = get_font_path(config.watermark_font)

        from renderers.glyph_cache import get_font_metrics

        resize_mode = (
            str(getattr(config, "watermark_resize_mode", "fit") or "fit")
            .strip()
            .lower()
        )

        # Use paper-size-scaled setfontsizes value unless explicitly overridden.
        base_size = float(config.watermark_size or 256)
        base_size = max(1.0, base_size)
        left, top, span_w, span_h = self._watermark_bounds(config)
        waterX = left + (span_w / 2)
        center_y = top + (span_h / 2)
        center_x_svg = waterX
        center_y_svg = center_y

        transform_parts: list[str] = []

        if resize_mode == "stretch":
            text_width = string_width(config.watermark, font_path, base_size)
            upm, ascender, descender = get_font_metrics(font_path)
            text_height = max(1.0, (ascender - descender) * (base_size / upm))
            if text_width <= 0:
                return

            # Keep a tiny safety margin to avoid clipping on edge glyph extrema.
            max_w = span_w * 0.98
            max_h = span_h * 0.98
            stretch_x = max_w / text_width
            stretch_y = max_h / text_height

            # Center baseline so the unscaled text box is centered, then scale
            # around the page center.
            asc_pt = ascender * (base_size / upm)
            desc_pt = descender * (base_size / upm)
            waterY = center_y - ((asc_pt + desc_pt) / 2.0)
            transform_parts.append(
                f"translate({center_x_svg} {center_y_svg}) "
                f"scale({stretch_x:.6f} {stretch_y:.6f}) "
                f"translate({-center_x_svg} {-center_y_svg})"
            )
            font_size = base_size
        else:
            # fit mode: keep glyph proportions and fit width using base_size as
            # the ceiling (paper-size aware via setfontsizes/config).
            font_size = shrinktext(
                config.watermark,
                span_w * 0.98,
                font_path,
                base_size,
            )
            waterY = center_y - (font_size / 3)

        angle = float(getattr(config, "watermark_rotation_angle", 0.0) or 0.0)
        if angle:
            transform_parts.insert(0, f"rotate({angle} {center_x_svg} {center_y_svg})")
        transform = " ".join(transform_parts) or None

        self._draw_text(
            waterX,
            waterY,
            config.watermark,
            config.watermark_font,
            font_size,
            fill=config.watermark_color,
            fill_opacity=config.watermark_alpha,
            anchor="middle",
            transform=transform,
        )

    def _is_svg(self, filepath: str) -> bool:
        """Check if file is an SVG by extension."""
        return os.path.splitext(filepath)[1].lower() == ".svg"

    def _render_image_watermark(self, config: CalendarConfig):
        """
        Render image watermark centered on page.

        Supports raster images (PNG, JPEG, etc.) and SVG files.

        Args:
            config: Calendar configuration with imagemark settings
        """
        if not config.imagemark:
            return

        # Calculate center position in SVG coordinates
        left, top, span_w, span_h = self._watermark_bounds(config)
        waterX = left + (span_w / 2) - (config.imagemark_width / 2)
        waterY = top + (span_h / 2) - (config.imagemark_height / 2)
        angle = float(getattr(config, "imagemark_rotation_angle", 0.0) or 0.0)
        center_x = waterX + (config.imagemark_width / 2)
        center_y_svg = waterY + (config.imagemark_height / 2)
        transform = f"rotate({angle} {center_x} {center_y_svg})" if angle else None

        if self._is_svg(config.imagemark):
            self._draw_svg_watermark(
                config.imagemark,
                waterX,
                waterY,
                config.imagemark_width,
                config.imagemark_height,
                transform=transform,
            )
        else:
            self._draw_image(
                waterX,
                waterY,
                config.imagemark_width,
                config.imagemark_height,
                config.imagemark,
                transform=transform,
            )

    def _draw_svg_watermark(
        self,
        svg_path: str,
        x: float,
        y: float,
        target_width: float,
        target_height: float,
        *,
        transform: str | None = None,
    ):
        """
        Read an SVG file and embed it as a nested SVG element.

        Args:
            svg_path: Path to the SVG file
            x: X coordinate in SVG space (top-left corner)
            y: Y coordinate in SVG space (top-left corner)
            target_width: Target width in points
            target_height: Target height in points
            transform: Optional SVG transform attribute
        """
        path = Path(svg_path)
        if not path.exists():
            logger.warning("SVG watermark file not found: %s", svg_path)
            return

        svg_content = path.read_text(encoding="utf-8")

        # Wrap in a positioned SVG element
        nested_svg = (
            f'<svg x="{_r(x)}" y="{_r(y)}" width="{_r(target_width)}" '
            f'height="{_r(target_height)}" '
            f'preserveAspectRatio="xMidYMid meet">'
            f"{svg_content}</svg>"
        )
        if transform:
            nested_svg = f'<g transform="{transform}">{nested_svg}</g>'
        nested = drawsvg.Raw(nested_svg)
        self._drawing.append(nested)

    def _load_icon_svg_cache(self, db: "CalendarDB") -> None:
        """Load icon SVG lookup from database (best-effort)."""
        try:
            self._icon_svg_map = db.get_icon_svg_map()
        except Exception:
            self._icon_svg_map = {}

    def _resolve_icon_svg(self, icon_name: str | None) -> str | None:
        """Resolve icon name to SVG markup from preloaded cache."""
        if not icon_name:
            return None
        key = str(icon_name).strip().lower()
        if not key:
            return None
        return self._icon_svg_map.get(key)

    @staticmethod
    def _strip_svg_wrapper(svg_markup: str) -> str:
        """Return inner SVG content without XML/DOCTYPE/<svg> wrapper."""
        inner = re.sub(r"<\?xml[^>]*\?>", "", svg_markup, flags=re.IGNORECASE)
        inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner, flags=re.IGNORECASE)
        inner = re.sub(r"<svg[^>]*>", "", inner, count=1, flags=re.IGNORECASE)
        if "</svg>" in inner:
            inner = inner.rsplit("</svg>", 1)[0]
        return inner.strip()

    def _draw_icon_svg(
        self,
        icon_name: str | None,
        x: float,
        baseline_y: float,
        size: float,
        *,
        anchor: str = "start",
        color: str | None = None,
        fallback_name: str | None = None,
        fallback_color: str | None = None,
        transform: str | None = None,
    ) -> bool:
        """
        Draw an icon from the DB icon cache at text-like baseline coordinates.

        If icon_name is specified but not found in the cache and fallback_name is
        provided, the fallback icon is drawn with fallback_color instead.

        Returns:
            True if an icon was drawn, else False.
        """
        svg_markup = self._resolve_icon_svg(icon_name)
        if (
            svg_markup is None
            and icon_name
            and str(icon_name).strip()
            and fallback_name
        ):
            svg_markup = self._resolve_icon_svg(fallback_name)
            color = fallback_color
        if not svg_markup or size <= 0 or self._drawing is None:
            return False

        draw_x = x
        if anchor == "middle":
            draw_x -= size / 2
        elif anchor == "end":
            draw_x -= size

        # Align icon with adjacent text that shares the same baseline_y.
        # A typical font's ascender reaches ~0.80 * size above the baseline, so
        # the icon top is placed there and its bottom lands near the descender
        # (~0.20 * size below baseline).  This keeps icon and text caps visually
        # centered on the same axis.
        draw_y = baseline_y - (size * 0.80)

        # Extract the icon's original viewBox before stripping the wrapper so
        # the nested <svg> preserves the icon's own coordinate space.  width
        # and height are always set to `size` (the caller's display size), and
        # the SVG renderer scales the viewBox content to fit — correctly
        # handling icons whose coordinate system is 48×48 or any other value.
        vb_match = re.search(
            r'viewBox=["\'][\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)["\']',
            svg_markup,
            re.IGNORECASE,
        )
        viewbox = (
            f"0 0 {vb_match.group(1)} {vb_match.group(2)}" if vb_match else "0 0 24 24"
        )

        inner = self._strip_svg_wrapper(svg_markup)

        style_attr = (
            f' style="color:{color};stroke:{color};fill:{color};"' if color else ""
        )
        nested_svg = (
            f'<svg x="{_r(draw_x)}" y="{_r(draw_y)}" width="{_r(size)}" height="{_r(size)}" '
            f'viewBox="{viewbox}" preserveAspectRatio="xMidYMid meet"{style_attr}>'
            f"{inner}</svg>"
        )
        if transform:
            nested_svg = f'<g transform="{transform}">{nested_svg}</g>'
        self._drawing.append(drawsvg.Raw(nested_svg))
        return True

    def _draw_icon_band_row(
        self,
        day_cells: "list[tuple[float, float, list[tuple[str, str]]]]",
        row_y: float,
        row_h: float,
        icon_h: float,
        fill_color: str = "none",
    ) -> None:
        """
        Render one icon-band row.

        Parameters
        ----------
        day_cells:
            Sequence of ``(cell_x, cell_w, [(icon_name, color), ...])`` — one
            entry per visible day.  Days with no icons have an empty icon list.
        row_y:
            Top Y coordinate of the band row.
        row_h:
            Height of the band row in points.
        icon_h:
            Display height of each icon in points.
        fill_color:
            Background fill for every day cell (``"none"`` = transparent).
        """
        # Vertical centring formula (mirrors milestone / continuation icons):
        #   icon top     = baseline_y - 0.8 * icon_h
        #   icon centre  = baseline_y - 0.3 * icon_h  =  row_y + row_h * 0.5
        #   → baseline_y = row_y + row_h * 0.5 + 0.3 * icon_h
        icon_baseline_y = row_y + row_h * 0.5 + icon_h * 0.3
        draw_fill = str(fill_color or "none").strip().lower()
        has_fill = draw_fill not in ("none", "transparent", "")

        for cell_x, cell_w, icons in day_cells:
            if has_fill and cell_w > 0:
                self._draw_rect(cell_x, row_y, cell_w, row_h, fill=draw_fill)
            n = len(icons)
            if n == 0:
                continue
            # Evenly divide the cell width into n slots; centre each icon in its slot.
            slot_w = cell_w / n
            for i, (icon_name, color) in enumerate(icons):
                icon_x = cell_x + slot_w * (i + 0.5)
                self._draw_icon_svg(
                    icon_name, icon_x, icon_baseline_y, icon_h,
                    anchor="middle", color=color,
                )

    # =========================================================================
    # Decorations (headers, footers, day labels)
    # =========================================================================

    # Mapping: coordinate key -> (x_offset_fn, anchor, config_prefix)
    # x_offset_fn(X, width) -> text x position
    _HEADER_FOOTER_SLOTS: tuple[tuple, ...] = (
        ("HeaderLeft", lambda X, W: X, "start", "header_left"),
        ("HeaderCenter", lambda X, W: X + W / 2, "middle", "header_center"),
        ("HeaderRight", lambda X, W: X + W, "end", "header_right"),
        ("FooterLeft", lambda X, W: X, "start", "footer_left"),
        ("FooterCenter", lambda X, W: X + W / 2, "middle", "footer_center"),
        ("FooterRight", lambda X, W: X + W, "end", "footer_right"),
    )
    _HEADER_FOOTER_MAP: dict = {slot[0]: slot for slot in _HEADER_FOOTER_SLOTS}

    _DAY_NAME_KEYS: frozenset = frozenset(
        {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"}
    )

    def _render_decorations(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
    ):
        """
        Render headers, footers, and day labels.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
        """
        for key in sorted(coordinates):
            X, Y, width, height = coordinates[key]

            if key in self._HEADER_FOOTER_MAP:
                _, x_fn, anchor, prefix = self._HEADER_FOOTER_MAP[key]
                self._draw_text(
                    x_fn(X, width),
                    Y + (height * 0.8),
                    getattr(config, f"{prefix}_text"),
                    getattr(config, f"{prefix}_font"),
                    getattr(config, f"{prefix}_font_size"),
                    fill=getattr(config, f"{prefix}_font_color"),
                    anchor=anchor,
                )

            elif key in self._DAY_NAME_KEYS:
                self._draw_text(
                    X + width / 2,
                    Y + (height * 0.7),
                    key,
                    config.day_name_font,
                    config.day_name_font_size,
                    fill=config.day_name_font_color,
                    anchor="middle",
                    max_width=width,
                )

    # =========================================================================
    # Overflow page (separate SVG)
    # =========================================================================

    def _overflow_content_area(
        self,
        config: CalendarConfig,
    ) -> tuple[float, float, float, float, float]:
        """
        Compute overflow page content area bounds.

        Returns:
            Tuple of (content_left, content_right, content_width, content_top, content_bottom)
        """
        from config.config import resolve_page_margins

        margins = resolve_page_margins(config)
        header_height = (
            round(config.pageY * config.header_percent, 2)
            if config.include_header
            else 0.0
        )
        footer_height = (
            round(config.pageY * config.footer_percent, 2)
            if config.include_footer
            else 0.0
        )
        content_left = margins["left"]
        content_right = config.pageX - margins["right"]
        content_width = content_right - content_left
        content_top = margins["top"] + header_height
        content_bottom = config.pageY - margins["bottom"] - footer_height
        return content_left, content_right, content_width, content_top, content_bottom

    def _draw_overflow_table_header(
        self,
        config: CalendarConfig,
        content_left: float,
        content_right: float,
        content_width: float,
        col1_x: float,
        col2_x: float,
        col3_x: float,
        table_top: float,
        row_height: float,
        table_font: str,
        table_font_size: float,
    ) -> float:
        """
        Draw the overflow table header row and separator line.

        Returns:
            sep_y: Y coordinate of the separator (first data row starts here)
        """
        header_y = table_top
        text_baseline = header_y + row_height - 5

        self._draw_rect(
            content_left,
            header_y,
            content_width,
            row_height,
            fill="lightgrey",
            fill_opacity=0.4,
        )
        self._draw_text(
            col1_x + 4,
            text_baseline,
            "Start Date",
            table_font,
            table_font_size,
            fill=config.day_box_font_color,
        )
        self._draw_text(
            col2_x + 4,
            text_baseline,
            "End Date",
            table_font,
            table_font_size,
            fill=config.day_box_font_color,
        )
        self._draw_text(
            col3_x + 4,
            text_baseline,
            "Event Name",
            table_font,
            table_font_size,
            fill=config.day_box_font_color,
        )

        sep_y = header_y + row_height
        self._draw_line(
            content_left,
            sep_y,
            content_right,
            sep_y,
            stroke="grey",
            stroke_opacity=0.5,
        )
        return sep_y

    def _draw_overflow_table_rows(
        self,
        config: CalendarConfig,
        overflow_entries: list,
        content_left: float,
        content_right: float,
        content_width: float,
        content_bottom: float,
        col1_x: float,
        col2_x: float,
        col3_x: float,
        col3_width: float,
        sep_y: float,
        row_height: float,
        table_font: str,
        table_font_size: float,
        font_path: str,
    ) -> None:
        """Draw all data rows in the overflow table."""
        from config.config import monthcolors

        current_y = sep_y
        for idx, entry in enumerate(overflow_entries):
            row_bottom = current_y + row_height

            if row_bottom > content_bottom:
                break

            if idx % 2 == 1:
                month_key = entry.start[4:6] if len(entry.start) >= 6 else "01"
                theme_monthcolors = getattr(config, "theme_monthcolors", None)
                row_color = (theme_monthcolors or monthcolors).get(
                    month_key, "lightgrey"
                )
                self._draw_rect(
                    content_left,
                    current_y,
                    content_width,
                    row_height,
                    fill=row_color,
                    fill_opacity=0.15,
                )

            text_baseline = row_bottom - 5
            self._draw_text(
                col1_x + 4,
                text_baseline,
                self._format_date(entry.start),
                table_font,
                table_font_size,
                fill=config.day_box_font_color,
            )
            self._draw_text(
                col2_x + 4,
                text_baseline,
                self._format_date(entry.end),
                table_font,
                table_font_size,
                fill=config.day_box_font_color,
            )
            self._draw_text(
                col3_x + 4,
                text_baseline,
                entry.task_name or "",
                table_font,
                table_font_size,
                fill=config.day_box_font_color,
                max_width=col3_width - 8,
            )
            current_y = row_bottom

    def _render_overflow_svg(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        overflow_entries: list,
    ):
        """
        Render a table of overflow entries as a separate SVG file.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            overflow_entries: List of OverflowEntry objects
        """
        from config.config import get_font_path

        saved_drawing = self._drawing
        self._drawing = self._create_drawing(config)
        self._content_bbox_svg = None
        if config.shrink_to_content:
            self._shrink_drawing_to_content(coordinates)
        if config.watermark:
            self._render_text_watermark(config)
        if config.imagemark:
            self._render_image_watermark(config)
        self._render_decorations(config, coordinates)

        content_left, content_right, content_width, content_top, content_bottom = (
            self._overflow_content_area(config)
        )

        # Title
        title_font = config.header_center_font
        title_font_size = config.header_center_font_size
        title_y = content_top + title_font_size + 10
        self._draw_text(
            content_left + content_width / 2,
            title_y,
            "Overflow Events",
            title_font,
            title_font_size,
            fill=config.day_box_font_color,
            anchor="middle",
        )

        # Table layout
        table_font = config.event_text_font
        table_font_size = config.event_text_font_size + 1
        row_height = table_font_size + 6
        table_top = title_y + title_font_size + 5

        col1_width = content_width * 0.15
        col2_width = content_width * 0.15
        col3_width = content_width * 0.70
        col1_x = content_left
        col2_x = content_left + col1_width
        col3_x = content_left + col1_width + col2_width

        sep_y = self._draw_overflow_table_header(
            config,
            content_left,
            content_right,
            content_width,
            col1_x,
            col2_x,
            col3_x,
            table_top,
            row_height,
            table_font,
            table_font_size,
        )

        font_path = get_font_path(table_font)
        self._draw_overflow_table_rows(
            config,
            overflow_entries,
            content_left,
            content_right,
            content_width,
            content_bottom,
            col1_x,
            col2_x,
            col3_x,
            col3_width,
            sep_y,
            row_height,
            table_font,
            table_font_size,
            font_path,
        )

        overflow_path = config.outputfile.replace(".svg", "_overflow.svg")
        self._drawing.save_svg(overflow_path)
        logger.info("Overflow page saved to: %s", overflow_path)

        self._drawing = saved_drawing

    @staticmethod
    def _format_date(date_str: str) -> str:
        """
        Format a YYYYMMDD date string as YYYY-MM-DD.

        Args:
            date_str: Date in YYYYMMDD format

        Returns:
            Date in YYYY-MM-DD format
        """
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str

    # =========================================================================
    # Abstract method for subclasses
    # =========================================================================

    @abstractmethod
    def _render_content(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list]:
        """
        Render visualization-specific content.

        Args:
            config: Calendar configuration
            coordinates: Layout coordinates
            events: Event list
            db: Database access instance

        Returns:
            Tuple of (overflow_count, list of OverflowEntry objects)
        """
        pass
