"""
Sample-sheet SVG generators.

The inspection subcommands (``palettesheet``, ``colorsheet``,
``fontsheet``, ``iconsheet``, ``patternsheet``) render reference sheets
of the database's palettes, named colors, registered fonts, icons, and
patterns.  These are standalone SVG-string builders -- they do not go
through the layout/renderer pipeline the calendar visualizers use.
"""

from __future__ import annotations

from pathlib import Path


def _hex_hsv_sort_key(color: str) -> tuple:
    """
    HSV sort key for a hex colour string, matching the colorsheet ordering.

    Parses a ``#RRGGBB`` (or ``RRGGBB``) string into RGB, then returns the
    ``(hue, saturation, value)`` tuple used to sort swatches.  This is the same
    perceptual-hue ordering applied to the ``colorsheet`` output: achromatic
    colours (blacks/greys/whites) first, then reds, oranges, yellows, greens,
    blues, purples.

    Args:
        color: Hex colour string, with or without a leading ``#``.

    Returns:
        ``(h, s, v)`` tuple of floats in 0–1, suitable as a ``sorted`` key.
    """
    import colorsys

    hx = color.lstrip("#")
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)
    try:
        red = int(hx[0:2], 16) / 255.0
        green = int(hx[2:4], 16) / 255.0
        blue = int(hx[4:6], 16) / 255.0
    except (ValueError, IndexError):
        return (0.0, 0.0, 0.0)
    return colorsys.rgb_to_hsv(red, green, blue)


def _parse_hex_rgb(color: str) -> tuple[int, int, int]:
    """Parse a hex colour string into ``(red, green, blue)`` 0–255 ints.

    Accepts 3- or 6-digit hex with or without a leading ``#``.  Returns
    ``(0, 0, 0)`` on malformed input rather than raising.
    """
    hx = color.lstrip("#")
    if len(hx) == 3:
        hx = "".join(c * 2 for c in hx)
    try:
        return int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
    except (ValueError, IndexError):
        return (0, 0, 0)


def _swatch_value_labels(cx: float, cy: float, red: int, green: int, blue: int) -> list[str]:
    """SVG ``<text>`` lines for the hex value and RGB triplet inside a swatch.

    Hex sits on top, the zero-padded ``XXX,XXX,XXX`` RGB triplet just below.
    Text colour flips to white on dark backgrounds (luminance < 128) so the
    labels stay legible.  Shared by the colorsheet and palettesheet outputs.

    Args:
        cx, cy: Centre point of the swatch box.
        red, green, blue: Channel values (0–255).
    """
    hex_color = f"#{red:02X}{green:02X}{blue:02X}"
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    text_color = "white" if luminance < 128 else "#222"
    return [
        f'  <text x="{cx}" y="{cy - 2}"'
        f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
        f' fill="{text_color}" text-anchor="middle">{hex_color}</text>',
        f'  <text x="{cx}" y="{cy + 12}"'
        f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
        f' fill="{text_color}" text-anchor="middle">{red:03d},{green:03d},{blue:03d}</text>',
    ]


def _swatch_name_label(cx: float, baseline_y: float, name: str) -> str:
    """SVG ``<text>`` line for the lowercase colour name below a swatch.

    Shared by the colorsheet and palettesheet outputs.
    """
    return (
        f'  <text x="{cx}" y="{baseline_y}"'
        f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
        f' fill="#555" text-anchor="middle">{_xml_escape(name.lower())}</text>'
    )


# --------------------------------------------------------------------------- #
# Pagination helpers shared by the colorsheet, fontsheet, iconsheet and        #
# palettesheet                                                                 #
# --------------------------------------------------------------------------- #
#
# All four sheets support the same ``--paginate`` model: instead of one very
# large SVG, the items are split into pages and each page is written to its own
# file with a ``_pNN`` suffix.  The colorsheet, fontsheet and iconsheet chunk by
# ``columns × rows`` entries; the all-palettes sheet instead packs whole palette
# sections into a per-page height budget (see _pack_palette_sections).  The
# helpers below own that shared behaviour so the individual generators only have
# to describe how one page is drawn.

_SHEET_MARGIN = 40
_SHEET_TITLE_H = 55


def _xml_escape(text: str) -> str:
    """Escape ``&``/``<``/``>`` so *text* is safe inside an SVG text node."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _paginate_items(items: list, columns: int, rows: int) -> list[list]:
    """Split *items* into pages of at most ``columns × rows`` entries.

    Always returns at least one (possibly empty) page so callers can render an
    empty sheet rather than writing no file at all.
    """
    per_page = max(1, max(1, columns) * max(1, rows))
    pages = [items[i : i + per_page] for i in range(0, len(items), per_page)]
    return pages or [[]]


def _page_output_path(output_path: Path, page_idx: int, npages: int) -> Path:
    """Path for one page: ``sheet.svg`` → ``sheet_p03.svg`` (1-based).

    A single-page run keeps the base filename unchanged.
    """
    if npages <= 1:
        return output_path
    return output_path.with_name(
        f"{output_path.stem}_p{page_idx + 1:02d}{output_path.suffix}"
    )


def _write_sheet_pages(output_path: Path, pages: list[str]) -> list[Path]:
    """Write rendered page documents, numbering them when there is more than one.

    Returns the list of paths actually written, in page order.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for idx, document in enumerate(pages):
        page_path = _page_output_path(output_path, idx, len(pages))
        page_path.write_text(document, encoding="utf-8")
        written.append(page_path)
    return written


def _range_subtitle(names: list[str]) -> str:
    """``(first to last)`` subtitle describing the items on one page.

    Used on paginated pages in place of the total item count, so a printed
    stack of sheets can be located by name at a glance.  Collapses to
    ``(name)`` when the page holds a single item, and to an empty string when
    the page is empty.
    """
    if not names:
        return ""
    first, last = names[0], names[-1]
    return f"({first})" if first == last else f"({first} to {last})"


