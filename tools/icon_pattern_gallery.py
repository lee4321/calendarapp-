"""Generate a gallery of pattern swatches from calendar.db, one section per source.

* ``icons/``    -- the ``icon`` table: each icon becomes a padded tile, normalized to
  one size, with alternating rows staggered by half a tile.
* ``patterns/`` -- the ``patterns`` table: tiles exactly as a render draws them
  (auto-normalized to the pattern target size, no padding or stagger).

Each source is paged (``page_001.svg`` ...) into its own folder; ``index.html``
links every page, grouped by source.

Usage: uv run python tools/icon_pattern_gallery.py [output_dir] [--match TEXT]
       [--source icons|patterns|all] [--limit N] [--per-page N] [--color HEX] [--pad PT] [--icon-size PT] [--opacity 0-1]
       [--scale X] [--no-stagger] [--stagger-patterns]
"""

from __future__ import annotations

import argparse
import html
import re
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from renderers.svg_patterns import (  # noqa: E402
    parse_svg_tile_size,
    pattern_def_id,
    pattern_def_xml,
    pattern_is_recolorable,
)

DEFAULT_OUT = ROOT / "output" / "icon_pattern_gallery"
SWATCH_W, SWATCH_H = 140.0, 100.0
GAP, MARGIN, LABEL_H, TITLE_H = 10.0, 20.0, 14.0, 30.0
COLUMNS = 6


def is_flattened(svg: str) -> bool:
    """True when colorizing collapses more than one ink color (or uses <style>)."""
    cols = {v.lower() for v in re.findall(r'(?:fill|stroke)="([^"]*)"', svg)}
    cols -= {"none", "currentcolor", "inherit", "transparent"}
    return len(cols) > 1 or bool(re.search(r"<style\b|<image\b|data:image/", svg))


@dataclass(frozen=True)
class Source:
    """One table of SVG tiles and how its swatches are built."""

    key: str  # output subfolder
    label: str
    table: str
    tile_def: Callable[[str, str, argparse.Namespace], str]  # (pat_id, svg, args) -> <pattern> xml
    note: Callable[[str], str]  # svg -> label suffix


def _icon_tile(pat_id: str, svg: str, args: argparse.Namespace) -> str:
    # Normalize: draw the icon's largest side at icon_size, with pad (in output pt) around it.
    factor = args.icon_size / max(parse_svg_tile_size(svg))
    return pattern_def_xml(
        pat_id,
        svg,
        args.color,
        target_size=0,
        extra_scale=factor * args.scale,
        pad=args.pad / factor,
        stagger=not args.no_stagger,
    )


def _pattern_tile(pat_id: str, svg: str, args: argparse.Namespace) -> str:
    return pattern_def_xml(pat_id, svg, args.color, extra_scale=args.scale, stagger=args.stagger_patterns)


SOURCES = {
    "icons": Source("icons", "Icons", "icon", _icon_tile, lambda s: " (flattened)" if is_flattened(s) else ""),
    "patterns": Source(
        "patterns", "Patterns", "patterns", _pattern_tile, lambda s: "" if pattern_is_recolorable(s) else " (fixed)"
    ),
}


def load_tiles(db_path: Path, table: str, match: str | None) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(f"SELECT name, svg FROM {table} WHERE svg IS NOT NULL ORDER BY name").fetchall()
    finally:
        conn.close()
    needle = match.lower() if match else None
    return [(n, s) for n, s in rows if n and (needle is None or needle in n.lower())]


