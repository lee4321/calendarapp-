#!/usr/bin/env python3
"""Generate capsule number SVG icons (circle and square variants).

Creates 20,000 SVG files (10,000 circle + 10,000 square) in the output
directory, each composed of 4 font glyphs accessed by glyph ID from
SF-Mono-Light.otf.

Usage:
    uv run python tools/generate_capsule_numbers.py
    uv run python tools/generate_capsule_numbers.py --shape circle
    uv run python tools/generate_capsule_numbers.py --output-dir /tmp/icons
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

# ---------------------------------------------------------------------------
# Glyph ID mappings: digit (0-9) → font glyph index
# ---------------------------------------------------------------------------

MID_GIDS = [1523, 1524, 1525, 1526, 1527, 1528, 1529, 1530, 1531, 1532]
CLEFT_GIDS = [1513, 1514, 1515, 1516, 1517, 1518, 1519, 1520, 1521, 1522]
CRIGHT_GIDS = [1533, 1534, 1535, 1536, 1537, 1538, 1539, 1540, 1541, 1542]
SLEFT_GIDS = [1557, 1558, 1559, 1560, 1561, 1562, 1563, 1564, 1565, 1566]
SRIGHT_GIDS = [1567, 1568, 1569, 1570, 1571, 1572, 1573, 1574, 1575, 1576]

DEFAULT_FONT = "fonts/SF-Mono-Light.otf"
DEFAULT_OUTPUT = "capsule_numbers"
FONT_SIZE = 24  # px height target


# ---------------------------------------------------------------------------
# Glyph extraction helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GlyphData:
    """Pre-extracted glyph: SVG path + advance/bounds in font units."""
    path_d: str
    advance_width: int  # in font units
    # Bounding box in font units (Y-up): (xMin, yMin, xMax, yMax)
    bounds: tuple[float, float, float, float] | None


def extract_glyph_by_gid(font: TTFont, gid: int) -> GlyphData:
    """Extract SVG path data and advance width for a glyph by its GID."""
    glyph_order = font.getGlyphOrder()
    if gid < 0 or gid >= len(glyph_order):
        raise ValueError(f"GID {gid} out of range (font has {len(glyph_order)} glyphs)")

    glyph_name = glyph_order[gid]
    gs = font.getGlyphSet()
    pen = SVGPathPen(gs)
    gs[glyph_name].draw(pen)
    path_d = pen.getCommands()

    # Bounding box via BoundsPen
    bp = BoundsPen(gs)
    gs[glyph_name].draw(bp)
    bounds = bp.bounds  # (xMin, yMin, xMax, yMax) or None if empty

    # Advance width from hmtx table
    advance_width = font["hmtx"][glyph_name][0]

    return GlyphData(path_d=path_d, advance_width=advance_width, bounds=bounds)


def preload_glyphs(font: TTFont, gid_lists: list[list[int]]) -> dict[int, GlyphData]:
    """Pre-extract all needed glyphs into a dict keyed by GID."""
    cache: dict[int, GlyphData] = {}
    for gid_list in gid_lists:
        for gid in gid_list:
            if gid not in cache:
                cache[gid] = extract_glyph_by_gid(font, gid)
    return cache


# ---------------------------------------------------------------------------
# SVG composition
# ---------------------------------------------------------------------------

def compose_svg(
    glyphs: list[GlyphData],
    upm: int,
    font_size: float = FONT_SIZE,
) -> str:
    """Compose multiple glyphs into a single SVG icon string with tight bounding box.

    Args:
        glyphs: Ordered list of GlyphData for the 4 positions.
        upm: Font units-per-em.
        font_size: Target height in px.

    Returns:
        Complete SVG markup string.
    """
    scale = font_size / upm

    # Compute horizontal positions in font units (advance-based)
    positions_fu: list[float] = []
    cursor_fu = 0.0
    for g in glyphs:
        positions_fu.append(cursor_fu)
        cursor_fu += g.advance_width

    # Compute tight bounding box in font units across all positioned glyphs
    # Font coordinates: Y-up (yMin=bottom, yMax=top)
    bb_xmin = float("inf")
    bb_ymin = float("inf")
    bb_xmax = float("-inf")
    bb_ymax = float("-inf")
    for g, x_off in zip(glyphs, positions_fu):
        if g.bounds:
            gx_min, gy_min, gx_max, gy_max = g.bounds
            bb_xmin = min(bb_xmin, gx_min + x_off)
            bb_ymin = min(bb_ymin, gy_min)
            bb_xmax = max(bb_xmax, gx_max + x_off)
            bb_ymax = max(bb_ymax, gy_max)

    if bb_xmin == float("inf"):
        # No visible glyphs
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 0"/>\n'

    # Convert bounding box to SVG coordinates (Y-flip: svg_y = -font_y)
    # In the transform, each glyph is placed at translate(tx, 0) scale(s, -s)
    # which maps font (fx, fy) → (tx + fx*s, -fy*s)
    # So the overall SVG bbox is:
    svg_xmin = bb_xmin * scale
    svg_xmax = bb_xmax * scale
    svg_ymin = -bb_ymax * scale  # font top → SVG top (smallest Y)
    svg_ymax = -bb_ymin * scale  # font bottom → SVG bottom (largest Y)

    vb_w = svg_xmax - svg_xmin
    vb_h = svg_ymax - svg_ymin

    # Scale so the icon is exactly FONT_SIZE px tall
    fit_scale = font_size / vb_h if vb_h > 0 else 1.0
    final_w = vb_w * fit_scale
    final_h = font_size

    # Build path elements — translate so content starts at viewBox origin
    # Each glyph transform: translate to its advance position, then scale with Y-flip
    # We shift by -svg_xmin, -svg_ymin to move content to (0,0)
    paths: list[str] = []
    for g, x_fu in zip(glyphs, positions_fu):
        if g.path_d:
            # Glyph in SVG space before cropping: translate(x_fu*scale, 0) scale(s,-s)
            # After cropping offset: subtract svg_xmin from X, svg_ymin from Y
            tx = x_fu * scale - svg_xmin
            ty = -svg_ymin  # baseline offset so content starts at top of viewBox
            paths.append(
                f'<path d="{g.path_d}" '
                f'transform="translate({tx:.4f},{ty:.4f}) scale({scale:.6f},{-scale:.6f})"/>'
            )

    inner = "\n    ".join(paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vb_w:.4f} {vb_h:.4f}" '
        f'width="{final_w:.4f}" height="{final_h:.4f}">\n'
        f'  <g fill="black" stroke="black" stroke-width="0.5">\n'
        f'    {inner}\n'
        f'  </g>\n'
        f'</svg>\n'
    )


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

def generate_icons(
    font_path: str,
    output_dir: str,
    shape: str = "both",
) -> None:
    """Generate all capsule number SVG icons.

    Args:
        font_path: Path to the OTF/TTF font file.
        output_dir: Directory to write SVG files into.
        shape: 'circle', 'square', or 'both'.
    """
    font = TTFont(font_path)
    upm = font["head"].unitsPerEm

    # Pre-extract all glyphs
    all_gid_lists = [MID_GIDS, CLEFT_GIDS, CRIGHT_GIDS, SLEFT_GIDS, SRIGHT_GIDS]
    glyph_cache = preload_glyphs(font, all_gid_lists)

    os.makedirs(output_dir, exist_ok=True)

    shapes_to_generate: list[tuple[str, list[int], list[int]]] = []
    if shape in ("circle", "both"):
        shapes_to_generate.append(("circle", CLEFT_GIDS, CRIGHT_GIDS))
    if shape in ("square", "both"):
        shapes_to_generate.append(("square", SLEFT_GIDS, SRIGHT_GIDS))

    # 2-digit (00-99) + 3-digit (000-999) + 4-digit (0000-9999) per shape
    total = len(shapes_to_generate) * (100 + 1_000 + 10_000)
    count = 0

    for prefix, left_gids, right_gids in shapes_to_generate:
        # 2-digit icons: [left_A, right_B]
        for num in range(100):
            d0 = num // 10
            d1 = num % 10

            glyphs = [
                glyph_cache[left_gids[d0]],
                glyph_cache[right_gids[d1]],
            ]

            svg = compose_svg(glyphs, upm)
            filename = f"{prefix}{num:02d}.svg"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg)

            count += 1
            if count % 100 == 0:
                print(f"  [{count}/{total}] {filename}")

        # 3-digit icons: [left_A, mid_B, right_C]
        for num in range(1_000):
            d0 = num // 100
            d1 = (num // 10) % 10
            d2 = num % 10

            glyphs = [
                glyph_cache[left_gids[d0]],
                glyph_cache[MID_GIDS[d1]],
                glyph_cache[right_gids[d2]],
            ]

            svg = compose_svg(glyphs, upm)
            filename = f"{prefix}{num:03d}.svg"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg)

            count += 1
            if count % 1000 == 0:
                print(f"  [{count}/{total}] {filename}")

        # 4-digit icons: [left_A, mid_B, mid_C, right_D]
        for num in range(10_000):
            d0 = num // 1000
            d1 = (num // 100) % 10
            d2 = (num // 10) % 10
            d3 = num % 10

            glyphs = [
                glyph_cache[left_gids[d0]],
                glyph_cache[MID_GIDS[d1]],
                glyph_cache[MID_GIDS[d2]],
                glyph_cache[right_gids[d3]],
            ]

            svg = compose_svg(glyphs, upm)
            filename = f"{prefix}{num:04d}.svg"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg)

            count += 1
            if count % 1000 == 0:
                print(f"  [{count}/{total}] {filename}")

    print(f"Done. Generated {count} SVG icons in {output_dir}/")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate capsule number SVG icons from font glyphs."
    )
    parser.add_argument(
        "--font-path",
        default=DEFAULT_FONT,
        help=f"Path to the OTF/TTF font (default: {DEFAULT_FONT})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--shape",
        choices=["circle", "square", "both"],
        default="both",
        help="Which icon shape to generate (default: both)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.font_path):
        print(f"Error: Font not found: {args.font_path}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Font: {args.font_path}")
    print(f"Output: {args.output_dir}/")
    print(f"Shape: {args.shape}")
    print(f"Font size: {FONT_SIZE}px")
    print()

    generate_icons(args.font_path, args.output_dir, args.shape)


if __name__ == "__main__":
    main()