def _sheet_header_lines(
    svg_w: float, svg_h: float, header: str, subtitle: str, title_dy: int = 36
) -> list[str]:
    """Opening SVG element, white background and the title line of a sheet page.

    *subtitle* is the smaller grey parenthetical after the title — either an
    item count (``(140 colors)``) or a page range from :func:`_range_subtitle`.
    *title_dy* is the title baseline's offset below the top margin (the
    fontsheet sits its title 4 pt lower than the swatch sheets).
    """
    subtitle_tspan = (
        f'  <tspan font-size="18" font-weight="normal" font-style="normal"'
        f' fill="#666">{_xml_escape(subtitle)}</tspan>'
        if subtitle
        else ""
    )
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}"'
        f' viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
        f'  <text x="{_SHEET_MARGIN}" y="{_SHEET_MARGIN + title_dy}"'
        f' font-family="Helvetica, Arial, sans-serif"'
        f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
        f"{_xml_escape(header)}{subtitle_tspan}</text>",
    ]


def _render_swatch_page(
    swatches: list[tuple[str, str, int, int, int]],
    header: str,
    subtitle: str,
    ncols: int,
    *,
    box_w: int,
    box_h: int,
    label_h: int,
    gap_x: int,
    gap_y: int,
) -> str:
    """Render one page of colour swatches to an SVG document string.

    Shared by the colorsheet and palettesheet, whose cells are identical apart
    from box geometry: a filled box with the hex value and RGB triplet centred
    inside it and the colour name below.

    Args:
        swatches: ``(name, fill, red, green, blue)`` tuples in display order.
                  *fill* is the literal SVG paint (kept verbatim from the
                  source data), while the RGB channels drive the labels.
        header:   Sheet title drawn at the top left.
        subtitle: Grey parenthetical after the title (count or page range).
        ncols:    Swatches per row.
        box_w/box_h/label_h/gap_x/gap_y: Cell geometry in points.
    """
    import math

    cell_w = box_w + gap_x
    cell_h = box_h + label_h + gap_y

    n = len(swatches)
    nrows = math.ceil(n / ncols) if n else 1
    svg_w = _SHEET_MARGIN * 2 + ncols * cell_w - gap_x
    svg_h = _SHEET_MARGIN + _SHEET_TITLE_H + nrows * cell_h - gap_y + _SHEET_MARGIN

    lines = _sheet_header_lines(svg_w, svg_h, header, subtitle)

    for i, (name, fill, red, green, blue) in enumerate(swatches):
        row = i // ncols
        col = i % ncols
        x = _SHEET_MARGIN + col * cell_w
        y = _SHEET_MARGIN + _SHEET_TITLE_H + row * cell_h
        cx = x + box_w // 2

        lines.append(
            f'  <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}"'
            f' fill="{fill}" stroke="#bbbbbb" stroke-width="0.5"/>'
        )
        # Hex value + RGB triplet centred inside the swatch
        lines.extend(_swatch_value_labels(cx, y + box_h // 2, red, green, blue))
        # Colour name below the swatch (forced lowercase)
        lines.append(_swatch_name_label(cx, y + box_h + 18, name))

    lines.append("</svg>")
    return "\n".join(lines)


# Palette-sheet cell geometry (shared by the single-palette, all-palettes and
# paginated variants).
_PALETTE_BOX = 80
_PALETTE_LABEL_H = 26
_PALETTE_GAP_X = 10
_PALETTE_GAP_Y = 14
_PALETTE_MAX_COLS = 12


def _palette_swatches(
    colors: list[str], name_lookup: dict[str, str] | None
) -> list[tuple[str, str, int, int, int]]:
    """Hue-sort palette colours into ``(name, fill, r, g, b)`` swatch tuples.

    The colour string from the database is kept verbatim as the SVG fill; the
    label falls back to the hex value when the colour has no name in the
    ``colors`` table.
    """
    swatches: list[tuple[str, str, int, int, int]] = []
    for color in sorted(colors, key=_hex_hsv_sort_key):
        hx = color.upper() if color.startswith("#") else f"#{color.upper()}"
        red, green, blue = _parse_hex_rgb(color)
        swatches.append(
            ((name_lookup or {}).get(hx) or hx, color, red, green, blue)
        )
    return swatches


def _palette_pages(
    name: str,
    swatches: list[tuple[str, str, int, int, int]],
    paginate: bool,
    columns: int,
    rows: int,
    cell_size: int,
) -> list[str]:
    """Render one palette to a list of SVG page documents.

    A non-paginated palette is always a single page up to
    ``_PALETTE_MAX_COLS`` swatches wide.  When paginating, the palette is split
    into ``columns × rows`` pages; the title subtitle then shows the page's
    colour-name range instead of the palette's total colour count (a palette
    that still fits on one page keeps the count).
    """
    n = len(swatches)
    box = max(1, cell_size)
    geometry = dict(
        box_w=box,
        box_h=box,
        label_h=_PALETTE_LABEL_H,
        gap_x=_PALETTE_GAP_X,
        gap_y=_PALETTE_GAP_Y,
    )

    if not paginate:
        ncols = min(n, _PALETTE_MAX_COLS) if n else 1
        return [
            _render_swatch_page(
                swatches, name, f"({n} colors)", ncols, **geometry
            )
        ]

    ncols = max(1, columns)
    pages = _paginate_items(swatches, ncols, rows)
    single = len(pages) == 1
    return [
        _render_swatch_page(
            page,
            name,
            f"({n} colors)" if single else _range_subtitle([s[0] for s in page]),
            ncols,
            **geometry,
        )
        for page in pages
    ]


def _generate_palette_svg(
    name: str,
    colors: list[str],
    output_path: Path,
    name_lookup: dict[str, str] | None = None,
    paginate: bool = False,
    columns: int = _PALETTE_MAX_COLS,
    rows: int = 10,
    cell_size: int = _PALETTE_BOX,
) -> list[Path]:
    """
    Write one or more SVG files showing a colour palette as a grid of swatches.

    Each swatch displays the colour as a filled box with its hex value and RGB
    triplet inside it and the colour name below.  Swatches are sorted by
    perceptual hue (the same HSV ordering used by the colorsheet).  The title
    bar shows the palette name and total colour count.

    Provides a quick visual reference so users can choose palettes for their
    themes without needing to render a full calendar.

    Output modes
    ────────────
    Single sheet (``paginate=False``, the default):
        Every colour in one SVG written to ``output_path``, up to 12 swatches
        per row.

    Paginated (``paginate=True``):
        The palette is split into pages of at most ``columns × rows`` swatches,
        written with a ``_pNN`` suffix before the extension (a single resulting
        page keeps the base filename).  The title subtitle then shows the
        page's colour-name range, e.g. ``(azure to steelblue)``.

    Called by:
        run() when args.command == "palettesheet".

    Args:
        name:        Palette name shown in the SVG title.
        colors:      Ordered list of hex colour strings (e.g. ``["#4472C4", …]``).
        output_path: Destination path for the generated SVG file (page suffix
                     added automatically when more than one page is produced).
        name_lookup: Uppercase-hex → colour-name map used for swatch labels.
        paginate:    When True, split swatches across ``columns × rows`` pages.
        columns:     Swatches per row on each page when paginating (default 12).
        rows:        Rows of swatches per page when paginating (default 10).
        cell_size:   Swatch box size in points (width = height); the label and
                     spacing gaps are unchanged (default 80).

    Returns:
        List of ``Path`` objects actually written, in page order.
    """
    pages = _palette_pages(
        name, _palette_swatches(colors, name_lookup), paginate, columns, rows, cell_size
    )
    return _write_sheet_pages(output_path, pages)


_PALETTE_SECTION_TITLE_H = 40
_PALETTE_SECTION_GAP = 24


def _palette_section_lines(
    name: str,
    swatches: list[tuple[str, str, int, int, int]],
    ncols: int,
    title_y: float,
    grid_y: float,
    box: int,
) -> list[str]:
    """SVG lines for one palette section: its title row plus its swatch grid.

    Shared by the one-sheet-per-run layout and the packed pages produced by
    ``--paginate``, so a palette looks the same either way.
    """
    cell_w = box + _PALETTE_GAP_X
    cell_h = box + _PALETTE_LABEL_H + _PALETTE_GAP_Y
    n = len(swatches)

    lines = [
        f'  <text x="{_SHEET_MARGIN}" y="{title_y + 28}"'
        f' font-family="Helvetica, Arial, sans-serif" font-size="22"'
        f' font-weight="bold" font-style="italic" fill="#222">'
        f'{_xml_escape(name)}  <tspan font-size="16" font-weight="normal"'
        f' font-style="normal" fill="#666">({n} colors)</tspan></text>'
    ]

    for i, (col_name, fill, red, green, blue) in enumerate(swatches):
        row = i // ncols
        col = i % ncols
        x = _SHEET_MARGIN + col * cell_w
        y = grid_y + row * cell_h
        cx = x + box // 2
        lines.append(
            f'  <rect x="{x}" y="{y}" width="{box}" height="{box}"'
            f' fill="{fill}" stroke="#bbbbbb" stroke-width="0.5"/>'
        )
        # Hex + RGB inside the swatch (same as the colorsheet)
        lines.extend(_swatch_value_labels(cx, y + box // 2, red, green, blue))
        # Colour name below the swatch (same as the colorsheet); falls back to
        # the hex value when the colour has no name in the database.
        lines.append(_swatch_name_label(cx, y + box + 18, col_name))

    return lines


def _pack_palette_sections(
    sections: list[tuple[str, list[tuple[str, str, int, int, int]], int, float]],
    budget_h: float,
) -> list[list[tuple[str, list[tuple[str, str, int, int, int]], int, float]]]:
    """Greedily group whole palette sections into pages of at most *budget_h*.

    Palettes are never split: a section that does not fit in the space left on
    the current page starts the next one, and a section taller than a whole
    page simply gets a page of its own (that page ends up taller than the
    others rather than cutting the palette in half).

    Args:
        sections: ``(name, swatches, ncols, section_height)`` in render order.
        budget_h: Content height one page should aim for, in points.

    Returns:
        List of pages, each a list of the sections placed on it.
    """
    pages: list[list] = []
    current: list = []
    used = 0.0
    for section in sections:
        height = section[3]
        gap = _PALETTE_SECTION_GAP if current else 0
        if current and used + gap + height > budget_h:
            pages.append(current)
            current = [section]
            used = height
        else:
            current.append(section)
            used += gap + height
    if current:
        pages.append(current)
    return pages


def _render_palette_sections_page(
    sections: list[tuple[str, list[tuple[str, str, int, int, int]], int, float]],
    svg_w: float,
    min_content_h: float,
    box: int,
) -> str:
    """Render a page holding one or more complete palette sections."""
    content_h = sum(s[3] for s in sections) + _PALETTE_SECTION_GAP * max(
        0, len(sections) - 1
    )
    svg_h = _SHEET_MARGIN * 2 + max(min_content_h, content_h)

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}"'
        f' viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
    ]

    y_cursor = _SHEET_MARGIN
    for name, swatches, ncols, height in sections:
        lines.extend(
            _palette_section_lines(
                name,
                swatches,
                ncols,
                y_cursor,
                y_cursor + _PALETTE_SECTION_TITLE_H,
                box,
            )
        )
        y_cursor += height + _PALETTE_SECTION_GAP

    lines.append("</svg>")
    return "\n".join(lines)


def _generate_all_palettes_svg(
    palettes: dict[str, list[str]],
    output_path: Path,
    name_lookup: dict[str, str] | None = None,
    paginate: bool = False,
    columns: int = _PALETTE_MAX_COLS,
    rows: int = 10,
    cell_size: int = _PALETTE_BOX,
) -> list[Path]:
    """
    Write every palette in the database, either as one sheet or as packed pages.

    Output modes
    ────────────
    Single sheet (``paginate=False``, the default):
        One SVG containing every palette as a labeled section of swatches.
        Palettes are rendered top-to-bottom in alphabetical order. Each section
        has a title row (palette name + colour count) followed by a grid of
        swatches (up to 12 per row), sorted by perceptual hue (the same HSV
        ordering used by the colorsheet), matching the layout used by
        ``_generate_palette_svg``.

    Paginated (``paginate=True``):
        The same sections, split across printable pages that each hold as many
        *complete* palettes as fit: a page's content budget is the height of
        ``rows`` swatch rows, sections are packed into it greedily in
        alphabetical order, and a palette is never split across a page break
        (one taller than a whole page gets its own, taller, page).  ``columns``
        caps how wide each palette's grid wraps and therefore the page width.
        Pages are numbered sequentially with a ``_pNN`` suffix.

    Called by:
        run() when args.command == "palettesheet" and no palette name is given.

    Returns:
        List of ``Path`` objects actually written, in page order.
    """
    import math

    box = max(1, cell_size) if paginate else _PALETTE_BOX
    max_cols = max(1, columns) if paginate else _PALETTE_MAX_COLS
    cell_w = box + _PALETTE_GAP_X
    cell_h = box + _PALETTE_LABEL_H + _PALETTE_GAP_Y

    names = sorted(palettes.keys())
    sections: list[tuple[str, list[tuple[str, str, int, int, int]], int, float]] = []
    for name in names:
        swatches = _palette_swatches(palettes[name], name_lookup)
        n = len(swatches)
        ncols = min(n, max_cols) if n else 1
        nrows = math.ceil(n / ncols) if n else 0
        height = (
            _PALETTE_SECTION_TITLE_H + nrows * cell_h - (_PALETTE_GAP_Y if nrows else 0)
        )
        sections.append((name, swatches, ncols, height))

    if paginate:
        # A page aims to hold the same vertical space as ``rows`` swatch rows;
        # whole palettes are then packed into that budget.
        budget_h = max(1, rows) * cell_h - _PALETTE_GAP_Y
        svg_w = _SHEET_MARGIN * 2 + max_cols * cell_w - _PALETTE_GAP_X
        packed = _pack_palette_sections(sections, budget_h) or [[]]
        pages = [
            _render_palette_sections_page(page, svg_w, budget_h, box)
            for page in packed
        ]
        return _write_sheet_pages(output_path, pages)

    max_cols_used = min(max_cols, max((len(palettes[n]) for n in names), default=1))
    svg_w = _SHEET_MARGIN * 2 + max_cols_used * cell_w - _PALETTE_GAP_X
    svg_h = (
        sum(s[3] for s in sections)
        + _PALETTE_SECTION_GAP * max(0, len(sections) - 1)
        + _SHEET_MARGIN * 2
    )

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
    ]

    y_cursor = _SHEET_MARGIN
    for name, swatches, ncols, height in sections:
        lines.extend(
            _palette_section_lines(
                name,
                swatches,
                ncols,
                y_cursor,
                y_cursor + _PALETTE_SECTION_TITLE_H,
                box,
            )
        )
        y_cursor += height + _PALETTE_SECTION_GAP

    lines.append("</svg>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return [output_path]


# Colorsheet cell geometry.  The box is wider than it is tall so the hex value
# and RGB triplet fit on two lines inside the swatch; ``cell_size`` scales the
# width and keeps this aspect ratio.
_COLORSHEET_BOX_W = 110
_COLORSHEET_BOX_H = 60
_COLORSHEET_LABEL_H = 30
_COLORSHEET_GAP_X = 12
_COLORSHEET_GAP_Y = 10
_COLORSHEET_MAX_COLS = 8


def _generate_colorsheet_svg(
    colors: list[dict],
    output_path: "Path",
    title: str = "Colors",
    paginate: bool = False,
    columns: int = _COLORSHEET_MAX_COLS,
    rows: int = 10,
    cell_size: int = _COLORSHEET_BOX_W,
) -> list["Path"]:
    """
    Write one or more SVG grids of named-colour swatches from the ``colors`` table.

    Complements the ``colors`` listing command with a visual browseable sheet.
    The caller is responsible for ordering ``colors`` before passing them in;
    run() sorts by HSV hue via the ``_hsv_sort_key`` nested function so the
    sheet groups colours by hue rather than alphabetically.

    Each swatch shows:
    - Filled colour box (up to 8 columns; rows added as needed)
    - Hex value centred inside the box (white text on dark backgrounds,
      dark text on light backgrounds — determined by luminance threshold 128)
    - EN colour name below the box

    Output modes
    ────────────
    Single sheet (``paginate=False``, the default):
        Every colour is laid out in one SVG written to ``output_path``, up to
        ``_COLORSHEET_MAX_COLS`` swatches wide, headed by *title*.

    Paginated (``paginate=True``):
        Colours are split into pages of at most ``columns × rows`` swatches so
        each sheet stays small enough to print.  Pages are written with a
        ``_pNN`` suffix inserted before the extension (e.g.
        ``colorsheet_p01.svg``); a single resulting page keeps the base
        filename.  Each page keeps *title* as its header but replaces the
        colour count with the page's name range, e.g. ``(azure to steelblue)``.

    Called by:
        run() when args.command == "colorsheet", after HSV sorting.

    Args:
        colors:      List of colour dicts with keys: EN, red, green, blue, hex.
        output_path: Destination path for the generated SVG file (page suffix
                     added automatically when more than one page is produced).
        title:       SVG title string (includes filter text when --filter is set).
        paginate:    When True, split swatches across ``columns × rows`` pages.
        columns:     Swatches per row on each page when paginating (default 8).
        rows:        Rows of swatches per page when paginating (default 10).
        cell_size:   Swatch box width in points; the height scales with it to
                     keep the sheet's default aspect ratio, and the label and
                     spacing gaps are unchanged (default 110).

    Returns:
        List of ``Path`` objects actually written, in page order.
    """
    swatches: list[tuple[str, str, int, int, int]] = []
    for row in colors:
        name = str(row.get("EN") or "").strip()
        red = int(row.get("red") or 0)
        green = int(row.get("green") or 0)
        blue = int(row.get("blue") or 0)
        swatches.append((name, f"#{red:02x}{green:02x}{blue:02x}", red, green, blue))

    n = len(swatches)
    box_w = max(1, cell_size)
    box_h = max(1, round(box_w * _COLORSHEET_BOX_H / _COLORSHEET_BOX_W))
    geometry = dict(
        box_w=box_w,
        box_h=box_h,
        label_h=_COLORSHEET_LABEL_H,
        gap_x=_COLORSHEET_GAP_X,
        gap_y=_COLORSHEET_GAP_Y,
    )

    if not paginate:
        ncols = min(n, _COLORSHEET_MAX_COLS) if n else 1
        pages = [
            _render_swatch_page(swatches, title, f"({n} colors)", ncols, **geometry)
        ]
        return _write_sheet_pages(output_path, pages)

    ncols = max(1, columns)
    chunks = _paginate_items(swatches, ncols, rows)
    pages = [
        _render_swatch_page(
            chunk,
            title,
            _range_subtitle([s[0] for s in chunk]),
            ncols,
            **geometry,
        )
        for chunk in chunks
    ]
    return _write_sheet_pages(output_path, pages)


def _render_font_fullset(
    font_path: str,
    x_start: float,
    content_width: float,
    font_size: float,
    color: str,
) -> tuple[list[str], float]:
    """
    Render every mapped codepoint in a font as SVG ``<path>`` elements.

    Glyphs are emitted in codepoint order, placed horizontally from *x_start*
    and wrapped to a new line when the next glyph would exceed *x_start +
    content_width*.  Paths use a local coordinate space starting at (x_start, 0);
    callers must translate via ``<g transform="translate(0,{y_offset})">``.

    Extracted as a separate function so that its rendered height can be measured
    in a first pass before the enclosing SVG document dimensions are finalised
    (the two-pass approach used by _generate_fontsheet_svg with fullset=True).

    Called by:
        _generate_fontsheet_svg() when fullset=True.

    Calls:
        get_font_codepoints(), get_glyph(), get_font_metrics()
        from renderers.glyph_cache.

    Args:
        font_path:     Absolute path to the TTF/OTF font file.
        x_start:       Left margin x-coordinate in local space.
        content_width: Maximum line width before wrapping.
        font_size:     Render size in points.
        color:         SVG fill colour for all paths (e.g. ``"#222222"``).

    Returns:
        A tuple of (path_element_strings, total_rendered_height).
        Returns ([], 0.0) if the font has no mapped codepoints.
    """
    from renderers.glyph_cache import get_font_codepoints, get_glyph, get_font_metrics

    font_size_int = int(round(font_size))
    upm, _, _ = get_font_metrics(font_path)
    scale = font_size / upm
    row_h = font_size + 5

    codepoints = get_font_codepoints(font_path)
    if not codepoints:
        return [], 0.0

    x = x_start
    y = 0.0
    paths: list[str] = []

    for cp in codepoints:
        # Some mapped codepoints (control characters, unpaired combining marks)
        # cannot be laid out by PIL/raqm and raise.  Skip just that glyph —
        # letting it propagate would lose the whole font's sample instead.
        try:
            glyph = get_glyph(font_path, cp, font_size_int)
        except Exception:
            continue
        advance = glyph.advance_width if glyph.advance_width > 0 else font_size * 0.5

        # Wrap before placing if this glyph would exceed the right margin
        if x + advance > x_start + content_width and x > x_start:
            x = x_start
            y += row_h

        if glyph.path_d:
            baseline = y + font_size
            paths.append(
                f'<path d="{glyph.path_d}" fill="{color}"'
                f' transform="translate({x:.2f},{baseline:.2f})'
                f' scale({scale:.6f},{-scale:.6f})"/>'
            )
        x += advance

    total_height = y + row_h
    return paths, total_height


_FONTSHEET_PAGE_W = 1024
_FONTSHEET_TITLE_H = 60
_FONTSHEET_LABEL_H = 20
_FONTSHEET_ENTRY_PAD = 16
_FONTSHEET_COL_GAP = 32
_FONTSHEET_COLS = 2
_FONTSHEET_SAMPLE_SIZE = 16


def _render_fontsheet_page(
    fonts: list[tuple[str, str]],
    header: str,
    subtitle: str,
    cols: int,
    sample_size: int,
    color: str,
    fullset: bool,
) -> str:
    """
    Render one fontsheet page to an SVG document string.

    Shared by the single-sheet and paginated paths of
    :func:`_generate_fontsheet_svg`; see that function for the two layout modes.

    Args:
        fonts:       ``(font_name, font_path)`` pairs for this page, in order.
        header:      Sheet title drawn at the top left.
        subtitle:    Grey parenthetical after the title (font count or range).
        cols:        Entry columns (ignored in fullset mode, which is 1-column).
        sample_size: Sample text size in points.
        color:       Glyph fill colour.
        fullset:     When True, render every mapped codepoint per font.
    """
    from renderers.glyph_cache import text_to_svg_group

    SAMPLE_ROWS = [
        "abcdefghijklmnopqrstuvwxyz",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "1234567890!@#$%^&*()[]{}<>/?\\|`~",
    ]

    MARGIN = _SHEET_MARGIN
    TITLE_H = _FONTSHEET_TITLE_H
    PAGE_W = _FONTSHEET_PAGE_W
    CONTENT_W = PAGE_W - 2 * MARGIN
    SAMPLE_SIZE = max(1, sample_size)
    LABEL_H = _FONTSHEET_LABEL_H
    ROW_H = SAMPLE_SIZE + 5
    ENTRY_PAD = _FONTSHEET_ENTRY_PAD

    fonts_sorted = fonts

    # ------------------------------------------------------------------ #
    # fullset: pre-render each font's glyphs to know the entry height     #
    # ------------------------------------------------------------------ #
    if fullset:
        # Pass 1 — render and measure
        pre: list[
            tuple[str, str, list[str], float]
        ] = []  # (name, path, elems, content_h)
        for font_name, font_path in fonts_sorted:
            try:
                path_elems, content_h = _render_font_fullset(
                    font_path, MARGIN, CONTENT_W, SAMPLE_SIZE, color
                )
            except Exception:
                path_elems, content_h = [], 0.0
            pre.append((font_name, font_path, path_elems, content_h))

        # Pass 2 — compute total SVG height
        svg_h = MARGIN + TITLE_H
        for _, _, _, content_h in pre:
            svg_h += LABEL_H + max(content_h, ROW_H) + ENTRY_PAD
        svg_h += MARGIN

        lines = _sheet_header_lines(PAGE_W, svg_h, header, subtitle, title_dy=40)

        y = MARGIN + TITLE_H
        for font_name, font_path, path_elems, content_h in pre:
            entry_content_h = max(content_h, ROW_H)
            lines.append(
                f'  <line x1="{MARGIN}" y1="{y}" x2="{PAGE_W - MARGIN}" y2="{y}"'
                f' stroke="#ddd" stroke-width="1"/>'
            )
            lines.append(
                f'  <text x="{MARGIN}" y="{y + LABEL_H - 4}"'
                f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
                f' font-weight="bold" fill="#888">{font_name}</text>'
            )
            y_content = y + LABEL_H
            if path_elems:
                lines.append(f'  <g transform="translate(0,{y_content})">')
                lines.extend(f"    {p}" for p in path_elems)
                lines.append("  </g>")
            else:
                baseline = y_content + SAMPLE_SIZE
                lines.append(
                    f'  <text x="{MARGIN}" y="{baseline}"'
                    f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
                    f' fill="#ccc" font-style="italic">(no glyphs)</text>'
                )
            y += LABEL_H + entry_content_h + ENTRY_PAD

    # ------------------------------------------------------------------ #
    # default: fixed three sample rows, uniform entry height, 2 columns  #
    # ------------------------------------------------------------------ #
    else:
        COLS = max(1, cols)
        COL_GAP = _FONTSHEET_COL_GAP
        COL_W = (CONTENT_W - (COLS - 1) * COL_GAP) // COLS
        ENTRY_H = LABEL_H + 3 * ROW_H + ENTRY_PAD
        rows = (len(fonts_sorted) + COLS - 1) // COLS
        svg_h = MARGIN + TITLE_H + rows * ENTRY_H + MARGIN

        lines = _sheet_header_lines(PAGE_W, svg_h, header, subtitle, title_dy=40)

        for idx, (font_name, font_path) in enumerate(fonts_sorted):
            col = idx % COLS
            row = idx // COLS
            x_col = MARGIN + col * (COL_W + COL_GAP)
            y = MARGIN + TITLE_H + row * ENTRY_H
            x_right = x_col + COL_W
            lines.append(
                f'  <line x1="{x_col}" y1="{y}" x2="{x_right}" y2="{y}"'
                f' stroke="#ddd" stroke-width="1"/>'
            )
            lines.append(
                f'  <text x="{x_col}" y="{y + LABEL_H - 4}"'
                f' font-family="Helvetica, Arial, sans-serif" font-size="11"'
                f' font-weight="bold" fill="#888">{font_name}</text>'
            )
            y_row = y + LABEL_H
            for sample in SAMPLE_ROWS:
                baseline = y_row + SAMPLE_SIZE
                try:
                    g = text_to_svg_group(
                        sample, font_path, SAMPLE_SIZE, x_col, baseline, fill=color
                    )
                    if g:
                        lines.append(f"  {g}")
                    else:
                        lines.append(
                            f'  <text x="{x_col}" y="{baseline}"'
                            f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
                            f' fill="#ccc" font-style="italic">(no glyphs)</text>'
                        )
                except Exception:
                    lines.append(
                        f'  <text x="{x_col}" y="{baseline}"'
                        f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
                        f' fill="#bbb" font-style="italic">(not renderable)</text>'
                    )
                y_row += ROW_H

    lines.append("</svg>")
    return "\n".join(lines)


def _generate_fontsheet_svg(
    font_registry: dict,
    output_path: "Path",
    color: str = "#222222",
    title: str = "Fonts",
    fullset: bool = False,
    paginate: bool = False,
    columns: int = _FONTSHEET_COLS,
    rows: int = 10,
    cell_size: int = _FONTSHEET_SAMPLE_SIZE,
) -> list["Path"]:
    """
    Write one or more SVG sample sheets for the fonts in the registry.

    Provides visual font browsing within the ecalendar ecosystem.  This is
    important because fonts are rendered as glyph-path outlines — there is no
    browser or OS font substitution to fall back on, so choosing the right
    registered font name requires seeing how each font actually looks.

    Two rendering modes
    ───────────────────
    fullset=False (default)
        Two-column grid, uniform entry height.  Each font shows three fixed
        sample rows rendered as ``<path>`` glyph outlines via text_to_svg_group():
          - abcdefghijklmnopqrstuvwxyz
          - ABCDEFGHIJKLMNOPQRSTUVWXYZ
          - 1234567890!@#$%^&*()[]{}<>/?\\|`~

    fullset=True  (--fullset flag)
        Single column, variable entry height.  Every mapped codepoint is shown
        in codepoint order, wrapping at the right margin.  Uses a two-pass
        strategy: pass 1 calls _render_font_fullset() to measure each entry's
        height; pass 2 positions and emits them once the total SVG height is known.

    Output modes
    ────────────
    Single sheet (``paginate=False``, the default):
        Every font in one SVG written to ``output_path``.

    Paginated (``paginate=True``):
        Fonts are split into pages of at most ``columns × rows`` entries
        (``columns`` is forced to 1 in fullset mode, which is inherently a
        single column), written with a ``_pNN`` suffix before the extension; a
        single resulting page keeps the base filename.  Each page keeps *title*
        as its header but shows the page's font-name range in place of the font
        count, e.g. ``(JuliaMono to Roboto)``.

    Called by:
        run() when args.command == "fontsheet".

    Calls:
        _render_fontsheet_page() per page.

    Args:
        font_registry: Dict of ``{font_name: font_path}`` to render.
        output_path:   Destination path for the generated SVG (page suffix
                       added automatically when more than one page is produced).
        color:         Glyph fill colour (default ``"#222222"``).
        title:         SVG title string.
        fullset:       When True, renders every mapped codepoint per font.
        paginate:      When True, split fonts across ``columns × rows`` pages.
        columns:       Font columns per page when paginating (default 2).
        rows:          Font rows per page when paginating (default 10).
        cell_size:     Sample text size in points (default 16).

    Returns:
        List of ``Path`` objects actually written, in page order.
    """
    fonts_sorted = sorted(font_registry.items(), key=lambda x: x[0].lower())
    n = len(fonts_sorted)
    # fullset entries span the full content width, so they are always 1-column.
    ncols = 1 if fullset else max(1, columns)
    sample_size = max(1, cell_size)
    count_subtitle = f"({n} fonts, full glyph set)" if fullset else f"({n} fonts)"

    if not paginate:
        page = _render_fontsheet_page(
            fonts_sorted, title, count_subtitle, ncols, sample_size, color, fullset
        )
        return _write_sheet_pages(output_path, [page])

    pages = [
        _render_fontsheet_page(
            chunk,
            title,
            _range_subtitle([name for name, _ in chunk]),
            ncols,
            sample_size,
            color,
            fullset,
        )
        for chunk in _paginate_items(fonts_sorted, ncols, rows)
    ]
    return _write_sheet_pages(output_path, pages)


def _generate_iconsheet_svg(
    icons: list[dict],
    output_path: "Path",
    color: str = "#333333",
    title: str = "Icons",
    paginate: bool = False,
    columns: int = 8,
    rows: int = 10,
    cell_size: int = 24,
) -> list["Path"]:
    """
    Write one or more SVG grids of icon previews from the ``icon`` table.

    Lets users identify icon names for use in event ``Icon`` fields and
    theme hash-rules without needing to query the database directly.

    Output modes
    ────────────
    Single sheet (``paginate=False``, the default):
        Every icon is laid out in one SVG written to ``output_path``.  The
        grid is up to ``_DEFAULT_COLS`` icons wide; the header is *title*.

    Paginated (``paginate=True``):
        Icons (assumed pre-sorted by name) are split into pages of at most
        ``columns × rows`` icons so each sheet stays small enough to print.
        Pages are written with a ``_pNN`` suffix inserted before the
        extension (e.g. ``iconsheet_p01.svg``, ``iconsheet_p02.svg``); a
        single resulting page keeps the base filename.  Each page header
        shows the first and last icon name on that page, e.g.
        ``10baseT  to  C-squircle`` (no icon count is shown on paginated
        pages).

    Each cell contains the icon rendered at 24×24 with its name label below.
    Labels on odd columns are offset 12 px lower than even-column labels to
    reduce visual crowding on narrow icons.

    Colour handling — two icon styles
    ───────────────────────────────────
    Lucide-style (contains ``currentColor``):
        ``currentColor`` is replaced with *color*; the root ``fill`` attribute
        from the original ``<svg>`` element is preserved so stroked paths show.

    Klee-style (fill-based, no ``currentColor``):
        ``fill="{color}"`` is added to the container ``<svg>`` so fill-based
        paths inherit the chosen colour.

    The icon's original ``viewBox`` is preserved so internal paths render in
    their own coordinate space; ``width``/``height`` are always ``ICON_SIZE``
    so the SVG scales the content to fit the cell.

    Called by:
        run() when args.command == "iconsheet".

    Args:
        icons:       List of icon dicts with keys: name, svg (raw SVG markup).
                     Assumed already sorted by name.
        output_path: Destination path for the generated SVG (page suffix added
                     automatically when more than one page is produced).
        color:       Stroke/fill colour applied to icons (default ``"#333333"``).
        title:       SVG title string used as the header in single-sheet mode
                     (paginated headers are derived from the first/last icon
                     name on each page).
        paginate:    When True, split icons across ``columns × rows`` pages.
        columns:     Icons per row on each page when paginating (default 8).
        rows:        Rows of icons per page when paginating (default 10).
        cell_size:   Icon render box size in points (width = height); the
                     label/spacing gaps are unchanged (default 24).

    Returns:
        List of ``Path`` objects actually written, in page order.
    """
    import math
    import re

    from renderers.svg_base import BaseSVGRenderer

    MARGIN = 40
    TITLE_H = 55
    ICON_SIZE = max(1, cell_size)  # icon render box size in the sheet's space
    LABEL_H = 22
    GAP_X = 22
    GAP_Y = 19
    _DEFAULT_COLS = 12  # single-sheet grid width
    CELL_W = ICON_SIZE + GAP_X
    CELL_H = ICON_SIZE + LABEL_H + GAP_Y

    _svg_open_re = re.compile(r"<svg\b[^>]*>", re.IGNORECASE | re.DOTALL)
    _viewbox_re = re.compile(
        r'viewBox=["\'][\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)["\']', re.IGNORECASE
    )
    _preamble_re = re.compile(
        r"^(?:<\?xml\b[^?]*\?>|<!DOCTYPE\b[^>]*>|<!--.*?-->|\s)*",
        re.IGNORECASE | re.DOTALL,
    )

    def _render_page(
        page_icons: list[dict], header: str, ncols: int, show_count: bool = True
    ) -> str:
        """Render a single page of icons to an SVG document string."""
        page_n = len(page_icons)
        page_rows = math.ceil(page_n / ncols) if page_n else 1
        svg_w = MARGIN * 2 + ncols * CELL_W - GAP_X
        svg_h = MARGIN + TITLE_H + page_rows * CELL_H - GAP_Y + MARGIN

        count_tspan = (
            f'  <tspan font-size="18" font-weight="normal"'
            f' font-style="normal" fill="#666">({page_n} icons)</tspan>'
            if show_count
            else ""
        )
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}"'
            f' viewBox="0 0 {svg_w} {svg_h}">',
            f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
            f'  <text x="{MARGIN}" y="{MARGIN + 36}"'
            f' font-family="Helvetica, Arial, sans-serif"'
            f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
            f"{_xml_escape(header)}{count_tspan}</text>",
        ]

        for i, row in enumerate(page_icons):
            r = i // ncols
            col = i % ncols
            x = MARGIN + col * CELL_W
            y = MARGIN + TITLE_H + r * CELL_H

            name = str(row.get("name") or "").strip()
            svg_raw = _preamble_re.sub("", str(row.get("svg") or "").strip())

            # Replace currentColor with chosen stroke color (Lucide-style icons).
            uses_current_color = "currentColor" in svg_raw
            svg_colored = svg_raw.replace("currentColor", color)

            # Extract the icon's original viewBox so its internal paths render in
            # their own coordinate space.  width/height are always set to
            # ICON_SIZE so the SVG scales the content to fit the cell regardless
            # of whether the icon uses a 24- or 48-unit coordinate system.
            vb_match = _viewbox_re.search(svg_raw)
            vb = (
                f"0 0 {vb_match.group(1)} {vb_match.group(2)}"
                if vb_match
                else "0 0 24 24"
            )

            # Determine how to apply color on the container SVG:
            #   - Lucide-style: uses currentColor → already replaced above;
            #     preserve the original root fill (typically "none") so stroked
            #     paths show.
            #   - Klee-style: no currentColor, fill-based paths with no explicit
            #     fill → set fill on the container so paths inherit the colour.
            if uses_current_color:
                orig_fill_match = re.search(
                    r"<svg\b[^>]*\bfill=[\"']([^\"']*)[\"']",
                    svg_raw,
                    re.IGNORECASE | re.DOTALL,
                )
                color_attr = (
                    f' fill="{orig_fill_match.group(1)}"' if orig_fill_match else ""
                )
            else:
                color_attr = f' fill="{color}"'

            embedded = _svg_open_re.sub(
                f'<svg x="{x}" y="{y}" width="{ICON_SIZE}" height="{ICON_SIZE}"'
                f' viewBox="{vb}"{color_attr}'
                f' xmlns="http://www.w3.org/2000/svg">',
                svg_colored,
                count=1,
            )

            # Strip comments, collapse whitespace, and truncate long fractional
            # coordinates so the sheet stays small (path data dominates size).
            embedded = BaseSVGRenderer._minify_svg_markup(embedded)

            lines.append(f"  {embedded}")

            # Alternate label Y by column so adjacent labels are staggered and
            # do not overlap each other.
            label_y = y + ICON_SIZE + 5 + (12 if col % 2 else 0)

            lines.append(
                f'  <text x="{x + ICON_SIZE // 2}" y="{label_y}"'
                f' font-family="Helvetica, Arial, sans-serif" font-size="9"'
                f' fill="#555" text-anchor="middle">{_xml_escape(name)}</text>'
            )

        lines.append("</svg>")
        return "\n".join(lines)

    n = len(icons)

    # Single-sheet mode (default): one SVG holding every icon.
    if not paginate:
        ncols = min(n, _DEFAULT_COLS) if n else 1
        return _write_sheet_pages(output_path, [_render_page(icons, title, ncols)])

    # Paginated mode: split icons across columns × rows pages.
    ncols = max(1, columns)
    pages: list[str] = []
    for page_icons in _paginate_items(icons, ncols, rows):
        if page_icons:
            first_name = str(page_icons[0].get("name") or "").strip()
            last_name = str(page_icons[-1].get("name") or "").strip()
            header = (
                first_name
                if first_name == last_name
                else f"{first_name}  to  {last_name}"
            )
        else:
            header = title
        pages.append(_render_page(page_icons, header, ncols, show_count=False))

    return _write_sheet_pages(output_path, pages)