def build_page(src: Source, tiles, title: str, args: argparse.Namespace) -> str:
    rows = -(-len(tiles) // COLUMNS)
    cell_h = SWATCH_H + LABEL_H + GAP
    width = 2 * MARGIN + COLUMNS * SWATCH_W + (COLUMNS - 1) * GAP
    height = 2 * MARGIN + TITLE_H + rows * cell_h
    defs: list[str] = []
    body: list[str] = []
    for i, (name, svg) in enumerate(tiles):
        pat_id = pattern_def_id(f"{src.key}-{name}", args.color)
        defs.append(src.tile_def(pat_id, svg, args))
        x = MARGIN + (i % COLUMNS) * (SWATCH_W + GAP)
        y = MARGIN + TITLE_H + (i // COLUMNS) * cell_h
        label = html.escape(name + src.note(svg))
        body.append(
            f'<rect x="{x:g}" y="{y:g}" width="{SWATCH_W:g}" height="{SWATCH_H:g}" '
            f'fill="url(#{pat_id})" opacity="{args.opacity:g}"/>'
            f'<rect x="{x:g}" y="{y:g}" width="{SWATCH_W:g}" height="{SWATCH_H:g}" '
            f'fill="none" stroke="#999" stroke-width="0.5"/>'
            f'<text x="{x:g}" y="{y + SWATCH_H + 10:g}" font-size="8" fill="#333">{label}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width:g}" height="{height:g}" '
        f'viewBox="0 0 {width:g} {height:g}" font-family="Helvetica, Arial, sans-serif">'
        f"<defs>{''.join(defs)}</defs>"
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'<text x="{MARGIN:g}" y="{MARGIN + 14:g}" font-size="14" fill="#111">{html.escape(title)}</text>'
        f"{''.join(body)}</svg>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("output_dir", nargs="?", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--db", type=Path, default=ROOT / "calendar.db")
    ap.add_argument("--source", choices=["all", *SOURCES], default="all", help="which table(s) to render")
    ap.add_argument("--match", help="only tiles whose name contains this text")
    ap.add_argument("--limit", type=int, help="only the first N tiles per source")
    ap.add_argument("--per-page", type=int, default=120)
    ap.add_argument("--color", default="#333333")
    ap.add_argument("--pad", type=float, default=4.0, help="icons: margin around each icon in its tile (pt)")
    ap.add_argument("--icon-size", type=float, default=24.0, help="icons: drawn size of the largest side (pt)")
    ap.add_argument("--opacity", type=float, default=0.5, help="swatch pattern opacity, 0-1")
    ap.add_argument("--scale", type=float, default=1.0, help="tile scale multiplier")
    ap.add_argument("--no-stagger", action="store_true", help="icons: plain grid instead of offset rows")
    ap.add_argument(
        "--stagger-patterns",
        action="store_true",
        help="patterns: offset alternate rows by half a tile (seamless tiles will show a seam)",
    )
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.output_dir.glob("page_*.svg"):  # flat layout from earlier versions
        stale.unlink()
    sections: list[str] = []
    for src in SOURCES.values() if args.source == "all" else [SOURCES[args.source]]:
        tiles = load_tiles(args.db, src.table, args.match)
        if args.limit:
            tiles = tiles[: args.limit]
        if not tiles:
            print(f"{src.label}: no tiles matched")
            continue
        folder = args.output_dir / src.key
        folder.mkdir(exist_ok=True)
        for stale in folder.glob("page_*.svg"):
            stale.unlink()
        links = []
        pages = [tiles[i : i + args.per_page] for i in range(0, len(tiles), args.per_page)]
        for n, chunk in enumerate(pages, 1):
            rel = f"{src.key}/page_{n:03d}.svg"
            title = f"{src.label}: {chunk[0][0]} - {chunk[-1][0]} ({len(chunk)})"
            (args.output_dir / rel).write_text(build_page(src, chunk, title, args), encoding="utf-8")
            links.append(f'<li><a href="{rel}">{html.escape(title)}</a></li>')
        sections.append(
            f"<h2>{src.label} ({len(tiles)} from the <code>{src.table}</code> table)</h2><ul>{''.join(links)}</ul>"
        )
        print(f"{src.label}: {len(tiles)} tiles, {len(pages)} pages -> {folder}")
    (args.output_dir / "index.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>Pattern gallery</title><h1>Pattern gallery</h1>{''.join(sections)}",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
