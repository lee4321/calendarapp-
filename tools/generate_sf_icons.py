#!/usr/bin/env python3
"""Generate individual SVG icons from SF-Compact glyph IDs.

Reads a CSV file (name, glyph_id) and produces one SVG per row using
the same glyph extraction technique as generate_capsule_numbers.py.

Usage:
    uv run python tools/generate_sf_icons.py
    uv run python tools/generate_sf_icons.py --font-path /Library/Fonts/SF-Compact.ttf
    uv run python tools/generate_sf_icons.py --output-dir /tmp/sficons
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

DEFAULT_FONT = "/Library/Fonts/SF-Compact.ttf"
DEFAULT_INPUT = "icon glyphs.txt"
DEFAULT_OUTPUT = "sficons"
FONT_SIZE = 24  # px height target


def extract_glyph_svg(font: TTFont, gid: int, upm: int, font_size: float = FONT_SIZE) -> str:
    """Extract a single glyph by GID and return a complete SVG string."""
    glyph_order = font.getGlyphOrder()
    if gid < 0 or gid >= len(glyph_order):
        raise ValueError(f"GID {gid} out of range (font has {len(glyph_order)} glyphs)")

    glyph_name = glyph_order[gid]
    gs = font.getGlyphSet()

    # Extract SVG path
    pen = SVGPathPen(gs)
    gs[glyph_name].draw(pen)
    path_d = pen.getCommands()

    # Bounding box
    bp = BoundsPen(gs)
    gs[glyph_name].draw(bp)
    bounds = bp.bounds  # (xMin, yMin, xMax, yMax) or None

    if not path_d or not bounds:
        return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 0 0"/>\n'

    scale = font_size / upm
    xmin, ymin, xmax, ymax = bounds

    # Convert to SVG coordinates (Y-flip)
    svg_xmin = xmin * scale
    svg_xmax = xmax * scale
    svg_ymin = -ymax * scale
    svg_ymax = -ymin * scale

    vb_w = svg_xmax - svg_xmin
    vb_h = svg_ymax - svg_ymin

    # Scale to fit FONT_SIZE height
    fit_scale = font_size / vb_h if vb_h > 0 else 1.0
    final_w = vb_w * fit_scale
    final_h = font_size

    # Transform: shift content to viewBox origin, then scale with Y-flip
    tx = -svg_xmin
    ty = -svg_ymin

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vb_w:.4f} {vb_h:.4f}" '
        f'width="{final_w:.4f}" height="{final_h:.4f}">\n'
        f'  <g fill="black" stroke="black" stroke-width="0.25">\n'
        f'    <path d="{path_d}" '
        f'transform="translate({tx:.4f},{ty:.4f}) scale({scale:.6f},{-scale:.6f})"/>\n'
        f'  </g>\n'
        f'</svg>\n'
    )


def generate_icons(font_path: str, input_file: str, output_dir: str) -> None:
    """Read the CSV and generate one SVG per row."""
    font = TTFont(font_path)
    upm = font["head"].unitsPerEm

    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header row
        count = 0
        errors = 0
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            try:
                gid = int(row[1].strip())
            except ValueError:
                print(f"  Skipping '{name}': invalid glyph ID '{row[1].strip()}'", file=sys.stderr)
                errors += 1
                continue

            try:
                svg = extract_glyph_svg(font, gid, upm)
            except ValueError as e:
                print(f"  Skipping '{name}': {e}", file=sys.stderr)
                errors += 1
                continue

            filepath = os.path.join(output_dir, f"{name}.svg")
            with open(filepath, "w", encoding="utf-8") as out:
                out.write(svg)

            count += 1
            if count % 50 == 0:
                print(f"  [{count}] {name}.svg")

    print(f"Done. Generated {count} SVG icons in {output_dir}/")
    if errors:
        print(f"  ({errors} skipped due to errors)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SVG icons from SF-Compact font glyph IDs."
    )
    parser.add_argument(
        "--font-path",
        default=DEFAULT_FONT,
        help=f"Path to the TTF/OTF font (default: {DEFAULT_FONT})",
    )
    parser.add_argument(
        "--input-file",
        default=DEFAULT_INPUT,
        help=f"CSV input file (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.font_path):
        print(f"Error: Font not found: {args.font_path}", file=sys.stderr)
        raise SystemExit(1)

    if not os.path.isfile(args.input_file):
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Font: {args.font_path}")
    print(f"Input: {args.input_file}")
    print(f"Output: {args.output_dir}/")
    print(f"Font size: {FONT_SIZE}px")
    print()

    generate_icons(args.font_path, args.input_file, args.output_dir)


if __name__ == "__main__":
    main()
