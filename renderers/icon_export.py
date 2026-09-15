"""
Icon files for a run: one uniform-size SVG per icon or mark the chart drew.

Each distinct ``(icon, color)`` the render record holds becomes
``icons/<icon>--<color>.svg`` in the run folder.  Every file is the same
square size, and a DB icon is wrapped exactly the way
:meth:`renderers.svg_base.BaseSVGRenderer._draw_icon_svg` nests it in the
chart -- same viewBox handling, same recoloring -- so the file shows what
the chart shows.  Marks (a color swatch, a milestone flag, a bar) have no
icon behind them and are drawn here.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from html import escape
from typing import TYPE_CHECKING

from renderers.details_record import MARK_PREFIX, IconUse
from shared.run_paths import slugify

if TYPE_CHECKING:
    from shared.run_paths import RunPaths

_SVG_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_VIEWBOX_RE = re.compile(r'viewBox=["\'][\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)["\']', re.IGNORECASE)

#: Paint for a mark recorded without a color.
_NEUTRAL = "#808080"


def minify_svg_markup(markup: str) -> str:
    """Strip comments and collapse whitespace in SVG markup.

    Safe for icon and pattern fragments, which carry no significant text
    nodes.
    """
    markup = _SVG_COMMENT_RE.sub("", markup)
    markup = re.sub(r">\s+<", "><", markup)
    markup = re.sub(r"\s+", " ", markup)
    return markup.strip()


def strip_svg_wrapper(svg_markup: str) -> str:
    """Return minified inner SVG content without XML/DOCTYPE/<svg> wrapper."""
    inner = re.sub(r"<\?xml[^>]*\?>", "", svg_markup, flags=re.IGNORECASE)
    inner = re.sub(r"<!DOCTYPE[^>]*>", "", inner, flags=re.IGNORECASE)
    inner = re.sub(r"<svg[^>]*>", "", inner, count=1, flags=re.IGNORECASE)
    if "</svg>" in inner:
        inner = inner.rsplit("</svg>", 1)[0]
    return minify_svg_markup(inner)


def icon_viewbox(svg_markup: str) -> str:
    """The icon's own coordinate space, from its root viewBox."""
    match = _VIEWBOX_RE.search(svg_markup)
    return f"0 0 {match.group(1)} {match.group(2)}" if match else "0 0 24 24"


def icon_color_style(color: str | None) -> str:
    """The style attribute that paints an icon in *color*."""
    return f' style="color:{color};stroke:{color};fill:{color};"' if color else ""


def icon_filename(use: IconUse) -> str:
    """``diamond-fill--1f77b4.svg``: the icon, then the color it was drawn in."""
    color = slugify(str(use.color).lstrip("#"), fallback="native") if use.color else "native"
    return f"{slugify(use.icon)}--{color}.svg"


def _size_text(size: float) -> str:
    return f"{float(size):g}"


def _document(size: float, body: str) -> str:
    s = _size_text(size)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{s}" height="{s}" viewBox="0 0 {s} {s}">{body}</svg>\n'
    )


def icon_file_svg(markup: str, color: str | None, size: float) -> str:
    """A DB icon as a standalone *size* × *size* SVG, colored as drawn."""
    s = _size_text(size)
    style = icon_color_style(escape(color, quote=True) if color else None)
    inner = strip_svg_wrapper(markup)
    body = (
        f'<svg x="0" y="0" width="{s}" height="{s}" viewBox="{icon_viewbox(markup)}" '
        f'preserveAspectRatio="xMidYMid meet"{style}>{inner}</svg>'
    )
    return _document(size, body)


def mark_file_svg(kind: str, color: str | None, size: float) -> str:
    """A mark drawn as a standalone *size* × *size* SVG."""
    paint = escape(color or _NEUTRAL, quote=True)
    u = float(size) / 16.0  # drawn on a 16-unit grid

    def n(value: float) -> str:
        return f"{value * u:g}"

    if kind == "flag":
        body = (
            f'<line x1="{n(4)}" y1="{n(2)}" x2="{n(4)}" y2="{n(14)}" stroke="{paint}" stroke-width="{n(1.5)}"/>'
            f'<polygon points="{n(4)},{n(2)} {n(14)},{n(5)} {n(4)},{n(8)}" fill="{paint}"/>'
        )
    elif kind == "diamond":
        body = f'<polygon points="{n(8)},{n(2)} {n(14)},{n(8)} {n(8)},{n(14)} {n(2)},{n(8)}" fill="{paint}"/>'
    elif kind == "bracket":
        body = (
            f'<polyline points="{n(1)},{n(11)} {n(1)},{n(5)} {n(15)},{n(5)} {n(15)},{n(11)}" '
            f'fill="none" stroke="{paint}" stroke-width="{n(1.5)}"/>'
        )
    elif kind == "dot":
        body = f'<circle cx="{n(8)}" cy="{n(8)}" r="{n(5)}" fill="{paint}"/>'
    elif kind == "fill":
        body = f'<rect x="{n(1)}" y="{n(1)}" width="{n(14)}" height="{n(14)}" fill="{paint}"/>'
    elif kind == "bar":
        body = f'<rect x="0" y="{n(5)}" width="{n(16)}" height="{n(6)}" rx="{n(1)}" fill="{paint}"/>'
    else:  # swatch, and any kind this module does not know
        body = f'<rect x="{n(1)}" y="{n(4)}" width="{n(14)}" height="{n(8)}" rx="{n(1)}" fill="{paint}"/>'
    return _document(size, body)


def export_icons(
    uses: Iterable[IconUse],
    run_paths: RunPaths,
    size: float,
    resolve_markup: Callable[[str], str | None] | None,
) -> dict[IconUse, str]:
    """Write every icon file; returns each use's path relative to the run folder.

    A use whose DB icon cannot be resolved is left out of the result, so
    the document names it rather than linking a file that does not exist.
    """
    written: dict[str, str] = {}
    paths: dict[IconUse, str] = {}
    for use in uses:
        filename = icon_filename(use)
        if filename not in written:
            if use.icon.startswith(MARK_PREFIX):
                content = mark_file_svg(use.icon[len(MARK_PREFIX) :], use.color, size)
            else:
                markup = resolve_markup(use.icon) if resolve_markup is not None else None
                if not markup:
                    continue
                content = icon_file_svg(markup, use.color, size)
            target = run_paths.icon(filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written[filename] = f"{target.parent.name}/{target.name}"
        paths[use] = written[filename]
    return paths