def _generate_patternsheet_svg(
    patterns: list[tuple[str, str]],
    output_path: "Path",
    color: str = "#333333",
    title: str = "Patterns",
) -> None:
    """
    Write an SVG grid preview of day-box patterns from the database.

    Each cell shows a swatch filled with the pattern (tiled at its native
    size) plus the pattern name as a label below.  Lets users identify
    pattern names for use in theme ``day_box.hash_pattern`` and per-rule
    ``hash_rules[].pattern`` fields without querying the database directly.

    Pattern colorization mirrors the weekly renderer: black fills
    (``#000000``, ``#000``, ``black``) in the source SVG are replaced with
    *color* before the tile is embedded in a ``<pattern>`` element in
    ``<defs>``.  Each cell is then a ``<rect fill="url(#pat-id)">`` covering
    the swatch area.

    Called by:
        run() when args.command == "patternsheet".

    Args:
        patterns:    List of (name, svg) tuples (raw SVG markup).
        output_path: Destination path for the generated SVG.
        color:       Fill color applied to pattern tiles (default ``"#333333"``).
        title:       SVG title string.
    """
    import math

    from renderers.svg_base import BaseSVGRenderer
    from renderers.svg_patterns import (
        colorize_pattern_svg,
        extract_pattern_inner,
        parse_svg_tile_size,
        pattern_def_id,
    )

    MARGIN = 40
    TITLE_H = 55
    SWATCH_SIZE = 120
    LABEL_H = 22
    GAP_X = 22
    GAP_Y = 22
    MAX_COLS = 6
    CELL_W = SWATCH_SIZE + GAP_X
    CELL_H = SWATCH_SIZE + LABEL_H + GAP_Y

    n = len(patterns)
    ncols = min(n, MAX_COLS) if n else 1
    nrows = math.ceil(n / ncols) if n else 1
    svg_w = MARGIN * 2 + ncols * CELL_W - GAP_X
    svg_h = MARGIN + TITLE_H + nrows * CELL_H - GAP_Y + MARGIN

    defs: list[str] = []
    body: list[str] = []
    seen_ids: set[str] = set()

    for i, (name, raw_svg) in enumerate(patterns):
        r = i // ncols
        col = i % ncols
        x = MARGIN + col * CELL_W
        y = MARGIN + TITLE_H + r * CELL_H

        pat_id = pattern_def_id(name, color)

        if pat_id not in seen_ids:
            tile_w, tile_h = parse_svg_tile_size(raw_svg)
            colorized = colorize_pattern_svg(raw_svg, color)
            inner = extract_pattern_inner(colorized)

            # Scale oversized tiles down so at least one full tile fits inside
            # the swatch.  Wrap the tile content in a <g transform="scale(s)">
            # and shrink the pattern's reported tile size by the same factor
            # so the pattern still tiles correctly across the swatch.
            scale = (
                min(1.0, SWATCH_SIZE / max(tile_w, tile_h))
                if max(tile_w, tile_h) > 0
                else 1.0
            )
            if scale < 1.0:
                inner = f'<g transform="scale({scale})">{inner}</g>'
                tile_w *= scale
                tile_h *= scale

            inner = BaseSVGRenderer._minify_svg_markup(inner)
            defs.append(
                f'    <pattern id="{pat_id}" x="0" y="0"'
                f' width="{tile_w}" height="{tile_h}"'
                f' patternUnits="userSpaceOnUse">{inner}</pattern>'
            )
            seen_ids.add(pat_id)

        body.append(
            f'  <rect x="{x}" y="{y}" width="{SWATCH_SIZE}" height="{SWATCH_SIZE}"'
            f' fill="white" stroke="#cccccc" stroke-width="1"/>'
        )
        body.append(
            f'  <rect x="{x}" y="{y}" width="{SWATCH_SIZE}" height="{SWATCH_SIZE}"'
            f' fill="url(#{pat_id})"/>'
        )

        label_y = y + SWATCH_SIZE + 14
        body.append(
            f'  <text x="{x + SWATCH_SIZE // 2}" y="{label_y}"'
            f' font-family="Helvetica, Arial, sans-serif" font-size="10"'
            f' fill="#555" text-anchor="middle">{name}</text>'
        )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' xmlns:xlink="http://www.w3.org/1999/xlink"'
        f' width="{svg_w}" height="{svg_h}"'
        f' viewBox="0 0 {svg_w} {svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>',
        "  <defs>",
        *defs,
        "  </defs>",
        f'  <text x="{MARGIN}" y="{MARGIN + 36}"'
        f' font-family="Helvetica, Arial, sans-serif"'
        f' font-size="26" font-weight="bold" font-style="italic" fill="#222">'
        f'{title}  <tspan font-size="18" font-weight="normal" font-style="normal"'
        f' fill="#666">({n} patterns)</tspan></text>',
        *body,
        "</svg>",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

