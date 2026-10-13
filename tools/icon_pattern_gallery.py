"""Generate a gallery of pattern swatches, one section per source.  Standalone.

Sources (each is paged into its own folder, ``page_001.svg`` ..., and linked from
``index.html``):

* ``--svg-dir DIR`` (repeatable) -- every ``*.svg`` file in a folder; the file
  stem is the swatch name.  ``--svg-style`` chooses how they are tiled.
* ``icons/``    -- the ``icon`` table of a calendar.db: each icon becomes a padded
  tile, normalized to one size, with alternating rows staggered by half a tile.
* ``patterns/`` -- the ``patterns`` table of a calendar.db: tiles as a render
  draws them (auto-normalized to the pattern target size, no padding or stagger).

With ``--svg-dir`` only the folders are rendered, unless ``--source`` is given.
Without it, the database sources are rendered (``--db``, default ``./calendar.db``).

This file uses only the Python standard library and does not import the rest of
the EventCalendar codebase, so it can be copied anywhere and run with plain
``python3``.  The tile helpers below are a deliberate verbatim copy of
``renderers/svg_patterns.py``; ``tests/test_icon_pattern_gallery.py`` fails if the
two drift apart.

Usage: python3 icon_pattern_gallery.py [output_dir] [--svg-dir DIR ...]
       [--svg-style pattern|icon] [--db FILE] [--source icons|patterns|folders|all]
       [--match TEXT] [--limit N] [--per-page N] [--color HEX] [--pad PT]
       [--icon-size PT] [--opacity 0-1] [--scale X] [--no-stagger] [--stagger-patterns]
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

#: Default tile target size, in points (config.config.DEFAULT_PATTERN_TARGET_SIZE).
DEFAULT_PATTERN_TARGET_SIZE = 18.0

# ---------------------------------------------------------------------------
# Tile helpers: verbatim copy of renderers/svg_patterns.py (keep in sync).
# ---------------------------------------------------------------------------


def parse_svg_tile_size(svg: str) -> tuple[float, float]:
    """
    Extract tile width and height from an SVG string.

    Tries viewBox first (most reliable), then falls back to width/height
    attributes.  Returns (20, 20) if nothing can be parsed.
    """
    m = re.search(r'viewBox=["\'][\d.]+ [\d.]+ ([\d.]+) ([\d.]+)["\']', svg)
    if m:
        return float(m.group(1)), float(m.group(2))
    mw = re.search(r'<svg[^>]+width=["\'](\d+)(?:px)?["\']', svg)
    mh = re.search(r'<svg[^>]+height=["\'](\d+)(?:px)?["\']', svg)
    if mw and mh:
        return float(mw.group(1)), float(mh.group(1))
    return 20.0, 20.0


def normalize_tile_scale(
    tile_w: float,
    tile_h: float,
    target_size: float | None = DEFAULT_PATTERN_TARGET_SIZE,
    extra_scale: float = 1.0,
) -> float:
    """
    Return the factor that normalizes a tile to *target_size*.

    Auto-normalization is **shrink-only**: a tile whose largest dimension
    exceeds *target_size* is scaled down to it, and a tile already at or
    below the target is left alone.  Upscaling is deliberately not done —
    the goal is to stop oversized tiles from swamping a cell, not to
    inflate the small ones that already read correctly.

    *extra_scale* is a manual multiplier applied on top of the normalized
    factor, so a theme can nudge the whole library finer or coarser
    without restating the target.

    A *target_size* of None or <= 0 disables normalization, leaving only
    *extra_scale*.
    """
    scale = 1.0
    largest = max(tile_w, tile_h)
    if target_size and target_size > 0 and largest > 0:
        scale = min(1.0, target_size / largest)
    if extra_scale and extra_scale > 0:
        scale *= extra_scale
    return scale


def extract_pattern_inner(svg: str) -> str:
    """
    Return the inner content of a pattern SVG, ready to embed inside a
    ``<pattern>`` element.

    Peels off the XML prolog, doctype, and outer ``<svg>`` wrapper, then
    removes Inkscape-specific metadata (``<sodipodi:namedview>``,
    ``<metadata>``, and any leftover ``inkscape:`` / ``sodipodi:``
    attributes).  Those declarations live on the source ``<svg>`` element,
    so once that element is gone the prefixed content is no longer in
    scope and would make the embedding document invalid XML.
    """
    inner = re.sub(r"<\?xml[^>]*\?>", "", svg)
    inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner)
    inner = re.sub(r"<svg[^>]*>", "", inner, count=1)
    inner = inner.rsplit("</svg>", 1)[0]
    inner = re.sub(r"<sodipodi:namedview\b[^>]*/>", "", inner)
    inner = re.sub(
        r"<sodipodi:namedview\b[^>]*>.*?</sodipodi:namedview>",
        "",
        inner,
        flags=re.DOTALL,
    )
    inner = re.sub(r"<metadata\b[^>]*>.*?</metadata>", "", inner, flags=re.DOTALL)
    inner = re.sub(r"<metadata\b[^>]*/>", "", inner)
    inner = re.sub(r'\s+(?:inkscape|sodipodi):[a-zA-Z][\w-]*="[^"]*"', "", inner)
    inner = re.sub(r"\s+(?:inkscape|sodipodi):[a-zA-Z][\w-]*='[^']*'", "", inner)
    return inner.strip()


#: An ``id="…"`` declaration.  Empty values are skipped: they are already
#: invalid, and prefixing one would invent an id that nothing refers to.
_ID_DECL_RE = re.compile(r'\bid="([^"]+)"')

#: A same-document reference: ``url(#name)``, ``href="#name"`` or
#: ``xlink:href="#name"``.
_ID_REF_RE = re.compile(r'url\(\s*#([^)\s]+)\s*\)|(?:xlink:)?href="#([^"]+)"')


def scope_pattern_ids(inner: str, scope: str) -> str:
    """
    Prefix every id a tile declares with *scope*, and repoint the
    references that resolve to it.

    A tile's ids are authored as if it were its own document, but
    :func:`extract_pattern_inner` inlines its content into a shared
    ``<defs>``, so two tiles that use the same id collide.  The 112
    EMF-derived ``stars*`` tiles all carry ``defs2``, ``layer1``,
    ``base``, ``grid8``, ``metadata5`` and the empty hatch-base pattern
    ``EMFhbasepattern``, so a sheet showing 24 of them emits 24 copies of
    each.

    Today that is only invalid markup and not a wrong render, because no
    tile in the table references its own ids -- the colliding ones are
    inert leftovers.  The moment one does, though, a second copy would
    silently resolve to the first tile's element and paint the wrong
    thing with nothing to diagnose.  Scoping closes that off up front
    rather than after someone debugs it.

    Only references whose target is declared in this same tile are
    rewritten, so a reference out to the containing document (none ship
    today) still resolves.
    """
    local = set(_ID_DECL_RE.findall(inner))
    if not local:
        return inner

    def _declaration(m: re.Match[str]) -> str:
        return f'id="{scope}-{m.group(1)}"'

    def _reference(m: re.Match[str]) -> str:
        name = m.group(1) if m.group(1) is not None else m.group(2)
        if name not in local:
            return m.group(0)
        if m.group(1) is not None:
            return f"url(#{scope}-{name})"
        # Keep whichever spelling the source used (href / xlink:href).
        return m.group(0).replace(f"#{name}", f"#{scope}-{name}", 1)

    return _ID_DECL_RE.sub(_declaration, _ID_REF_RE.sub(_reference, inner))


#: A ``fill=`` / ``stroke=`` presentation attribute and its value.
_PAINT_ATTR_RE = re.compile(r'\b(fill|stroke)="([^"]*)"', re.IGNORECASE)

#: A ``fill:`` / ``stroke:`` declaration inside a ``style="…"`` attribute.
#: The lookbehind keeps the hyphenated properties out — ``fill-rule``,
#: ``fill-opacity``, ``stroke-width``, ``stroke-linejoin`` and friends have a
#: ``-`` rather than a ``:`` after the name, so they can never match anyway,
#: but the guard also stops a match starting mid-identifier.
_PAINT_STYLE_RE = re.compile(r'(?<![\w-])(fill|stroke)\s*:\s*([^;"}\s]+)', re.IGNORECASE)

#: Paint values that mean "draw nothing here", which must survive untouched:
#: repainting them would fill in shapes the artwork deliberately leaves
#: hollow.  ``inherit`` is left alone so it keeps resolving up the tree.
_UNPAINTED = frozenset({"none", "inherit", "transparent"})


def colorize_pattern_svg(svg: str, color: str | None) -> str:
    """
    Repaint a pattern tile's ink in *color*.

    Every tile in the ``patterns`` table is monochrome ink on transparent
    — a survey of all 350 finds exactly three ink values in use
    (``#000000``, ``#000`` and Serif's near-black ``rgb(35,31,32)``), and
    no tile mixes two.  So rather than matching a list of literals, this
    rewrites *every* paint declaration that draws something, in both the
    attribute form (``fill="…"``) and the ``style="fill:…"`` form that
    Inkscape and Serif exports use.

    ``currentColor`` is rewritten too.  Inside a ``<pattern>`` def it
    resolves against the def's own context rather than the element
    carrying ``fill="url(#pat-id)"``, so tiles declaring it used to
    render at the UA default regardless of the color a rule asked for.

    Values in :data:`_UNPAINTED` are left alone, so ``fill="none"`` keeps
    a shape hollow.  A tile that declares no paint at all inherits from
    the wrapper :func:`pattern_def_xml` emits.

    Note this flattens a tile to a single color by design.  Were a
    genuinely multi-color tile ever added to the table, it would need to
    opt out rather than be recolored.

    No-ops when *color* is None.
    """
    if not color:
        return svg

    def _attr(m: re.Match[str]) -> str:
        prop, value = m.group(1), m.group(2)
        if value.strip().lower() in _UNPAINTED:
            return m.group(0)
        return f'{prop}="{color}"'

    def _style(m: re.Match[str]) -> str:
        prop, value = m.group(1), m.group(2)
        if value.strip().lower() in _UNPAINTED:
            return m.group(0)
        return f"{prop}:{color}"

    result = _PAINT_ATTR_RE.sub(_attr, svg)
    return _PAINT_STYLE_RE.sub(_style, result)


#: A raster payload: an ``<image>`` element or an inline data URI.
_RASTER_RE = re.compile(r"<image\b|data:image/", re.IGNORECASE)


def pattern_is_recolorable(svg: str) -> bool:
    """
    Whether :func:`colorize_pattern_svg` can actually repaint this tile.

    False for a tile whose artwork is a raster image rather than vector
    geometry — the pixels carry their own color and no amount of ``fill``
    rewriting reaches them.  ``stars65`` is the only such tile in the
    shipped table (an embedded base64 PNG, which is also why it is by far
    the largest row at ~950 KB); it always renders in its baked-in black.

    Callers use this to tell a user why a pattern ignored their color,
    not to reject it: a raster tile still tiles correctly.
    """
    return not _RASTER_RE.search(svg)


def pattern_def_id(pattern_name: str, color: str | None) -> str:
    """Stable def id for a (pattern, color) pair: ``pat-{name}-{color}``."""
    safe_color = (color or "black").replace("#", "").replace(" ", "_")
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", pattern_name)
    return f"pat-{safe_name}-{safe_color}"


#: The opening ``<svg …>`` tag of a tile.
_ROOT_TAG_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)

#: Root stroke geometry that outline art relies on and that is lost with the root.
_ROOT_STROKE_ATTRS = ("stroke-width", "stroke-linecap", "stroke-linejoin")


def _root_attr(root: str, name: str) -> str | None:
    m = re.search(rf'(?<![\w-]){re.escape(name)}="([^"]*)"', root)
    return m.group(1).strip() if m else None


def root_paint_attrs(raw_svg: str, color: str | None) -> list[str]:
    """
    Paint attributes to carry from a tile's root ``<svg>`` onto its wrapper.

    :func:`extract_pattern_inner` drops the root element, and with it the
    inheritable paint children rely on.  Stroke-art icons (the ``icon``
    table) declare ``fill="none"`` and ``stroke="currentColor"`` once on
    the root, so without this they would be filled solid.

    * root ``fill="none"`` -> ``fill="none"``; otherwise ``fill`` is the color;
    * a root ``stroke`` that paints (``currentColor`` included) ->
      ``stroke`` is the color (the root's own value when no color is
      requested), with the root's stroke width / cap / join.
    """
    m = _ROOT_TAG_RE.search(raw_svg)
    root = m.group(0) if m else ""
    attrs: list[str] = []
    fill = _root_attr(root, "fill")
    if fill is not None and fill.lower() == "none":
        attrs.append('fill="none"')
    elif color:
        attrs.append(f'fill="{color}"')
    stroke = _root_attr(root, "stroke")
    if stroke is not None and stroke.lower() not in _UNPAINTED:
        attrs.append(f'stroke="{color or stroke}"')
        for name in _ROOT_STROKE_ATTRS:
            value = _root_attr(root, name)
            if value is not None:
                attrs.append(f'{name}="{value}"')
    return attrs


def pattern_def_xml(
    pat_id: str,
    raw_svg: str,
    color: str | None,
    target_size: float | None = DEFAULT_PATTERN_TARGET_SIZE,
    extra_scale: float = 1.0,
    *,
    pad: float = 0.0,
    stagger: bool = False,
) -> str:
    """Build the complete ``<pattern>`` element for an SVG ``<defs>`` block.

    Tiles with ``patternUnits="userSpaceOnUse"`` so tile sizes are in
    document coordinates.  The tile is auto-normalized per
    :func:`normalize_tile_scale`: the artwork is wrapped in a scaling
    ``<g>`` and the pattern's reported width/height shrink by the same
    factor, so it keeps tiling seamlessly at the smaller size.

    The def id does not encode the scale, because *target_size* and
    *extra_scale* come from the config and are therefore constant across
    a single document — one pattern name resolves to one scale per
    drawing.  Pass distinct ids if that ever stops holding.

    The artwork is wrapped in a ``<g>`` carrying the paint that
    ``extract_pattern_inner`` strips with the root ``<svg>``; see
    :func:`root_paint_attrs` (``fill="none"`` and a root stroke are kept
    so outline icons are not filled solid).

    *pad* adds that much empty margin on every side of the artwork, so
    tiles that are drawn edge to edge do not touch.  *stagger* doubles
    the tile height and offsets the second row by half a tile width
    (brick layout); the artwork is defined once and ``<use>``d, so its
    ids stay unique.

    The tile's own ids are scoped to *pat_id* first, so two tiles that
    were authored with the same id do not collide once both are inlined
    into one ``<defs>``.
    """
    tile_w, tile_h = parse_svg_tile_size(raw_svg)
    inner = extract_pattern_inner(colorize_pattern_svg(raw_svg, color))
    # The def id is unique per (pattern, color), so it is the natural scope
    # for the tile's own ids once they land in a shared <defs>.
    inner = scope_pattern_ids(inner, pat_id)

    attrs = root_paint_attrs(raw_svg, color)
    cell_w = tile_w + 2 * pad
    cell_h = tile_h + 2 * pad
    if stagger:
        art_id = f"{pat_id}-art"
        art_attrs = [f'id="{art_id}"', f'transform="translate({pad:.6g} {pad:.6g})"', *attrs]
        half = cell_w / 2
        inner = (
            f"<g {' '.join(art_attrs)}>{inner}</g>"
            f'<use href="#{art_id}" x="{-half:.6g}" y="{cell_h:.6g}"/>'
            f'<use href="#{art_id}" x="{half:.6g}" y="{cell_h:.6g}"/>'
        )
        tile_w, tile_h = cell_w, 2 * cell_h
        attrs = []
    elif pad:
        attrs = [f'transform="translate({pad:.6g} {pad:.6g})"', *attrs]
        tile_w, tile_h = cell_w, cell_h

    scale = normalize_tile_scale(tile_w, tile_h, target_size, extra_scale)
    if scale != 1.0:
        # Merge into the single wrapper unless it already carries a transform.
        if any(a.startswith("transform=") for a in attrs) or stagger:
            inner = f'<g transform="scale({scale:.6g})">{inner}</g>'
        else:
            attrs.insert(0, f'transform="scale({scale:.6g})"')
        tile_w *= scale
        tile_h *= scale
    if attrs:
        inner = f"<g {' '.join(attrs)}>{inner}</g>"

    return (
        f'<pattern id="{pat_id}" x="0" y="0" '
        f'width="{tile_w:.6g}" height="{tile_h:.6g}" '
        f'patternUnits="userSpaceOnUse">'
        f"{inner}"
        f"</pattern>"
    )


# ---------------------------------------------------------------------------
# Gallery
# ---------------------------------------------------------------------------

DEFAULT_OUT = Path("pattern_gallery")
DEFAULT_DB = Path("calendar.db")
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
    """One set of SVG tiles and how its swatches are built."""

    key: str  # output subfolder
    label: str
    origin: str  # shown in the index, e.g. "the <code>icon</code> table"
    tile_def: Callable[[str, str, argparse.Namespace], str]  # (pat_id, svg, args) -> <pattern> xml
    note: Callable[[str], str]  # svg -> label suffix, shown when recoloring
    table: str | None = None  # database table, or None for a folder
    folder: Path | None = None


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


def _icon_note(svg: str) -> str:
    return " (flattened)" if is_flattened(svg) else ""


def _pattern_note(svg: str) -> str:
    return "" if pattern_is_recolorable(svg) else " (fixed)"


DB_SOURCES = {
    "icons": Source("icons", "Icons", "the <code>icon</code> table", _icon_tile, _icon_note, table="icon"),
    "patterns": Source(
        "patterns", "Patterns", "the <code>patterns</code> table", _pattern_tile, _pattern_note, table="patterns"
    ),
}


def folder_source(path: Path, style: str, taken: set[str]) -> Source:
    """A source for a folder of SVG files; its output subfolder is unique among *taken*."""
    base = "folder-" + (re.sub(r"[^A-Za-z0-9_.-]+", "_", path.resolve().name) or "svg")
    key, n = base, 2
    while key in taken:
        key, n = f"{base}-{n}", n + 1
    taken.add(key)
    icon = style == "icon"
    return Source(
        key,
        f"Folder {path.resolve().name}",
        f"the folder <code>{html.escape(str(path))}</code>",
        _icon_tile if icon else _pattern_tile,
        _icon_note if icon else _pattern_note,
        folder=path,
    )


def _filter(tiles: list[tuple[str, str]], match: str | None) -> list[tuple[str, str]]:
    needle = match.lower() if match else None
    return [(n, s) for n, s in tiles if n and s and (needle is None or needle in n.lower())]


def load_db_tiles(db_path: Path, table: str, match: str | None) -> list[tuple[str, str]]:
    # Read-only, so a missing file is an error rather than a freshly created empty database.
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        rows = conn.execute(f"SELECT name, svg FROM {table} WHERE svg IS NOT NULL ORDER BY name").fetchall()
    except sqlite3.OperationalError as exc:
        print(f"{db_path}: cannot read table {table!r}: {exc}", file=sys.stderr)
        return []
    finally:
        conn.close()
    return _filter(rows, match)


def load_folder_tiles(folder: Path, match: str | None) -> list[tuple[str, str]]:
    tiles: list[tuple[str, str]] = []
    for path in sorted(folder.glob("*.svg"), key=lambda p: p.name.lower()):
        try:
            tiles.append((path.stem, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{path}: skipped ({exc})", file=sys.stderr)
    return _filter(tiles, match)


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
        label = html.escape(name + (src.note(svg) if args.color else ""))
        body.append(
            f'<rect x="{x:g}" y="{y:g}" width="{SWATCH_W:g}" height="{SWATCH_H:g}" '
            f'fill="url(#{pat_id})" opacity="{args.opacity:g}"/>'
            f'<rect x="{x:g}" y="{y:g}" width="{SWATCH_W:g}" height="{SWATCH_H:g}" '
            f'fill="none" stroke="#999" stroke-width="0.5"/>'
            f'<text x="{x:g}" y="{y + SWATCH_H + 10:g}" font-size="8" fill="#333">{label}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width:g}" height="{height:g}" '
        f'viewBox="0 0 {width:g} {height:g}" font-family="Helvetica, Arial, sans-serif">'
        f"<defs>{''.join(defs)}</defs>"
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'<text x="{MARGIN:g}" y="{MARGIN + 14:g}" font-size="14" fill="#111">{html.escape(title)}</text>'
        f"{''.join(body)}</svg>"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("output_dir", nargs="?", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--svg-dir", type=Path, action="append", default=[], metavar="DIR", help="folder of .svg files (repeatable)"
    )
    ap.add_argument(
        "--svg-style",
        choices=["pattern", "icon"],
        default="pattern",
        help="how folder SVGs are tiled: as-is like a pattern, or normalized and padded like an icon",
    )
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="calendar.db with icon/patterns tables")
    ap.add_argument(
        "--source",
        choices=["all", "folders", *DB_SOURCES],
        help="what to render (default: the --svg-dir folders if given, else the database tables)",
    )
    ap.add_argument("--match", help="only tiles whose name contains this text")
    ap.add_argument("--limit", type=int, help="only the first N tiles per source")
    ap.add_argument("--per-page", type=int, default=120)
    ap.add_argument("--color", help="recolor every tile to this color (default: keep the original colors)")
    ap.add_argument("--pad", type=float, default=4.0, help="icon style: margin around each icon in its tile (pt)")
    ap.add_argument("--icon-size", type=float, default=24.0, help="icon style: drawn size of the largest side (pt)")
    ap.add_argument("--opacity", type=float, default=0.5, help="swatch pattern opacity, 0-1")
    ap.add_argument("--scale", type=float, default=1.0, help="tile scale multiplier")
    ap.add_argument("--no-stagger", action="store_true", help="icon style: plain grid instead of offset rows")
    ap.add_argument(
        "--stagger-patterns",
        action="store_true",
        help="pattern style: offset alternate rows by half a tile (seamless tiles will show a seam)",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    source = args.source or ("folders" if args.svg_dir else "all")
    want_db = source in ("all", *DB_SOURCES)
    want_folders = source in ("all", "folders")
    if source == "folders" and not args.svg_dir:
        sys.exit("--source folders needs at least one --svg-dir")
    for folder in args.svg_dir:
        if not folder.is_dir():
            sys.exit(f"--svg-dir {folder}: not a folder")
    if want_db and not args.db.is_file():
        if source in DB_SOURCES or not (want_folders and args.svg_dir):
            sys.exit(f"database not found: {args.db} (use --db, or --svg-dir for a folder of SVG files)")
        want_db = False

    jobs: list[tuple[Source, list[tuple[str, str]]]] = []
    taken: set[str] = set(DB_SOURCES)
    if want_folders:
        for folder in args.svg_dir:
            src = folder_source(folder, args.svg_style, taken)
            jobs.append((src, load_folder_tiles(folder, args.match)))
    if want_db:
        for key, src in DB_SOURCES.items():
            if source in ("all", key) and src.table:
                jobs.append((src, load_db_tiles(args.db, src.table, args.match)))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.output_dir.glob("page_*.svg"):  # flat layout from earlier versions
        stale.unlink()
    sections: list[str] = []
    for src, tiles in jobs:
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
        sections.append(f"<h2>{html.escape(src.label)} ({len(tiles)} from {src.origin})</h2><ul>{''.join(links)}</ul>")
        print(f"{src.label}: {len(tiles)} tiles, {len(pages)} pages -> {folder}")
    if not sections:
        sys.exit("nothing to render")
    (args.output_dir / "index.html").write_text(
        f"<!doctype html><meta charset=utf-8><title>Pattern gallery</title><h1>Pattern gallery</h1>{''.join(sections)}",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
