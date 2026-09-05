"""
Timeline SVG renderer.

Renders a horizontal, date-scaled timeline with distinct point-event callouts
and duration bars aligned to start/end dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

from datetime import date

import arrow
import drawsvg

from config.config import get_font_path, resolve_continuation_icon
from renderers.glyph_cache import get_ink_extents
from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import shrinktext, string_width
from shared.data_models import Event
from shared.date_utils import format_arrow_date
from shared.rule_engine import StyleEngine, StyleResult
from shared.wbs_filter import wbs_group, wbs_sort_key
from shared.day_classifier import classify_day
from shared.icon_band import compute_icon_band_days
from shared.timeband import build_segments as _build_band_segments
from visualizers.timeline.labella_adapter import (
    CalloutPlacement,
    callout_date_extent,
    layout_callouts as _labella_layout_callouts,
)
from shared.orientation import Orientation, Side

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict

#: Breathing room between the top of the axis tick labels and the innermost
#: row of callout boxes.
_AXIS_LABEL_MARGIN = 2.0


def _timeline_style_rules(config: "CalendarConfig") -> list:
    """Source the raw style_rules list for StyleEngine.

    Prefers the parsed UnifiedTheme (``config.theme``) so the renderer no
    longer depends on the legacy ``theme_style_rules`` decompiler bridge.
    Mirrors compactplan / weekly / blockplan / mini-day_styles.
    """
    theme = getattr(config, "theme", None)
    if theme is not None:
        rules = theme.sections.get("style_rules")
        if isinstance(rules, list):
            return rules
    return list(getattr(config, "theme_style_rules", None) or [])


@dataclass(frozen=True)
class TimelineCallout:
    """Point-in-time event callout placement.

    Coordinates are absolute SVG (Y-down). `x_dot` / `y_dot` mark the
    location of the dot on the axis line where the leader originates;
    `box_*` give the label rectangle. `leader_path_d` is labella's bezier
    `d` attribute in *axis-local* coordinates — it pairs with `axis_origin`
    via a `<g transform="translate(ox,oy)">` wrapper when emitted.
    """

    event: Event
    color: str
    # Dot on the axis line (leader origin).
    x_dot: float
    y_dot: float
    # Label box.
    lane: int
    box_x: float
    box_y: float
    box_width: float
    box_height: float
    # Labella leader. Empty string is permitted for fallback paths.
    leader_path_d: str = ""
    axis_origin: tuple[float, float] = (0.0, 0.0)
    orientation: Orientation = Orientation.HORIZONTAL
    style: StyleResult | None = None

    @property
    def x(self) -> float:
        """Backwards-compat alias for the dot x position (used by older
        renderer code paths that pre-date the orientation refactor)."""
        return self.x_dot


@dataclass(frozen=True)
class TimelineDuration:
    """Duration bar placement alongside the timeline axis.

    For HORIZONTAL orientation: `start_x`/`end_x` are the bar endpoints
    along the axis, and `lane` stacks downward below the axis.

    For VERTICAL orientation: `start_y`/`end_y` are the bar endpoints
    along the axis, `start_x`/`end_x` both equal the axis x position,
    and `lane` stacks to the LEFT of the axis (secondary side).
    `continues_left` / `continues_right` map to "continues past the top"
    / "continues past the bottom" respectively.
    """

    event: Event
    color: str
    start_x: float
    end_x: float
    lane: int
    min_width: float
    continues_left: bool = False
    continues_right: bool = False
    style: StyleResult | None = None
    orientation: Orientation = Orientation.HORIZONTAL
    start_y: float = 0.0
    end_y: float = 0.0
    # Which side of the axis this bar sits on (vertical orientation only;
    # ignored for horizontal). PRIMARY = right, SECONDARY = left.
    lane_side: Side = Side.SECONDARY


#: Air kept above the title's ink and below the notes' ink inside a callout.
_CALLOUT_PAD_Y: float = 1.5

#: Space between the title's descenders and the notes' ascenders.
_CALLOUT_LINE_GAP: float = 1.0

#: Inset from a duration bar's edge to its in-bar start / end date.
_DURATION_DATE_PAD_X: float = 3.0

#: Clear space kept between an in-bar date and the bar's title.
_DURATION_DATE_GAP_X: float = 4.0


class TimelineRenderer(BaseSVGRenderer):
    """Renderer for timeline visualization."""

    # Tokens pre-resolved once per render; see BaseSVGRenderer._populate_tokens.
    TOKEN_VISUALIZER = "timeline"
    TOKENS = (
        "text:event_name", "text:event_notes", "text:event_date",
        "text:duration_date", "text:label", "text:today_label",
        "line:axis", "line:today", "line:tick", "line:duration_bar",
        "icon:event", "icon:milestone",
    )

    # NOTE: ``_callout_metrics`` is defined near the bottom of the file.
    # An earlier duplicate definition existed at this point pre-migration
    # (Python silently used the last one); removed during this migration
    # so the token-aware version is the single source of truth.

    @staticmethod
    def _ink_extents_pt(font_path: str | None, size: float) -> tuple[float, float]:
        """Ink height above and below the baseline, in points."""
        if not font_path or size <= 0:
            return size * 0.75, size * 0.22
        ascent, descent = get_ink_extents(font_path)
        return ascent * size, descent * size

    @classmethod
    def _callout_text_geometry(
        cls,
        box_height: float,
        title_size: float,
        notes_size: float,
        title_font_path: str | None,
        notes_font_path: str | None,
        has_notes: bool,
    ) -> tuple[float, float, float]:
        """Vertical layout of a callout box's text.

        Returns ``(title_dy, notes_dy, required_height)`` — the two baselines
        as offsets from the box top, and the height the block needs.

        One function serves both the fitter and the drawing pass on purpose.
        They used to carry separate formulas — the fitter allowed
        ``1.2 * title + 1.2 * notes + 2``, the renderer drew the notes
        baseline at ``1.15 * title + 1.55 * notes`` and counted no descender
        at all — so a box the fitter called a fit still hung the notes'
        descenders up to 1.9pt below its bottom edge.

        Extents come from the glyph outlines rather than the OS/2 typo
        metrics, which are line-spacing advice and overstate the ink badly
        for some fonts (see :func:`renderers.glyph_cache.get_ink_extents`).
        """
        title_ascent, title_descent = cls._ink_extents_pt(
            title_font_path, title_size
        )
        if has_notes:
            notes_ascent, notes_descent = cls._ink_extents_pt(
                notes_font_path, notes_size
            )
            gap = _CALLOUT_LINE_GAP
        else:
            notes_ascent = notes_descent = gap = 0.0

        block_h = (
            title_ascent + title_descent + gap + notes_ascent + notes_descent
        )
        # Centre the block, so a box taller than its text does not strand the
        # lines against the top edge. The clamp keeps the title inside its
        # padding when the box is too short for the block to fit at all.
        top = max(_CALLOUT_PAD_Y, (box_height - block_h) / 2.0)
        title_dy = top + title_ascent
        # With no notes there is no second baseline; returning the title's
        # keeps a caller that ignores ``has_notes`` from drawing below the ink.
        notes_dy = (
            title_dy + title_descent + gap + notes_ascent
            if has_notes
            else title_dy
        )
        return title_dy, notes_dy, block_h + (2.0 * _CALLOUT_PAD_Y)

    @classmethod
    def _fit_box_text_sizes(
        cls,
        text: str,
        notes: str,
        text_width: float,
        box_height: float,
        title_font_path: str | None,
        notes_font_path: str | None,
        title_size: float,
        notes_size: float,
        notes_width: float | None = None,
        height_for: "Callable[[float, float, bool], float] | None" = None,
    ) -> tuple[float, float]:
        """Shrink title/notes fonts to fit a constrained box width and height.

        ``notes_width`` is the width available to the notes line when it
        differs from the title's — inside a callout the title shares its line
        with the icon and the date, and the notes line has the box to itself.
        Measuring both against the title's narrower budget shrank the notes
        to clear space they were never drawn near. Defaults to
        ``text_width``.

        ``height_for`` supplies the height model, so the caller that draws the
        text is the one that decides how much room it needs; the default is
        the flat 1.2-per-line box the duration bars lay out with.
        """
        width = max(8.0, text_width)
        n_width = max(8.0, text_width if notes_width is None else notes_width)
        tsize = shrinktext(text, width, title_font_path, title_size)
        nsize = (
            shrinktext(notes, n_width, notes_font_path, notes_size)
            if notes
            else notes_size
        )

        def default_height(ts: float, ns: float, has: bool) -> float:
            # ~1.2 line height per row plus a small inner padding. The earlier
            # 1.9/1.7 multipliers were generous and caused declared font sizes
            # to be shrunk well below the box's actual capacity.
            return ts * 1.2 + ((ns * 1.2) if has else 0.0) + 2.0

        required_h = height_for or default_height

        has_notes = bool(notes)
        need = required_h(tsize, nsize, has_notes)
        if box_height > 0 and need > box_height:
            # Scale down first, then tighten iteratively if still too tall.
            factor = max(0.35, box_height / need)
            tsize = max(6.0, tsize * factor)
            if has_notes:
                nsize = max(5.0, nsize * factor)
            tsize = shrinktext(text, width, title_font_path, tsize)
            if has_notes:
                nsize = shrinktext(notes, n_width, notes_font_path, nsize)
            guard = 0
            while required_h(tsize, nsize, has_notes) > box_height and guard < 30:
                tsize = max(6.0, tsize - 0.2)
                if has_notes:
                    nsize = max(5.0, nsize - 0.2)
                guard += 1

        return tsize, nsize

    def _create_drawing(self, config: "CalendarConfig") -> drawsvg.Drawing:
        drawing = super()._create_drawing(config)
        bg_style = config.get_box_style("ec-background")
        bg = str(bg_style.fill or "").strip().lower()
        if bg not in {"", "none", "transparent"}:
            drawing.append(
                drawsvg.Rectangle(
                    0,
                    0,
                    round(config.pageX, 2),
                    round(config.pageY, 2),
                    fill=bg_style.fill,
                )
            )
        return drawing

    def _render_content(
        self,
        config: "CalendarConfig",
        coordinates: "CoordinateDict",
        events: list,
        db: "CalendarDB",
    ) -> tuple[int, list]:
        """Assemble the timeline page for either axis orientation.

        Sequence: compute axis geometry (horizontal or vertical) →
        labella callout layout for point events (`_layout_callouts`) and
        lane layout for durations → draw in layers: leader paths first
        (under everything), then durations, callout boxes, the axis with
        ticks/timebands, and finally the today marker.  Returns
        ``(0, [])`` — the timeline never overflows; density is labella's
        problem, not pagination's.
        """
        area_x, area_y, area_w, area_h = coordinates.get(
            "TimelineArea", (0.0, 0.0, config.pageX, config.pageY)
        )

        # Timeline is a continuous time axis — use the user-typed range so the
        # axis edges match the requested dates exactly. Fall back to the
        # weekend-style-adjusted range only when no user range was captured.
        user_start_str = getattr(config, "userstart", None) or config.adjustedstart
        user_end_str = getattr(config, "userend", None) or config.adjustedend
        start = arrow.get(user_start_str, "YYYYMMDD")
        end = arrow.get(user_end_str, "YYYYMMDD")
        if end < start:
            start, end = end, start

        orient = Orientation(config.timeline_orientation)
        label_side = Side(config.timeline_label_side)

        # Reserve room for top/bottom timebands only on horizontal axes —
        # timebands above/below a vertical axis are not supported in this
        # release and would land on top of the axis. The config fields
        # still parse, but they no-op for vertical.
        if orient is Orientation.HORIZONTAL:
            top_bands = list(getattr(config, "timeline_top_time_bands", None) or [])
            bottom_bands = list(getattr(config, "timeline_bottom_time_bands", None) or [])
        else:
            top_bands = []
            bottom_bands = []
        top_bands_h = sum(float(b.get("row_height", 14.0)) for b in top_bands)
        bottom_bands_h = sum(float(b.get("row_height", 14.0)) for b in bottom_bands)

        event_objs = [Event.from_dict(e) for e in events]
        self._load_icon_svg_cache(db)
        self._populate_tokens(config)
        point_events, duration_events = self._split_events(config, event_objs)
        style_engine = StyleEngine(_timeline_style_rules(config))
        # One color per WBS group for the whole chart, so a phase's events,
        # milestones and bars match instead of each layout cycling its own
        # palette independently.
        group_colors = self._wbs_group_colors(
            config, list(point_events) + list(duration_events)
        )

        # Compute the axis geometry for the chosen orientation. axis_origin
        # is the (x, y) where the 1-D idealPos=0 maps in absolute SVG. For
        # horizontal this is the left end of the axis; for vertical, the
        # top end. axis_length is the extent along the axis.
        if orient is Orientation.HORIZONTAL:
            axis_left = area_x + (area_w * 0.04)
            axis_right = area_x + (area_w * 0.96)
            inner_y = area_y + top_bands_h
            inner_h = max(1.0, area_h - top_bands_h - bottom_bands_h)
            if getattr(config, "includeevents", True):
                axis_y = inner_y + (inner_h * 0.44)
            else:
                tick_clearance = self._tick_label_top_clearance(
                    config, getattr(config, "timeline_ticks", None)
                )
                axis_y = inner_y + tick_clearance + 4.0
            axis_origin = (axis_left, axis_y)
            axis_length = axis_right - axis_left
            # End-of-axis coordinates for the line draw and downstream uses.
            axis_end = (axis_right, axis_y)
        else:
            axis_top = area_y + (area_h * 0.04)
            axis_bottom = area_y + (area_h * 0.96)
            # Pick the axis x so each populated side has room. With events
            # visible, callouts dominate the layout: keep the 44% bias that
            # leaves a wider right-hand label column. With --noevents the
            # only horizontal content is duration lanes, so center the axis
            # when bars go on both sides (label_side=both), push it right
            # when bars only go left (secondary), and keep it near the left
            # margin otherwise.
            if getattr(config, "includeevents", True):
                axis_x = area_x + (area_w * 0.44)
            elif label_side is Side.BOTH:
                axis_x = area_x + (area_w * 0.50)
            elif label_side is Side.SECONDARY:
                axis_x = area_x + (area_w * 0.90)
            else:
                axis_x = area_x + (area_w * 0.10)
            axis_origin = (axis_x, axis_top)
            axis_length = axis_bottom - axis_top
            axis_end = (axis_x, axis_bottom)
            # Legacy locals so the horizontal-only feature blocks below can
            # safely no-op when checked.
            axis_left = axis_x
            axis_right = axis_x
            axis_y = axis_top

        # Room one side of the axis has for its stack of callout rows. The
        # axis sits at 44% of the content area, so the near side is the
        # smaller of the two — using it bounds both sides safely.
        # A box stroked exactly on the page edge loses half its border to
        # the clip, so the bounds are inset by half the stroke.
        _edge_inset = config.get_box_style("ec-callout-box").stroke_width / 2.0
        if orient is Orientation.HORIZONTAL:
            callout_room = max(0.0, axis_y - (area_y + top_bands_h))
            label_bounds = (area_x + _edge_inset, area_x + area_w - _edge_inset)
        else:
            callout_room = max(0.0, axis_origin[0] - area_x)
            label_bounds = (area_y + _edge_inset, area_y + area_h - _edge_inset)

        callouts = self._layout_callouts(
            config,
            point_events,
            start,
            end,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orient,
            side=label_side,
            # Rows past the edge of the drawable area carry labels nobody
            # can read, so the layout stops buying them there.
            max_extent=callout_room,
            # A box that runs off the paper is a box the reader loses the
            # end of, so placement is bounded by the page, not the axis.
            label_bounds=label_bounds,
            group_colors=group_colors,
            style_engine=style_engine,
        )
        if orient is Orientation.HORIZONTAL:
            durations = self._layout_durations(
                config,
                duration_events,
                start,
                end,
                axis_left,
                axis_right,
                axis_y,
                style_engine,
                group_colors=group_colors,
            )
        else:
            durations = self._layout_durations_vertical(
                config,
                duration_events,
                start,
                end,
                axis_x=axis_origin[0],
                axis_top=axis_origin[1],
                axis_bottom=axis_end[1],
                side=label_side,
                style_engine=style_engine,
                group_colors=group_colors,
            )

        # Pass 1: emit labella's curved bezier leader paths under everything
        # else. Each path is in axis-local coordinates; we wrap it in a
        # translate() transform that places idealPos=0 at axis_origin.
        leader_style = config.get_line_style("ec-callout-leader")
        leader_stroke_width = leader_style.width or 1.25
        leader_opacity = leader_style.opacity or 0.75
        leader_dasharray = (
            leader_style.dasharray
            or config.timeline_connector_stroke_dasharray
            or None
        )
        ox, oy = axis_origin
        for callout in callouts:
            if not callout.leader_path_d:
                continue
            dash_attr = (
                f' stroke-dasharray="{leader_dasharray}"'
                if leader_dasharray else ""
            )
            self._drawing.append(drawsvg.Raw(
                f'<g transform="translate({ox:.2f},{oy:.2f})" '
                f'class="ec-callout-leader">'
                f'<path d="{callout.leader_path_d}" '
                f'stroke="{callout.color}" stroke-width="{leader_stroke_width}" '
                f'stroke-opacity="{leader_opacity}" fill="none"{dash_attr}/>'
                f'</g>'
            ))
        # How far the duration band may reach before it leaves the paper.
        # None under --shrink: the viewBox is grown to whatever the bars
        # need, so every lane is drawn however deep the stack goes.
        if config.shrink_to_content:
            duration_limit = None
            room_primary = room_secondary = None
        elif orient is Orientation.HORIZONTAL:
            duration_limit = area_y + area_h - bottom_bands_h
            room_primary = room_secondary = None
        else:
            # Vertical bars fan out on both sides of the axis, and the axis
            # is not centred, so each side is measured against its own room.
            duration_limit = None
            room_primary = max(0.0, area_x + area_w - axis_origin[0])
            room_secondary = max(0.0, axis_origin[0] - area_x)

        def _vertical_room(item: TimelineDuration) -> float | None:
            if config.shrink_to_content:
                return None
            return (
                room_primary
                if item.lane_side is Side.PRIMARY
                else room_secondary
            )

        if orient is Orientation.HORIZONTAL:
            for duration in durations:
                self._draw_duration_connectors(
                    config, duration, axis_y, duration_limit
                )
        else:
            for duration in durations:
                self._draw_duration_connectors_vertical(
                    config, duration, axis_origin[0], _vertical_room(duration)
                )

        # Main axis line. Vertical orientation: line runs (axis_x, axis_top)
        # → (axis_x, axis_bottom).
        _axis_style = config.get_line_style("ec-axis-line")
        self._draw_line(
            axis_origin[0],
            axis_origin[1],
            axis_end[0],
            axis_end[1],
            stroke=_axis_style.color,
            stroke_width=_axis_style.width,
            stroke_opacity=_axis_style.opacity,
            stroke_dasharray=_axis_style.dasharray or None,
            css_class="ec-axis-line",
        )

        # Tick/today/fiscal/holiday/timeband features below remain
        # horizontal-only in this release. They are skipped on vertical
        # axes (otherwise the date-format text would write atop the
        # vertical axis line). Vertical falls through to the shared
        # callout-drawing pass below.
        _horizontal = orient is Orientation.HORIZONTAL

        if _horizontal:
            tick_bands_cfg = getattr(config, "timeline_ticks", None)
            if tick_bands_cfg:
                tick_bands = (
                    [tick_bands_cfg] if isinstance(tick_bands_cfg, dict) else list(tick_bands_cfg)
                )
                # Precompute ticks per band so labels can be deduplicated when
                # bands collide on the same day. The band whose unit covers the
                # largest number of days (e.g. month > week > day) wins the label.
                band_ticks: list[list[tuple]] = []
                band_priorities: list[int] = []
                for tb in tick_bands:
                    if not isinstance(tb, dict):
                        band_ticks.append([])
                        band_priorities.append(-1)
                        continue
                    band_ticks.append(
                        self._compute_band_ticks(config, tb, start, end, db)
                    )
                    band_priorities.append(self._tick_unit_priority(tb))
                # Per-date max priority across bands. Equal-priority bands ticking
                # on the same date all draw their labels (each sits on its own
                # label row via label_gap/label_offset_y); only strictly lower
                # priority bands are suppressed.
                max_prio: dict = {}
                for idx, ticks in enumerate(band_ticks):
                    prio = band_priorities[idx]
                    for tick_date, _label in ticks:
                        if tick_date not in max_prio or max_prio[tick_date] < prio:
                            max_prio[tick_date] = prio
                for idx, tb in enumerate(tick_bands):
                    if not isinstance(tb, dict):
                        continue
                    prio = band_priorities[idx]
                    allowed = {
                        d for d, _l in band_ticks[idx] if max_prio.get(d) == prio
                    }
                    self._draw_axis_ticks_from_band(
                        config, tb, start, end, axis_left, axis_right, axis_y, db,
                        ticks=band_ticks[idx],
                        allowed_label_dates=allowed,
                    )
            else:
                self._draw_month_ticks(config, start, end, axis_left, axis_right, axis_y)
            if config.fiscal_lookup and (
                config.timeline_show_fiscal_periods or config.timeline_show_fiscal_quarters
            ):
                self._draw_fiscal_bands(config, start, end, axis_left, axis_right, axis_y)
            self._draw_today_marker(
                config,
                start,
                end,
                axis_left,
                axis_right,
                axis_y,
                area_y,
                area_h,
            )

            # Government holiday icons sit between the axis line and the duration
            # bars (the duration offset already reserves enough vertical space).
            if getattr(config, "timeline_show_holiday_icons", True):
                self._draw_holiday_icons(
                    config, start, end, axis_left, axis_right, axis_y, db
                )

        # Pass 2: draw all boxes, markers, and text on top.
        for callout in callouts:
            self._draw_callout(config, callout, axis_y)
        for duration in durations:
            if duration.orientation is Orientation.VERTICAL:
                self._draw_duration_vertical(
                    config, duration, axis_origin[0], _vertical_room(duration)
                )
            else:
                self._draw_duration(config, duration, axis_y, duration_limit)

        # Timebands: top bands stack above the timeline area; bottom bands
        # stack below it. Only drawn when declared in the theme.
        if top_bands:
            self._draw_timeline_bands(
                config, top_bands, area_y, axis_left, axis_right, start, end, db,
                events=event_objs,
            )
        if bottom_bands:
            self._draw_timeline_bands(
                config,
                bottom_bands,
                area_y + area_h - bottom_bands_h,
                axis_left,
                axis_right,
                start,
                end,
                db,
                events=event_objs,
            )

        # After all content is laid out, tighten the SVG viewBox to the actual
        # rendered extent. _shrink_drawing_to_content() runs before
        # _render_content() and uses only the coordinate dict, so it cannot see
        # the dynamic callout / duration row positions computed here. Override
        # the viewBox directly now that all bounds are known.
        if config.shrink_to_content:
            tight = self._actual_content_bounds(
                config,
                callouts,
                durations,
                axis_left,
                axis_right,
                axis_y,
                area_x,
                area_y,
                area_w,
                area_h,
            )
            coordinates["TimelineArea"] = tight
            tx, ty, tw, th = tight
            self._drawing.view_box = (tx, ty, tw, th)
            self._drawing.width = tw
            self._drawing.height = th
            self._content_bbox_svg = (tx, ty, tx + tw, ty + th)

        # Timeline view does not use overflow pages.
        return 0, []

    def _actual_content_bounds(
        self,
        config: "CalendarConfig",
        callouts: list[TimelineCallout],
        durations: list[TimelineDuration],
        axis_left: float,
        axis_right: float,
        axis_y: float,
        area_x: float,
        area_y: float,
        area_w: float,
        area_h: float = 0.0,
    ) -> tuple[float, float, float, float]:
        """
        Compute the tight bounding box (SVG space) of all rendered timeline content.

        Returns (x, y, w, h) suitable for replacing coordinates["TimelineArea"].
        """
        # Seed bounds with the axis line itself (plus tick clearance).
        tick_h = max(6.0, config.timeline_axis_width * 2.5)
        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        date_size = max(8.0, config.weekly_name_text_font_size * 0.95)

        # Axis + tick labels extend above axis_y (smaller SVG y = visually higher)
        axis_tick_top = axis_y - (tick_h + label_size * 1.5)
        # Date labels below axis sit slightly below axis_y (larger SVG y = visually lower)
        axis_date_bottom = axis_y + (date_size * 0.1)

        min_y = axis_tick_top
        max_y = axis_date_bottom

        # Holiday icons and their date labels hang below the axis. Durations
        # usually reach further down and would cover this, but a timeline with
        # no duration bars would otherwise crop the band away under --shrink.
        if getattr(config, "timeline_show_holiday_icons", True):
            max_y = max(max_y, axis_y + self._holiday_band_extent(config))

        # Callouts extend above axis_y (box_y is the SVG top of the box)
        for callout in callouts:
            min_y = min(min_y, callout.box_y)

        # Durations extend below axis_y (horizontal) or to the left of
        # axis_x (vertical).
        min_x = axis_left
        max_x = axis_right
        if durations:
            title_size, notes_size, d_date_size, bar_h = self._duration_metrics(config)
            min_duration_offset = self._min_duration_offset(config, d_date_size)
            duration_offset = max(
                config.timeline_duration_offset_y, min_duration_offset
            )
            lane_gap = max(config.timeline_duration_lane_gap_y, d_date_size * 0.9)
            lane_stride_h = bar_h + lane_gap
            lane_stride_v = bar_h + lane_gap

            for dur in durations:
                if dur.orientation is Orientation.VERTICAL:
                    if dur.lane_side is Side.PRIMARY:
                        bar_x_left = axis_left + duration_offset + (dur.lane * lane_stride_v)
                        max_x = max(max_x, bar_x_left + bar_h)
                    else:
                        bar_x_right = axis_left - duration_offset - (dur.lane * lane_stride_v)
                        min_x = min(min_x, bar_x_right - bar_h)
                    label_y_top = dur.start_y - (d_date_size * 1.3)
                    label_y_bot = dur.end_y + (d_date_size * 1.3)
                    min_y = min(min_y, label_y_top)
                    max_y = max(max_y, label_y_bot)
                else:
                    bar_bottom = axis_y + duration_offset
                    bar_y = bar_bottom + (dur.lane * lane_stride_h)
                    max_y = max(max_y, bar_y + bar_h)

        # Extend bounds for declared timebands (only when present).
        top_bands = list(getattr(config, "timeline_top_time_bands", None) or [])
        bottom_bands = list(getattr(config, "timeline_bottom_time_bands", None) or [])
        top_bands_h = sum(float(b.get("row_height", 14.0)) for b in top_bands)
        bottom_bands_h = sum(float(b.get("row_height", 14.0)) for b in bottom_bands)
        if top_bands_h > 0:
            min_y = min(min_y, area_y)
        if bottom_bands_h > 0:
            max_y = max(max_y, area_y + area_h)

        # X: axis extent (with 4% margins already baked in as area_x offsets),
        # extended to include any vertical-orientation duration lanes that
        # spill to the left of the axis.
        x = min(axis_left, min_x)
        w = max(axis_right, max_x) - x

        # Y: min_y is SVG top, max_y is SVG bottom
        y = min_y
        h = max(1.0, max_y - min_y)

        return (round(x, 2), round(y, 2), round(w, 2), round(h, 2))

    @staticmethod
    def _split_events(
        config: "CalendarConfig",
        events: list[Event],
    ) -> tuple[list[Event], list[Event]]:
        """Split into (point_events, duration_events), honoring the
        --noevents / --nodurations content filters."""
        point_events: list[Event] = []
        duration_events: list[Event] = []

        for event in events:
            if event.is_duration:
                if config.includedurations:
                    duration_events.append(event)
            else:
                if config.includeevents:
                    point_events.append(event)

        return point_events, duration_events

    def _layout_callouts(
        self,
        config: "CalendarConfig",
        events: list[Event],
        start: arrow.Arrow,
        end: arrow.Arrow,
        *,
        axis_origin: tuple[float, float],
        axis_length: float,
        orientation: Orientation,
        side: Side,
        max_extent: float | None = None,
        label_bounds: tuple[float, float] | None = None,
        group_colors: dict[str, str] | None = None,
        style_engine: StyleEngine | None = None,
    ) -> list[TimelineCallout]:
        """Place point-event callouts using the labella VPSC algorithm.

        Delegates label-position optimization to the vendored labella
        primitives (`vendor/labella/`). For each event, returns a
        `TimelineCallout` carrying both the axis dot position and the
        post-VPSC label box position, plus the bezier leader path in
        axis-local coordinates.

        Events whose start date falls outside the user-requested range
        (or that fail to parse) are dropped.
        """
        if not events:
            return []

        # User-range filtering — matches the legacy behavior so events
        # outside the requested window don't get drawn even though the
        # axis itself spans the rendered range.
        user_start = (
            self._safe_day(config.userstart, fallback=start)
            if config.userstart else start
        )
        user_end = (
            self._safe_day(config.userend, fallback=end)
            if config.userend else end
        )

        # Filter events to the user-requested window and assign palette
        # colors in chronological order BEFORE labella runs, so colour
        # assignment is independent of the layout algorithm.
        in_range: list[Event] = []
        for ev in events:
            day = self._safe_day(ev.start, fallback=start)
            if (
                day.floor("day") < user_start.floor("day")
                or day.floor("day") > user_end.floor("day")
            ):
                continue
            in_range.append(ev)
        if not in_range:
            return []

        ordered = sorted(
            in_range,
            key=lambda e: (
                e.start,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )

        group_colors = group_colors or {}
        group_depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)

        palette_primary = config.timeline_top_colors or [
            config.get_text_style("ec-event-name").color
            or config.timeline_name_text_font_color
        ]
        palette_secondary = config.timeline_bottom_colors or palette_primary

        # Pre-resolve color + rule-engine style per event, keyed by identity
        # so the post-labella lookup is robust to reordering (Side.BOTH
        # partitions events into two groups).
        per_event: dict[int, tuple[str, "StyleResult | None", int]] = {}
        for idx, event in enumerate(ordered):
            base_palette = (
                palette_secondary if side is Side.SECONDARY else palette_primary
            )
            group = wbs_group(event.wbs, group_depth) if group_colors else None
            color = (
                group_colors[group]
                if group is not None and group in group_colors
                else base_palette[idx % len(base_palette)]
            )
            sr = style_engine.evaluate_event(event) if style_engine else None
            if sr is not None and sr.fill_color:
                color = sr.fill_color
            per_event[id(event)] = (color, sr, idx)

        # Build the date → axis-local position closure. axis_length spans
        # the entire date window; the labella adapter handles minPos/maxPos
        # clamping based on config.
        def pos_for_day(day: arrow.Arrow) -> float:
            span_days = max(1, (end.floor("day") - start.floor("day")).days)
            offset = (day.floor("day") - start.floor("day")).days
            clamped = max(0, min(offset, span_days))
            return axis_length * (clamped / span_days)

        placements = _labella_layout_callouts(
            ordered,
            axis_origin=axis_origin,
            axis_length=axis_length,
            orientation=orientation,
            side=side,
            config=config,
            pos_for_day=pos_for_day,
            min_layer_gap=(
                self._axis_label_clearance(config, start, end)
                if orientation is Orientation.HORIZONTAL
                else 0.0
            ),
            max_extent=max_extent,
            label_bounds=label_bounds,
        )

        # For Side.BOTH the secondary-side events get the secondary palette
        # — unless a WBS group already decided the color, which has to hold
        # on both sides of the axis or the group stops being one color.
        out: list[TimelineCallout] = []
        for p in placements:
            color, sr, source_idx = per_event[id(p.event)]
            if (
                not group_colors
                and p.side is Side.SECONDARY
                and config.timeline_bottom_colors
            ):
                color = config.timeline_bottom_colors[
                    source_idx % len(config.timeline_bottom_colors)
                ]
                if sr is not None and sr.fill_color:
                    color = sr.fill_color
            out.append(
                TimelineCallout(
                    event=p.event,
                    color=color,
                    x_dot=p.x_dot,
                    y_dot=p.y_dot,
                    lane=p.layer,
                    box_x=p.x_label,
                    box_y=p.y_label,
                    box_width=p.label_w,
                    box_height=p.label_h,
                    leader_path_d=p.leader_path_d,
                    axis_origin=p.axis_origin,
                    orientation=p.orientation,
                    style=sr,
                )
            )

        return out

    @staticmethod
    def _wbs_group_colors(
        config: "CalendarConfig", events: "Sequence[Event]"
    ) -> dict[str, str]:
        """One color per WBS group, shared by every item drawn on the chart.

        Events, milestones and duration bars are laid out separately but
        belong to one schedule, so a phase reads as a phase only if its
        colour is the same above and below the axis.  The map is therefore
        built once over all of them, in date order, so a group takes the
        palette entry its earliest item would have taken.

        ``timeline_top_colors`` is the palette: with one colour per group
        there is only one palette to draw from, so a theme's
        ``bottom_colors`` no longer separates durations from callouts while
        grouping is on.

        Returns ``{}`` when grouping is off, which leaves each layout to its
        own per-item palette cycling.
        """
        depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)
        if depth <= 0:
            return {}

        _notes_style = config.get_text_style("ec-event-notes")
        palette = (
            config.timeline_top_colors
            or config.timeline_bottom_colors
            or [_notes_style.color or config.timeline_notes_text_font_color]
        )

        ordered = sorted(
            events,
            key=lambda e: (
                e.start,
                e.end,
                e.priority,
                e.task_name.lower() if e.task_name else "",
            ),
        )
        colors: dict[str, str] = {}
        for event in ordered:
            group = wbs_group(event.wbs, depth)
            if group not in colors:
                colors[group] = palette[len(colors) % len(palette)]
        return colors

    @staticmethod
    def _order_durations(
        config: "CalendarConfig",
        events: list[Event],
        group_colors: dict[str, str] | None = None,
    ) -> tuple[list[Event], dict[int, str]]:
        """Order duration events and decide what color each one gets.

        Bars are grouped by the first ``timeline_wbs_group_depth``
        segments of their WBS, so ``NP.3.S1.4`` and ``NP.3.S2.1`` both land
        in ``NP.3``.  A group's bars sort together and take one color from
        the palette, which is what lets a phase read as a band without a
        legend.  Unnumbered bars form their own block after the numbered
        ones — interleaving them by date would scatter them through the
        hierarchy, the same reasoning the gantt's row ordering uses.

        Depth 0 turns grouping off: bars run in date order and the palette
        cycles per bar, as it did before grouping existed.

        ``group_colors`` is the chart-wide map from
        :py:meth:`_wbs_group_colors`, so a bar takes the same colour as the
        milestones and events in its phase.

        Returns ``(ordered_events, {id(event): color})``.
        """
        # A caller that lays bars out on their own — a test, or any future
        # path that skips _render_content — still gets grouped colors; the
        # map is only passed in so events and bars agree chart-wide.
        if not group_colors:
            group_colors = TimelineRenderer._wbs_group_colors(config, events)

        def date_key(event: Event) -> tuple:
            return (
                event.start,
                event.end,
                event.priority,
                event.task_name.lower() if event.task_name else "",
            )

        depth = int(getattr(config, "timeline_wbs_group_depth", 0) or 0)

        if depth > 0:
            groups = {id(e): wbs_group(e.wbs, depth) for e in events}
            ordered = sorted(
                events,
                key=lambda e: (
                    0 if groups[id(e)] else 1,
                    wbs_sort_key(groups[id(e)]),
                    wbs_sort_key(e.wbs),
                    date_key(e),
                ),
            )
        else:
            groups = {id(e): "" for e in events}
            ordered = sorted(events, key=date_key)

        colors: dict[int, str] = {}
        if depth > 0:
            for event in ordered:
                colors[id(event)] = group_colors.get(groups[id(event)], "")
        else:
            _notes_style = config.get_text_style("ec-event-notes")
            palette = config.timeline_bottom_colors or [
                _notes_style.color or config.timeline_notes_text_font_color
            ]
            for index, event in enumerate(ordered):
                colors[id(event)] = palette[index % len(palette)]

        return ordered, colors

    def _layout_durations(
        self,
        config: "CalendarConfig",
        events: list[Event],
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        style_engine: StyleEngine | None = None,
        group_colors: dict[str, str] | None = None,
    ) -> list[TimelineDuration]:
        """Lay out duration bars in lanes below a horizontal axis.

        Chronologically sorted bars pack greedily into the first lane
        whose previous bar ends at least ``min_gap`` px earlier.  Bars
        are clamped to the user-typed range with ``continues_left/right``
        flagged so the drawer can add continuation arrows; events wholly
        outside the range are dropped.  Returns placement records only —
        drawing happens in `_draw_duration`.
        """
        if not events:
            return []

        ordered, duration_colors = self._order_durations(
            config, events, group_colors
        )

        lane_last_end: list[float] = []
        min_gap = max(10.0, self._page_width * 0.01)
        _layout_notes_style = config.get_text_style("ec-event-notes")
        title_size, notes_size, date_size, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(_layout_notes_style.font or config.timeline_notes_text_font_name)
        notes_font_path = self._safe_font_path(_layout_notes_style.font or config.timeline_notes_text_font_name)
        date_font_path = self._safe_font_path(
            config.get_text_style("ec-duration-date").font
            or config.timeline_duration_date_font
            or self._tk("text:duration_date").get("font")
            or config.timeline_date_font
        )

        out: list[TimelineDuration] = []

        # Compare to the user-typed range (not the weekend-adjusted range)
        # so events ending on an excluded weekend day are not flagged as
        # continuing past the visible diagram.
        user_start = self._safe_day(config.userstart, fallback=start) if config.userstart else start
        user_end = self._safe_day(config.userend, fallback=end) if config.userend else end

        for idx, event in enumerate(ordered):
            start_day = self._safe_day(event.start, fallback=start)
            end_day = self._safe_day(event.end, fallback=start_day)
            if end_day < start_day:
                start_day, end_day = end_day, start_day

            # Skip events entirely outside the visible date range.
            if end_day.floor("day") < user_start.floor("day"):
                continue
            if start_day.floor("day") > user_end.floor("day"):
                continue

            continues_left = start_day.floor("day") < user_start.floor("day")
            continues_right = end_day.floor("day") > user_end.floor("day")

            sx = self._x_for_day(start_day, start, end, axis_left, axis_right)
            ex = self._x_for_day(end_day, start, end, axis_left, axis_right)

            configured_w = (
                float(config.timeline_duration_box_width)
                if config.timeline_duration_box_width is not None
                else 0.0
            )
            if configured_w > 0:
                min_width = configured_w
            else:
                # Increase short duration bars when larger font sizes are used so
                # the name/notes lines can fit within the bar.
                name_w = string_width(
                    event.task_name or "", title_font_path, title_size
                )
                notes_w = string_width(
                    (event.notes or "").strip(), notes_font_path, notes_size
                )
                # The start/end dates sit inside the bar's ends, so a bar has
                # to be wide enough for them plus whatever text it carries —
                # otherwise the title is squeezed to nothing on a short event.
                dates_w = self._duration_dates_width(
                    format_arrow_date(
                        self._safe_day(event.start, fallback=start),
                        config.timeline_date_format,
                    ),
                    format_arrow_date(
                        self._safe_day(event.end, fallback=start),
                        config.timeline_date_format,
                    ),
                    date_font_path,
                    date_size,
                )
                min_width = max(
                    max(16.0, self._page_width * 0.02),
                    name_w + 12.0 + dates_w,
                    notes_w + 12.0 + dates_w,
                )
            if ex - sx < min_width:
                ex = min(axis_right, sx + min_width)

            lane = self._place_span_in_lane(lane_last_end, sx, ex, min_gap)
            color = duration_colors[id(event)]
            _sr = style_engine.evaluate_event(event) if style_engine is not None else None
            if _sr is not None and _sr.fill_color:
                color = _sr.fill_color
            out.append(
                TimelineDuration(
                    event=event,
                    color=color,
                    start_x=sx,
                    end_x=ex,
                    lane=lane,
                    min_width=min_width,
                    continues_left=continues_left,
                    continues_right=continues_right,
                    style=_sr,
                )
            )

        return out

    def _layout_durations_vertical(
        self,
        config: "CalendarConfig",
        events: list[Event],
        start: arrow.Arrow,
        end: arrow.Arrow,
        *,
        axis_x: float,
        axis_top: float,
        axis_bottom: float,
        side: Side = Side.SECONDARY,
        style_engine: StyleEngine | None = None,
        group_colors: dict[str, str] | None = None,
    ) -> list[TimelineDuration]:
        """Place vertical-orientation duration bars alongside the axis.

        Bars run along the axis from start_y to end_y. Lanes stack
        perpendicularly away from the axis (each new overlapping bar sits
        further out). The per-bar `min_width` field carries the minimum
        *along-axis* length for vertical bars so short events still have
        room for their labels.

        ``side`` selects which side(s) of the axis bars go on:
        - PRIMARY  → right side
        - SECONDARY → left side
        - BOTH     → alternate by start date, each side gets independent
          lane tracking
        """
        if not events:
            return []

        ordered, duration_colors = self._order_durations(
            config, events, group_colors
        )

        if side is Side.BOTH:
            # Chronological alternation mirrors how callouts split for
            # Side.BOTH; gives a balanced layout regardless of input order.
            primary_events = [e for i, e in enumerate(ordered) if i % 2 == 0]
            secondary_events = [e for i, e in enumerate(ordered) if i % 2 == 1]
            return (
                self._layout_durations_vertical(
                    config, primary_events, start, end,
                    axis_x=axis_x, axis_top=axis_top, axis_bottom=axis_bottom,
                    side=Side.PRIMARY, style_engine=style_engine,
                    group_colors=group_colors,
                )
                + self._layout_durations_vertical(
                    config, secondary_events, start, end,
                    axis_x=axis_x, axis_top=axis_top, axis_bottom=axis_bottom,
                    side=Side.SECONDARY, style_engine=style_engine,
                    group_colors=group_colors,
                )
            )

        lane_last_end: list[float] = []
        min_gap = max(10.0, self._page_height * 0.01)
        _layout_notes_style = config.get_text_style("ec-event-notes")
        title_size, notes_size, date_size, _ = self._duration_metrics(config)
        title_font_path = self._safe_font_path(
            _layout_notes_style.font or config.timeline_notes_text_font_name
        )
        notes_font_path = self._safe_font_path(
            _layout_notes_style.font or config.timeline_notes_text_font_name
        )
        date_font_path = self._safe_font_path(
            config.get_text_style("ec-duration-date").font
            or config.timeline_duration_date_font
            or self._tk("text:duration_date").get("font")
            or config.timeline_date_font
        )

        out: list[TimelineDuration] = []

        user_start = self._safe_day(config.userstart, fallback=start) if config.userstart else start
        user_end = self._safe_day(config.userend, fallback=end) if config.userend else end

        for idx, event in enumerate(ordered):
            start_day = self._safe_day(event.start, fallback=start)
            end_day = self._safe_day(event.end, fallback=start_day)
            if end_day < start_day:
                start_day, end_day = end_day, start_day

            if end_day.floor("day") < user_start.floor("day"):
                continue
            if start_day.floor("day") > user_end.floor("day"):
                continue

            continues_top = start_day.floor("day") < user_start.floor("day")
            continues_bottom = end_day.floor("day") > user_end.floor("day")

            sy = self._y_for_day(start_day, start, end, axis_top, axis_bottom)
            ey = self._y_for_day(end_day, start, end, axis_top, axis_bottom)

            configured_len = (
                float(config.timeline_duration_box_width)
                if config.timeline_duration_box_width is not None
                else 0.0
            )
            if configured_len > 0:
                min_length = configured_len
            else:
                # Text reads bottom→top once rotated, so the bar's
                # along-axis length is the available width for the label.
                name_w = string_width(
                    event.task_name or "", title_font_path, title_size
                )
                notes_w = string_width(
                    (event.notes or "").strip(), notes_font_path, notes_size
                )
                # The dates ride inside the bar's two along-axis ends, so the
                # bar has to be long enough for them and its label both.
                dates_w = self._duration_dates_width(
                    format_arrow_date(
                        self._safe_day(event.start, fallback=start),
                        config.timeline_date_format,
                    ),
                    format_arrow_date(
                        self._safe_day(event.end, fallback=start),
                        config.timeline_date_format,
                    ),
                    date_font_path,
                    date_size,
                )
                min_length = max(
                    max(16.0, self._page_height * 0.02),
                    name_w + 12.0 + dates_w,
                    notes_w + 12.0 + dates_w,
                )
            if ey - sy < min_length:
                ey = min(axis_bottom, sy + min_length)

            lane = self._place_span_in_lane(lane_last_end, sy, ey, min_gap)
            color = duration_colors[id(event)]
            _sr = style_engine.evaluate_event(event) if style_engine is not None else None
            if _sr is not None and _sr.fill_color:
                color = _sr.fill_color
            out.append(
                TimelineDuration(
                    event=event,
                    color=color,
                    start_x=axis_x,
                    end_x=axis_x,
                    lane=lane,
                    min_width=min_length,
                    continues_left=continues_top,
                    continues_right=continues_bottom,
                    style=_sr,
                    orientation=Orientation.VERTICAL,
                    start_y=sy,
                    end_y=ey,
                    lane_side=side,
                )
            )

        return out

    @staticmethod
    def _place_span_in_lane(
        lane_last_end: list[float],
        start_x: float,
        end_x: float,
        min_gap: float,
    ) -> int:
        for lane, last_end in enumerate(lane_last_end):
            if start_x >= (last_end + min_gap):
                lane_last_end[lane] = end_x
                return lane

        lane_last_end.append(end_x)
        return len(lane_last_end) - 1

    @staticmethod
    def _boxes_overlap(
        box_a: tuple[float, float, float, float],
        box_b: tuple[float, float, float, float],
        pad: float = 0.0,
    ) -> bool:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        return not (
            ax2 + pad <= bx1 or bx2 + pad <= ax1 or ay2 + pad <= by1 or by2 + pad <= ay1
        )


    def _draw_callout(
        self,
        config: "CalendarConfig",
        item: TimelineCallout,
        axis_y: float,
    ) -> None:
        """Draw one placed callout: axis dot, label box, and box content
        (icon, name, notes, and — horizontal axes only — the event date,
        right-aligned on the title line).  Text is shrunk to fit via
        `_fit_box_text_sizes`; the leader path was already drawn in
        `_render_content`'s underlay pass."""
        title = item.event.task_name or "(untitled)"
        notes = (item.event.notes or "").strip()

        title_font_size, notes_font_size, date_font_size = self._callout_metrics(config)

        # Always draw a plain circle on the axis — icons go in the label box.
        # `item.x_dot` / `item.y_dot` already account for orientation; the
        # `axis_y` arg is retained for backwards-compatibility but only
        # consulted by the legacy horizontal-only date-label rendering path
        # further down in this method.
        self._draw_timeline_marker(
            config,
            x=item.x_dot,
            y=item.y_dot,
            color=item.color,
            icon_name=None,
        )

        # Label box.
        _callout_style = config.get_box_style("ec-callout-box")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=_callout_style.fill_opacity,
            stroke=item.color,
            stroke_width=_callout_style.stroke_width,
            stroke_opacity=0.95,
            stroke_dasharray=_callout_style.stroke_dasharray or None,
        )
        self._draw_rect(
            item.box_x,
            item.box_y,
            item.box_width,
            item.box_height,
            css_class="ec-callout-box",
            **rect_kwargs,
        )

        has_icon = bool(item.event.icon and self._resolve_icon_svg(item.event.icon))
        icon_gap = 2.0
        icon_reserved = (title_font_size + icon_gap) if has_icon else 0.0

        # The box is two columns: a narrow left one carrying the icon over
        # the date, and the text column with the name over the notes.  The
        # left column is as wide as the wider of its two occupants, so the
        # date sits under the icon without running beneath the notes.
        date_label = self._callout_date_label(config, item)
        date_reserved = (
            self._callout_date_width(config, date_label, date_font_size)
            if date_label
            else 0.0
        )

        _name_style = config.get_text_style("ec-event-name")
        _notes_style = config.get_text_style("ec-event-notes")
        tk_name = self._tk("text:event_name")
        tk_notes = self._tk("text:event_notes")
        name_font_default = (
            tk_name.get("font")
            or config.timeline_name_text_font_name
            or _name_style.font
        )
        notes_font_default = (
            tk_notes.get("font")
            or config.timeline_notes_text_font_name
            or _notes_style.font
        )
        title_font_path = self._safe_font_path(name_font_default)
        notes_font_path = self._safe_font_path(notes_font_default)
        # Both text lines start after the left column, so both are measured
        # against the same width.
        left_column = max(icon_reserved, date_reserved)
        text_width = item.box_width - 12.0 - left_column
        fitted_title, fitted_notes = self._fit_box_text_sizes(
            title,
            notes,
            text_width,
            item.box_height,
            title_font_path,
            notes_font_path,
            title_font_size,
            notes_font_size,
            height_for=lambda ts, ns, has: self._callout_text_geometry(
                item.box_height, ts, ns, title_font_path, notes_font_path, has
            )[2],
        )

        text_x = item.box_x + 6.0
        title_dy, notes_dy, _ = self._callout_text_geometry(
            item.box_height,
            fitted_title,
            fitted_notes,
            title_font_path,
            notes_font_path,
            bool(notes),
        )
        title_y = item.box_y + title_dy
        notes_y = item.box_y + notes_dy

        event_text_color = (
            tk_name.get("color")
            or config.timeline_name_text_font_color
            or _name_style.color
            or item.color
        )
        name_font, _, name_color, name_opacity = _sr.text_override(
            "event_name",
            font=name_font_default,
            color=event_text_color,
            opacity=_name_style.opacity,
        )
        notes_color_base = (
            tk_notes.get("color")
            or config.timeline_notes_text_font_color
            or _notes_style.color
            or event_text_color
        )
        notes_font, _, notes_color, notes_opacity = _sr.text_override(
            "event_notes",
            font=notes_font_default,
            color=notes_color_base,
            opacity=_notes_style.opacity,
        )
        icon_to_draw = _sr.icon if _sr.icon is not None else item.event.icon
        icon_color = _sr.icon_color or event_text_color

        if has_icon:
            self._draw_icon_svg(
                icon_to_draw,
                text_x,
                title_y,
                fitted_title,
                anchor="start",
                color=icon_color,
                css_class="ec-event-icon",
                box_token=(
                    "box:milestone"
                    if getattr(item.event, "milestone", False)
                    else "box:event"
                ),
                box_ctx=self._event_ctx(item.event),
            )

        # One left edge for the name and the notes both — the notes used to
        # start at the box edge, under the icon, which read as a hanging
        # indent nobody asked for.
        content_x = text_x + left_column
        content_max_w = max(8.0, item.box_width - 12.0 - left_column)

        self._draw_text(
            content_x,
            title_y,
            title,
            name_font,
            fitted_title,
            fill=name_color,
            fill_opacity=name_opacity,
            max_width=content_max_w,
            css_class="ec-event-name",
        )

        if notes:
            self._draw_text(
                content_x,
                notes_y,
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                max_width=content_max_w,
                css_class="ec-event-notes",
            )

        # Date, in the left column under the icon.  It sits with the event
        # it belongs to — it used to be drawn near the axis at the event's
        # dot, staggered by source index, which put it nowhere near its own
        # callout and let two dates collide.
        if date_label:
            _event_date_style = config.get_text_style("ec-event-date")
            tk_event_date = self._tk("text:event_date")
            date_font, _, date_color, _ = _sr.text_override(
                "event_date",
                font=(
                    _event_date_style.font
                    or tk_event_date.get("font")
                    or config.timeline_date_font
                ),
                color=(
                    _event_date_style.color
                    or tk_event_date.get("color")
                    or event_text_color
                ),
            )
            self._draw_text(
                text_x,
                notes_y,
                date_label,
                date_font,
                date_font_size,
                fill=date_color,
                anchor="start",
                max_width=max(8.0, left_column),
                css_class="ec-event-date",
            )

    def _duration_bar_y(
        self, config: "CalendarConfig", item: TimelineDuration, axis_y: float
    ) -> tuple[float, float]:
        """``(bar_y, bar_h)`` for one horizontal duration bar.

        The connector and the bar itself both need this and used to compute
        it separately; sharing it is what lets the connector know whether the
        bar it points at was actually drawn.
        """
        _title, _notes, date_size, bar_h = self._duration_metrics(config)
        duration_offset = max(
            config.timeline_duration_offset_y,
            self._min_duration_offset(config, date_size),
        )
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        # The start/end dates ride inside the bar, so a row is the bar plus
        # the gap to the next one — no label band underneath.
        lane_stride = bar_h + lane_gap
        return axis_y + duration_offset + (item.lane * lane_stride), bar_h

    @staticmethod
    def _duration_dates_width(
        start_label: str,
        end_label: str,
        font_path: str | None,
        size: float,
    ) -> float:
        """Horizontal room the two in-bar dates claim, padding included.

        Reserved before the title is fitted and matched by the layout's
        `min_width`, so what the bar promises the dates is what they get.
        """
        def measure(text: str) -> float:
            if not text:
                return 0.0
            if not font_path:
                return len(text) * size * 0.5
            return string_width(text, font_path, size)

        return (
            measure(start_label)
            + measure(end_label)
            + (2.0 * _DURATION_DATE_PAD_X)
            + (2.0 * _DURATION_DATE_GAP_X)
        )

    def _duration_row_extent(self, config: "CalendarConfig") -> float:
        """Vertical room one duration row needs, its date labels included.

        The dates sit inside the bar, so the row is just the rect.  Kept as
        its own method because `_actual_content_bounds` reserves the same
        figure and the two must not drift.
        """
        _title, _notes, _date_size, bar_h = self._duration_metrics(config)
        return bar_h

    def _duration_bar_x(
        self, config: "CalendarConfig", item: TimelineDuration, axis_x: float
    ) -> tuple[float, float, float]:
        """``(near_edge_x, thickness, sign)`` for one vertical duration bar.

        ``sign`` is +1 on the primary side (right of the axis), -1 on the
        secondary.
        """
        _title, _notes, date_size, bar_thickness = self._duration_metrics(config)
        duration_offset = max(
            config.timeline_duration_offset_y,
            self._min_duration_offset(config, date_size),
        )
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_thickness + lane_gap
        sign = 1.0 if item.lane_side is Side.PRIMARY else -1.0
        near_x = axis_x + sign * (duration_offset + (item.lane * lane_stride))
        return near_x, bar_thickness, sign

    @staticmethod
    def _duration_fits(bar_far_edge: float, limit: float | None) -> bool:
        """True when a bar's far edge is inside the drawable area.

        ``limit`` is None whenever nothing constrains the band — no page
        bound was supplied, or --shrink is growing the page to fit the
        content, in which case every bar is drawn however deep the stack
        goes.
        """
        return limit is None or bar_far_edge <= limit

    def _draw_missing_box_marker(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        size: float,
        color: str,
    ) -> None:
        """Mark a leader whose box ran out of room with the missing icon.

        Without it the leader still gets drawn and simply runs off the page,
        which reads as a line pointing at a bar that is not there.  The glyph
        is the theme's ``base.default_missing_icon``; a theme that leaves it
        unset gets a leader that stops at the edge and nothing else, which is
        still better than one that leaves the paper.
        """
        icon = getattr(config, "default_missing_icon", None)
        if not icon:
            return
        configured = getattr(config, "default_missing_icon_size", None)
        if configured and configured > 0:
            size = float(configured)
        self._draw_icon_svg(
            str(icon),
            x,
            self._icon_baseline(y, size),
            size,
            anchor="middle",
            color=color,
            css_class="ec-overflow-icon",
        )

    def _draw_duration_connectors(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_y: float,
        limit: float | None = None,
    ) -> None:
        """Draw the vertical aligner line from the axis to the duration bar.

        Only the bar's left edge gets one.  A bar is widened to whatever its
        name and notes need (see ``_layout_durations``), so on a short event
        the right edge sits at a date the event does not end on — a leader
        there pointed confidently at the wrong day.  The left edge is always
        the true start date, so that one still says something.

        When the bar itself did not fit below ``limit`` the leader stops at
        the edge of the drawable area and ends in the theme's missing-box
        icon, instead of running off the page toward a bar nobody drew.
        """
        bar_y, bar_h = self._duration_bar_y(config, item, axis_y)
        row_extent = self._duration_row_extent(config)
        fits = self._duration_fits(bar_y + row_extent, limit)
        end_y = bar_y if fits else float(limit) - row_extent
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        self._draw_line(
            item.start_x,
            axis_y,
            item.start_x,
            end_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )
        if not fits:
            self._draw_missing_box_marker(
                config, item.start_x, end_y + bar_h / 2.0, bar_h, item.color
            )

    def _draw_duration(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_y: float,
        limit: float | None = None,
    ) -> None:
        """Draw one placed duration below a horizontal axis: the bar
        rect (fill opacity token-first from ``line:duration_bar``),
        start/end axis markers, continuation arrows when the event
        extends past the visible range, and the name / notes / date
        text block sized to the bar's lane.

        A bar whose lane falls past ``limit`` is not drawn at all — its
        leader carries the missing-box icon instead (see
        :py:meth:`_draw_duration_connectors`), which says more than a bar
        printed off the edge of the paper.
        """
        _probe_y, _probe_h = self._duration_bar_y(config, item, axis_y)
        if not self._duration_fits(
            _probe_y + self._duration_row_extent(config), limit
        ):
            return

        title = item.event.task_name or "(untitled duration)"
        notes = (item.event.notes or "").strip()
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)

        title_size, notes_size, date_size, bar_h = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(config, date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_h + lane_gap

        bar_bottom = axis_y + duration_offset
        bar_y = bar_bottom + (item.lane * lane_stride)

        # Duration bar.
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        # Bar-rect fill opacity is token-first: themes set it per-visualizer
        # via a line:duration_bar rule with select: {visualizer: timeline}.
        _tk_bar_opacity = self._tk("line:duration_bar").get("opacity")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=(
                _tk_bar_opacity if _tk_bar_opacity is not None
                else _dur_bar_style.opacity
            ),
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.9,
            stroke_dasharray=_dur_bar_style.dasharray or None,
        )
        self._draw_rect(
            item.start_x,
            bar_y,
            max(1.0, item.end_x - item.start_x),
            bar_h,
            css_class="ec-duration-bar",
            **rect_kwargs,
        )

        # Start/end markers on the main axis.
        _marker_style = config.get_box_style("ec-milestone-marker")
        marker_fill = _sr.fill_color if _sr.fill_color is not None else item.color
        marker_stroke = _sr.stroke_color if _sr.stroke_color is not None else _marker_style.stroke
        self._draw_circle(
            item.start_x,
            axis_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )
        self._draw_circle(
            item.end_x,
            axis_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )

        # Continuation icons for duration bars clipped by the visible range.
        # continues_left == event starts before the visualization start
        # ("before"); continues_right == event ends after the visualization
        # end ("after"). Driven by the global `continuation` theme section.
        if (item.continues_left or item.continues_right) and bool(
            getattr(config, "show_continuation_icon", True)
        ):
            cont_h = float(getattr(config, "continuation_icon_height", 8.0))
            cont_color_cfg = getattr(config, "continuation_icon_color", None)
            cont_color = cont_color_cfg if cont_color_cfg else item.color
            cont_baseline = bar_y + bar_h * 0.5 + cont_h * 0.3
            if item.continues_left:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_before", None),
                        "horizontal",
                        "arrow-left",
                    ),
                    item.start_x,
                    cont_baseline,
                    cont_h,
                    anchor="start",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )
            if item.continues_right:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_after", None),
                        "horizontal",
                        "arrow-right",
                    ),
                    item.end_x,
                    cont_baseline,
                    cont_h,
                    anchor="end",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )

        _dur_name_style = config.get_text_style("ec-event-name")
        _dur_notes_style = config.get_text_style("ec-event-notes")
        tk_dur_name = self._tk("text:event_name")
        tk_dur_notes = self._tk("text:event_notes")
        dur_name_font_default = (
            tk_dur_name.get("font")
            or config.timeline_name_text_font_name
            or _dur_name_style.font
        )
        dur_notes_font_default = (
            tk_dur_notes.get("font")
            or config.timeline_notes_text_font_name
            or _dur_notes_style.font
        )
        title_font_path = self._safe_font_path(dur_name_font_default)
        notes_font_path = self._safe_font_path(dur_notes_font_default)

        # The start/end dates sit inside the bar's two ends, so the title and
        # notes get what is left between them rather than the whole bar.
        start_label = format_arrow_date(start_day, config.timeline_date_format)
        end_label = format_arrow_date(end_day, config.timeline_date_format)
        date_font_path = self._safe_font_path(
            config.get_text_style("ec-duration-date").font
            or config.timeline_duration_date_font
            or self._tk("text:duration_date").get("font")
            or config.timeline_date_font
        )
        dates_w = self._duration_dates_width(
            start_label, end_label, date_font_path, date_size
        )
        bar_w = max(1.0, item.end_x - item.start_x)
        text_w = max(10.0, bar_w - 6.0 - dates_w)
        fitted_title, fitted_notes = self._fit_box_text_sizes(
            title,
            notes,
            text_w,
            bar_h,
            title_font_path,
            notes_font_path,
            title_size,
            notes_size,
        )
        duration_text_color = (
            tk_dur_name.get("color")
            or config.timeline_name_text_font_color
            or _dur_name_style.color
            or item.color
        )
        title_font_base = dur_name_font_default
        title_font, _, name_color, name_opacity = _sr.text_override(
            "duration_name",
            font=title_font_base,
            color=duration_text_color,
            opacity=_dur_name_style.opacity,
        )
        # Vertically center the title (and notes, when present) within the bar
        # so the text sits in the lower portion of the rectangle rather than
        # being pinned to its top edge.
        has_notes = bool(notes and config.include_notes)
        line1_h = fitted_title * 1.2
        line2_h = (fitted_notes * 1.2) if has_notes else 0.0
        text_block_h = line1_h + line2_h
        text_top_y = bar_y + max(0.0, (bar_h - text_block_h) / 2.0)
        title_y = text_top_y + fitted_title * 0.85
        show_icon = bool(config.timeline_duration_icon_visible) and bool(item.event.icon)
        if show_icon:
            icon_size = fitted_title
            try:
                title_w = string_width(title, title_font_path, fitted_title)
            except Exception:
                title_w = len(title) * fitted_title * 0.55
            gap = 2.0
            total_w = icon_size + gap + title_w
            available_w = max(8.0, text_w)
            icon_scale_x = min(1.0, available_w / total_w) if total_w > available_w else 1.0
            effective_icon_w = icon_size * icon_scale_x
            effective_text_w = min(title_w * icon_scale_x, available_w - effective_icon_w - gap)
            group_x0 = (item.start_x + item.end_x) / 2 - (effective_icon_w + gap + effective_text_w) / 2.0
            draw_x = max(item.start_x, group_x0)
            icon_transform = None
            if icon_scale_x < 1.0:
                icon_transform = (
                    f"translate({draw_x:.4f} {title_y:.4f}) "
                    f"scale({icon_scale_x:.6f} 1) "
                    f"translate({-draw_x:.4f} {-title_y:.4f})"
                )
            dur_icon = _sr.icon if _sr.icon is not None else item.event.icon
            dur_icon_color = _sr.icon_color or duration_text_color
            icon_drawn = self._draw_icon_svg(
                dur_icon,
                draw_x,
                title_y,
                icon_size,
                anchor="start",
                color=dur_icon_color,
                fallback_name=config.default_missing_icon,
                fallback_size=config.default_missing_icon_size,
                fallback_color=dur_icon_color,
                transform=icon_transform,
                css_class="ec-duration-icon",
                box_token="box:duration",
                box_ctx=self._event_ctx(item.event),
            )
            text_x = draw_x + effective_icon_w + gap if icon_drawn else (item.start_x + item.end_x) / 2
            self._draw_text(
                text_x,
                title_y,
                title,
                title_font,
                fitted_title,
                fill=name_color,
                fill_opacity=name_opacity,
                anchor="start" if icon_drawn else "middle",
                max_width=max(8.0, item.end_x - text_x - 2),
                css_class="ec-event-name",
            )
        else:
            self._draw_text(
                (item.start_x + item.end_x) / 2,
                title_y,
                title,
                title_font,
                fitted_title,
                fill=name_color,
                fill_opacity=name_opacity,
                anchor="middle",
                max_width=text_w,
                css_class="ec-event-name",
            )

        if has_notes:
            notes_color_base = (
                tk_dur_notes.get("color")
                or config.timeline_notes_text_font_color
                or _dur_notes_style.color
                or duration_text_color
            )
            notes_font, _, notes_color, notes_opacity = _sr.text_override(
                "duration_notes",
                font=dur_notes_font_default,
                color=notes_color_base,
                opacity=_dur_notes_style.opacity,
            )
            notes_y = text_top_y + line1_h + fitted_notes * 0.85
            self._draw_text(
                (item.start_x + item.end_x) / 2,
                notes_y,
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                anchor="middle",
                max_width=text_w,
                css_class="ec-event-notes",
            )

        # Keep start/end labels on the same Y baseline.
        _dur_date_style = config.get_text_style("ec-duration-date")
        tk_dur_date = self._tk("text:duration_date")
        date_font_base = (
            _dur_date_style.font
            or config.timeline_duration_date_font
            or tk_dur_date.get("font")
            or config.timeline_date_font
        )
        date_color_base = (
            _dur_date_style.color
            or config.timeline_duration_date_color
            or tk_dur_date.get("color")
            or duration_text_color
        )
        start_date_font, _, start_date_color, _ = _sr.text_override(
            "duration_start_date",
            font=date_font_base,
            color=date_color_base,
        )
        end_date_font, _, end_date_color, _ = _sr.text_override(
            "duration_end_date",
            font=date_font_base,
            color=date_color_base,
        )
        # Inside the bar, one at each end, on the title's baseline — the
        # same arrangement the event callouts use for their date.
        date_y = title_y
        self._draw_text(
            item.start_x + _DURATION_DATE_PAD_X,
            date_y,
            start_label,
            start_date_font,
            date_size,
            fill=start_date_color,
            anchor="start",
            css_class="ec-duration-date",
        )
        self._draw_text(
            item.end_x - _DURATION_DATE_PAD_X,
            date_y,
            end_label,
            end_date_font,
            date_size,
            fill=end_date_color,
            anchor="end",
            css_class="ec-duration-date",
        )

    def _draw_duration_connectors_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_x: float,
        limit: float | None = None,
    ) -> None:
        """Horizontal aligner line from the vertical axis to the duration bar.

        Start edge only, for the reason given in
        :py:meth:`_draw_duration_connectors`: the far edge is padded out to fit
        the label and does not mark the end date.

        ``limit`` is how far from the axis this side may reach; a lane past it
        gets a leader that stops at the edge and ends in the missing-box icon
        rather than one that runs off the page.
        """
        bar_near_axis_x, bar_thickness, sign = self._duration_bar_x(
            config, item, axis_x
        )
        far_edge = bar_near_axis_x + sign * bar_thickness
        fits = self._duration_fits(abs(far_edge - axis_x), limit)
        end_x = (
            bar_near_axis_x
            if fits
            else axis_x + sign * (float(limit) - bar_thickness)
        )
        _dur_bar_style = config.get_line_style("ec-duration-bar")
        self._draw_line(
            axis_x,
            item.start_y,
            end_x,
            item.start_y,
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.8,
            stroke_dasharray=_dur_bar_style.dasharray or None,
            css_class="ec-connector",
        )
        if not fits:
            self._draw_missing_box_marker(
                config,
                end_x + sign * (bar_thickness / 2.0),
                item.start_y,
                bar_thickness,
                item.color,
            )

    def _draw_duration_vertical(
        self,
        config: "CalendarConfig",
        item: TimelineDuration,
        axis_x: float,
        limit: float | None = None,
    ) -> None:
        """Draw a vertical-orientation duration bar (left of axis).

        A lane past ``limit`` is skipped; its leader carries the missing-box
        icon instead.
        """
        _near_x, _thickness, _sign = self._duration_bar_x(config, item, axis_x)
        if not self._duration_fits(
            abs(_near_x + _sign * _thickness - axis_x), limit
        ):
            return

        title = item.event.task_name or "(untitled duration)"
        notes = (item.event.notes or "").strip()
        start_day = self._safe_day(item.event.start, fallback=arrow.now())
        end_day = self._safe_day(item.event.end, fallback=start_day)

        title_size, notes_size, date_size, bar_thickness = self._duration_metrics(config)
        min_duration_offset = self._min_duration_offset(config, date_size)
        duration_offset = max(config.timeline_duration_offset_y, min_duration_offset)
        lane_gap = max(config.timeline_duration_lane_gap_y, date_size * 0.9)
        lane_stride = bar_thickness + lane_gap

        if item.lane_side is Side.PRIMARY:
            # Right of axis: bars grow rightward, bar_x is the left edge.
            bar_x = axis_x + duration_offset + (item.lane * lane_stride)
        else:
            # Left of axis: bars grow leftward, bar_x is still the left
            # edge of the rectangle (axis_x - offset - lane*stride - thickness).
            bar_right = axis_x - duration_offset - (item.lane * lane_stride)
            bar_x = bar_right - bar_thickness
        bar_y = item.start_y
        bar_h = max(1.0, item.end_y - item.start_y)

        _dur_bar_style = config.get_line_style("ec-duration-bar")
        # Bar-rect fill opacity is token-first: themes set it per-visualizer
        # via a line:duration_bar rule with select: {visualizer: timeline}.
        _tk_bar_opacity = self._tk("line:duration_bar").get("opacity")
        _sr = item.style or StyleResult()
        rect_kwargs = _sr.rect_overrides(
            fill=item.color,
            fill_opacity=(
                _tk_bar_opacity if _tk_bar_opacity is not None
                else _dur_bar_style.opacity
            ),
            stroke=item.color,
            stroke_width=0.9,
            stroke_opacity=0.9,
            stroke_dasharray=_dur_bar_style.dasharray or None,
        )
        self._draw_rect(
            bar_x,
            bar_y,
            bar_thickness,
            bar_h,
            css_class="ec-duration-bar",
            **rect_kwargs,
        )

        # Start/end markers on the main axis at the bar's start/end y.
        _marker_style = config.get_box_style("ec-milestone-marker")
        marker_fill = _sr.fill_color if _sr.fill_color is not None else item.color
        marker_stroke = _sr.stroke_color if _sr.stroke_color is not None else _marker_style.stroke
        self._draw_circle(
            axis_x,
            item.start_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )
        self._draw_circle(
            axis_x,
            item.end_y,
            radius=max(2.7, config.timeline_marker_radius * 0.8),
            fill=marker_fill,
            stroke=marker_stroke,
            stroke_width=max(0.6, _marker_style.stroke_width * 0.8),
        )

        # Continuation icons for bars clipped above/below the visible range.
        # continues_left == event starts before visualization start ("before");
        # continues_right == event ends after visualization end ("after").
        # On a vertical axis the second element of a [horizontal, vertical]
        # icon-list pair selects the orientation-appropriate glyph.
        if (item.continues_left or item.continues_right) and bool(
            getattr(config, "show_continuation_icon", True)
        ):
            cont_h = float(getattr(config, "continuation_icon_height", 8.0))
            cont_color_cfg = getattr(config, "continuation_icon_color", None)
            cont_color = cont_color_cfg if cont_color_cfg else item.color
            cont_x = bar_x + bar_thickness * 0.5
            if item.continues_left:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_before", None),
                        "vertical",
                        "arrow-up",
                    ),
                    cont_x,
                    item.start_y + cont_h * 0.5,
                    cont_h,
                    anchor="middle",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )
            if item.continues_right:
                self._draw_icon_svg(
                    resolve_continuation_icon(
                        getattr(config, "continuation_icon_after", None),
                        "vertical",
                        "arrow-down",
                    ),
                    cont_x,
                    item.end_y - cont_h * 0.5,
                    cont_h,
                    anchor="middle",
                    color=cont_color,
                    css_class="ec-duration-icon",
                )

        # Title + notes rotated -90° so they read bottom→top inside the bar.
        _dur_name_style = config.get_text_style("ec-event-name")
        _dur_notes_style = config.get_text_style("ec-event-notes")
        tk_dur_name = self._tk("text:event_name")
        tk_dur_notes = self._tk("text:event_notes")
        dur_name_font_default = (
            tk_dur_name.get("font")
            or config.timeline_name_text_font_name
            or _dur_name_style.font
        )
        dur_notes_font_default = (
            tk_dur_notes.get("font")
            or config.timeline_notes_text_font_name
            or _dur_notes_style.font
        )
        title_font_path = self._safe_font_path(dur_name_font_default)
        notes_font_path = self._safe_font_path(dur_notes_font_default)
        # Available "width" for the rotated text is the bar's along-axis
        # length, less the two dates that now sit inside its ends.
        start_label = format_arrow_date(start_day, config.timeline_date_format)
        end_label = format_arrow_date(end_day, config.timeline_date_format)
        date_font_path = self._safe_font_path(
            config.get_text_style("ec-duration-date").font
            or config.timeline_duration_date_font
            or self._tk("text:duration_date").get("font")
            or config.timeline_date_font
        )
        dates_w = self._duration_dates_width(
            start_label, end_label, date_font_path, date_size
        )
        text_w = max(10.0, bar_h - 6.0 - dates_w)
        fitted_title, fitted_notes = self._fit_box_text_sizes(
            title,
            notes,
            text_w,
            bar_thickness,
            title_font_path,
            notes_font_path,
            title_size,
            notes_size,
        )
        duration_text_color = (
            tk_dur_name.get("color")
            or config.timeline_name_text_font_color
            or _dur_name_style.color
            or item.color
        )
        title_font, _, name_color, name_opacity = _sr.text_override(
            "duration_name",
            font=dur_name_font_default,
            color=duration_text_color,
            opacity=_dur_name_style.opacity,
        )

        has_notes = bool(notes and config.include_notes)
        line1_h = fitted_title * 1.2
        line2_h = (fitted_notes * 1.2) if has_notes else 0.0
        text_block_h = line1_h + line2_h
        # Anchor the rotation around the bar's center; pre-rotation the text
        # is laid out horizontally centered at (cx, cy) and rotate(-90)
        # turns it into a vertical run reading bottom→top.
        cx = bar_x + bar_thickness / 2.0
        cy = bar_y + bar_h / 2.0
        # Title baseline (pre-rotation) sits above center by half text_block;
        # adjust so the title line ends up on the +y side after rotation
        # (i.e. closer to the bar's start_y / top edge).
        title_pre_y = cy + (bar_thickness / 2.0) - max(0.0, (bar_thickness - text_block_h) / 2.0) - line2_h - (fitted_title * 0.15)
        rot = f"rotate(-90 {cx:.4f} {cy:.4f})"
        self._draw_text(
            cx,
            title_pre_y,
            title,
            title_font,
            fitted_title,
            fill=name_color,
            fill_opacity=name_opacity,
            anchor="middle",
            max_width=text_w,
            transform=rot,
            css_class="ec-event-name",
        )
        if has_notes:
            notes_color_base = (
                tk_dur_notes.get("color")
                or config.timeline_notes_text_font_color
                or _dur_notes_style.color
                or duration_text_color
            )
            notes_font, _, notes_color, notes_opacity = _sr.text_override(
                "duration_notes",
                font=dur_notes_font_default,
                color=notes_color_base,
                opacity=_dur_notes_style.opacity,
            )
            notes_pre_y = title_pre_y + line1_h
            self._draw_text(
                cx,
                notes_pre_y,
                notes,
                notes_font,
                fitted_notes,
                fill=notes_color,
                fill_opacity=notes_opacity,
                anchor="middle",
                max_width=text_w,
                transform=rot,
                css_class="ec-event-notes",
            )

        # Date labels above the bar's start edge and below its end edge,
        # placed at the bar's horizontal center.
        _dur_date_style = config.get_text_style("ec-duration-date")
        tk_dur_date = self._tk("text:duration_date")
        date_font_base = (
            _dur_date_style.font
            or config.timeline_duration_date_font
            or tk_dur_date.get("font")
            or config.timeline_date_font
        )
        date_color_base = (
            _dur_date_style.color
            or config.timeline_duration_date_color
            or tk_dur_date.get("color")
            or duration_text_color
        )
        start_date_font, _, start_date_color, _ = _sr.text_override(
            "duration_start_date",
            font=date_font_base,
            color=date_color_base,
        )
        end_date_font, _, end_date_color, _ = _sr.text_override(
            "duration_end_date",
            font=date_font_base,
            color=date_color_base,
        )
        # Inside the bar's two along-axis ends, rotated with the label.
        # rotate(-90 cx cy) maps a pre-rotation offset of +dx along x onto
        # -dx along y, so the start date is laid out to the right of centre
        # to come out at the bar's top.
        half = (bar_h / 2.0) - _DURATION_DATE_PAD_X
        self._draw_text(
            cx + half,
            cy,
            start_label,
            start_date_font,
            date_size,
            fill=start_date_color,
            anchor="end",
            transform=rot,
            css_class="ec-duration-date",
        )
        self._draw_text(
            cx - half,
            cy,
            end_label,
            end_date_font,
            date_size,
            fill=end_date_color,
            anchor="start",
            transform=rot,
            css_class="ec-duration-date",
        )

    def _draw_timeline_marker(
        self,
        config: "CalendarConfig",
        x: float,
        y: float,
        color: str,
        icon_name: str | None,
    ) -> None:
        """Draw default filled circle marker or icon-in-circle marker."""
        radius = max(2.5, config.timeline_marker_radius)

        # Resolve effective icon: fall back to "position-align" (red) when the
        # requested icon name exists but is not found in the icon table.
        effective_icon = icon_name
        effective_color = color
        if icon_name and self._resolve_icon_svg(icon_name) is None:
            effective_icon = "position-align"
            effective_color = "red"

        icon_found = self._resolve_icon_svg(effective_icon) is not None

        _marker_style = config.get_box_style("ec-milestone-marker")
        if icon_found:
            self._draw_circle(
                x,
                y,
                radius=radius,
                fill="none",
                stroke=effective_color,
                stroke_width=_marker_style.stroke_width,
            )
            # DB-provided SVG icon centered in the circle.
            self._draw_icon_svg(
                effective_icon,
                x,
                y,
                max(7.0, config.timeline_icon_size),
                anchor="middle",
                color=effective_color,
                css_class="ec-event-icon",
            )
            return

        self._draw_circle(
            x,
            y,
            radius=radius,
            fill=color,
            stroke=_marker_style.stroke,
            stroke_width=_marker_style.stroke_width,
        )

    def _duration_metrics(
        self,
        config: "CalendarConfig",
    ) -> tuple[float, float, float, float]:
        """Return (title_size, notes_size, date_size, bar_height).

        Consults ``text:event_name`` / ``text:event_notes`` / ``text:duration_date``
        tokens first; falls back to legacy ``timeline_*_font_size`` (with the
        same 0.85 / 0.82 scale-down factors that pre-migration code applied)
        and finally to the page-scaled ``weekly_name_text_font_size``.
        Token sizes are taken at face value — if a theme defines an explicit
        size for the duration bar text, it's expected to be that size.
        """
        title_size = (
            self._tk("text:event_name").get("size")
            or (
                float(config.timeline_name_text_font_size * 0.85)
                if config.timeline_name_text_font_size is not None
                else max(8.0, config.weekly_name_text_font_size * 0.86)
            )
        )
        notes_size = (
            self._tk("text:event_notes").get("size")
            or (
                float(config.timeline_notes_text_font_size * 0.82)
                if config.timeline_notes_text_font_size is not None
                else max(7.0, config.weekly_name_text_font_size * 0.74)
            )
        )
        date_size = (
            self._tk("text:duration_date").get("size")
            or (
                float(config.timeline_duration_date_font_size)
                if config.timeline_duration_date_font_size is not None
                else max(7.0, config.weekly_name_text_font_size * 0.78)
            )
        )
        if config.timeline_duration_box_height is not None:
            bar_h = max(8.0, float(config.timeline_duration_box_height))
            return title_size, notes_size, date_size, bar_h

        top_pad = max(2.0, notes_size * 0.30)
        line_gap = max(1.0, notes_size * 0.25)
        bottom_pad = max(2.0, notes_size * 0.30)
        bar_h = top_pad + title_size + line_gap + notes_size + bottom_pad
        return title_size, notes_size, date_size, bar_h

    def _min_duration_offset(self, config: "CalendarConfig", date_size: float) -> float:
        """Minimum axis-to-bar clearance so what sits under the axis stays legible.

        The clearance has to cover the timeline date labels and, when holiday
        marks are drawn, the icon-plus-date band that shares the same strip.
        """
        clearance = max(22.0, date_size * 3.2)
        if getattr(config, "timeline_show_holiday_icons", True):
            clearance = max(clearance, self._holiday_band_extent(config) + 2.0)
        return clearance

    def _draw_timeline_bands(
        self,
        config: "CalendarConfig",
        bands: list[dict],
        block_top_y: float,
        axis_left: float,
        axis_right: float,
        start: arrow.Arrow,
        end: arrow.Arrow,
        db: "CalendarDB",
        events: "list[Event] | None" = None,
    ) -> None:
        """Draw a stack of timebands using shared.timeband.build_segments().

        Each band gets a row of the configured ``row_height``. Bands are stacked
        downward starting at ``block_top_y``. Segment x positions are mapped via
        the same date→x function used by the timeline axis.

        Bands with ``unit: "icon"`` are rendered per visible day via
        :func:`shared.icon_band.compute_icon_band_days` rather than as labeled
        segments.
        """
        if not bands:
            return

        start_d = start.floor("day").date()
        end_d = end.floor("day").date()
        # visible_days for date/dow units (continuous calendar — timeline does
        # not skip weekends).
        from datetime import timedelta
        visible_days: list = []
        d = start_d
        while d <= end_d:
            visible_days.append(d)
            d = d + timedelta(days=1)

        _events: list[Event] = events or []
        _day_classes: dict = (
            {d: classify_day(d, db, config) for d in visible_days} if db is not None else {}
        )

        def _classify(day_) -> frozenset:
            return _day_classes.get(day_, frozenset())

        _band_text_style = config.get_text_style("ec-label")
        tk_band_label = self._tk("text:label")
        text_color = str(tk_band_label.get("color") or _band_text_style.color or "black")
        text_opacity = float(
            tk_band_label.get("opacity")
            if tk_band_label.get("opacity") is not None
            else _band_text_style.opacity
        )

        row_y = block_top_y
        for band in bands:
            row_h = float(band.get("row_height", 14.0))
            unit = str(band.get("unit", "week")).strip().lower()

            # ── Icon band — one cell per visible day, icons driven by rules ──
            if unit == "icon":
                icon_rules = list(band.get("icon_rules") or [])
                day_icon_map = compute_icon_band_days(
                    _events, icon_rules, visible_days, classify_fn=_classify
                )
                icon_h = float(band.get("icon_height") or row_h * 0.65)
                fill = str(band.get("fill_color") or "none")
                day_cells: list[tuple[float, float, list[tuple[str, str]]]] = []
                for day_d in visible_days:
                    day_arrow = arrow.Arrow(day_d.year, day_d.month, day_d.day)
                    next_arrow = arrow.Arrow(day_d.year, day_d.month, day_d.day).shift(days=1)
                    cell_x = self._x_for_day(day_arrow, start, end, axis_left, axis_right)
                    cell_x2 = self._x_for_day(next_arrow, start, end, axis_left, axis_right)
                    cell_w = max(0.0, cell_x2 - cell_x)
                    day_cells.append((cell_x, cell_w, day_icon_map.get(day_d, [])))
                self._draw_icon_band_row(day_cells, row_y, row_h, icon_h, fill)
                sep_y = row_y + row_h
                self._draw_line(
                    axis_left, sep_y, axis_right, sep_y,
                    stroke="#cccccc", stroke_width=0.5,
                    css_class="ec-separator",
                )
                row_y += row_h
                continue

            fill_color = str(band.get("fill_color") or "none")
            alt_fill_color = str(band.get("alt_fill_color") or "none")
            text_align = str(band.get("text_align", "center")).strip().lower()
            if text_align not in {"left", "center", "right"}:
                text_align = "center"
            band_font = str(
                band.get("font")
                or tk_band_label.get("font")
                or _band_text_style.font
                or config.timeline_text_font_name
            )
            band_font_color = str(band.get("font_color") or text_color)
            band_label_color = str(band.get("label_color") or band_font_color)
            font_size = float(
                band.get("font_size")
                or tk_band_label.get("size")
                or max(7.0, row_h * 0.55)
            )

            segments = _build_band_segments(
                band, start_d, end_d, config,
                visible_days=visible_days,
                db=db,
                week_start_default=0,
                fiscal_year_start_month_default=int(
                    getattr(config, "blockplan_fiscal_year_start_month", 2) or 2
                ),
            )

            for seg_idx, seg in enumerate(segments):
                seg_start_arrow = arrow.Arrow(seg.start.year, seg.start.month, seg.start.day)
                seg_end_arrow = arrow.Arrow(
                    seg.end_exclusive.year, seg.end_exclusive.month, seg.end_exclusive.day
                )
                x1 = self._x_for_day(seg_start_arrow, start, end, axis_left, axis_right)
                x2 = self._x_for_day(seg_end_arrow, start, end, axis_left, axis_right)
                seg_w = max(0.0, x2 - x1)
                if seg_w <= 0:
                    continue

                fill = alt_fill_color if seg_idx % 2 else fill_color
                if fill and fill.strip().lower() not in {"none", "transparent", ""}:
                    self._draw_rect(
                        x1, row_y, seg_w, row_h,
                        fill=fill,
                        fill_opacity=1.0,
                        css_class="ec-band-cell",
                    )

                label = seg.label
                if label:
                    pad = 2.0
                    if text_align == "center":
                        text_x = x1 + seg_w / 2.0
                        anchor = "middle"
                        max_w = seg_w - pad * 2
                    elif text_align == "right":
                        text_x = x2 - pad
                        anchor = "end"
                        max_w = seg_w - pad * 2
                    else:
                        text_x = x1 + pad
                        anchor = "start"
                        max_w = seg_w - pad * 2
                    self._draw_text(
                        text_x, row_y + row_h * 0.72, label,
                        band_font, font_size,
                        fill=band_label_color,
                        fill_opacity=text_opacity,
                        anchor=anchor,
                        max_width=max_w,
                        css_class="ec-label",
                    )

            sep_y = row_y + row_h
            self._draw_line(
                axis_left, sep_y, axis_right, sep_y,
                stroke="#cccccc", stroke_width=0.5,
                css_class="ec-separator",
            )
            row_y += row_h

    @staticmethod
    def _tick_label_top_clearance(
        config: "CalendarConfig", tick_bands_cfg: object
    ) -> float:
        """Maximum vertical extent (pts) of any tick band's label above the axis.

        Used to size the area above axis_y when there are no callouts/events to
        accommodate, so the axis can be raised toward the top edge while still
        leaving room for the tick labels themselves.
        """
        if not tick_bands_cfg:
            return 0.0
        bands = (
            [tick_bands_cfg]
            if isinstance(tick_bands_cfg, dict)
            else list(tick_bands_cfg)
        )
        default_label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        default_tick_h = max(6.0, config.timeline_axis_width * 2.5)
        max_above = 0.0
        for tb in bands:
            if not isinstance(tb, dict):
                continue
            tick_h = float(tb.get("tick_length") or default_tick_h)
            lsize = float(
                tb.get("label_font_size")
                or tb.get("font_size")
                or default_label_size
            )
            offset = tb.get("label_offset_y")
            gap = tb.get("label_gap")
            if offset is not None:
                lo = float(offset)
            elif gap is not None:
                lo = tick_h + float(gap)
            else:
                lo = tick_h + lsize * 1.5
            max_above = max(max_above, lo + lsize)
        return max_above

    @staticmethod
    def _tick_unit_priority(band: dict) -> int:
        """Approximate days-per-segment for a tick band's unit.

        Larger units (month) win the shared-day label over smaller ones (week,
        day). Used to deduplicate labels when two bands tick on the same date.
        """
        unit = str(band.get("unit", "date")).strip().lower()
        if unit == "interval":
            try:
                return max(1, int(band.get("interval_days", 14) or 14))
            except (TypeError, ValueError):
                return 14
        return {
            "year": 365,
            "fiscal_quarter": 91,
            "month": 30,
            "fiscal_period": 28,
            "week": 7,
            "dow": 7,
            "date": 1,
            "countdown": 1,
            "countup": 1,
        }.get(unit, 1)

    def _compute_band_ticks(
        self,
        config: "CalendarConfig",
        band: dict,
        start: arrow.Arrow,
        end: arrow.Arrow,
        db: "CalendarDB",
    ) -> list[tuple[date, str]]:
        """Return the (date, label) ticks a band would draw."""
        from datetime import timedelta

        start_d = start.floor("day").date()
        end_d = end.floor("day").date()
        visible_days: list = []
        d = start_d
        while d <= end_d:
            visible_days.append(d)
            d = d + timedelta(days=1)

        segments = _build_band_segments(
            band, start_d, end_d, config,
            visible_days=visible_days,
            db=db,
            week_start_default=0,
            fiscal_year_start_month_default=int(
                getattr(config, "blockplan_fiscal_year_start_month", 2) or 2
            ),
        )
        if not segments:
            return []

        fmt = band.get("label_format") or band.get("date_format")
        fmt_str = str(fmt) if fmt else None
        include_endpoints = bool(band.get("include_endpoints", True))

        def _format_label(d: date, fallback: str = "") -> str:
            if fmt_str:
                return format_arrow_date(arrow.get(d), fmt_str)
            return fallback

        ticks: list[tuple[date, str]] = []
        seen: set[date] = set()
        if include_endpoints:
            ticks.append((start_d, _format_label(start_d)))
            seen.add(start_d)
        for seg in segments:
            if seg.start in seen:
                continue
            ticks.append((seg.start, _format_label(seg.start, fallback=seg.label)))
            seen.add(seg.start)
        if include_endpoints and end_d not in seen:
            ticks.append((end_d, _format_label(end_d)))
        return ticks

    def _draw_axis_ticks_from_band(
        self,
        config: "CalendarConfig",
        band: dict,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        db: "CalendarDB",
        ticks: list[tuple[date, str]] | None = None,
        allowed_label_dates: set[date] | None = None,
    ) -> None:
        """Draw axis ticks at the start of each segment produced by a band dict.

        Accepts any unit supported by shared.timeband.build_segments
        (fiscal_quarter, fiscal_period, month, week, interval, date, dow,
        countdown, countup). Each segment.start gets a tick line; segment.label
        is rendered above the axis.

        Tick label_format is always an Arrow date format applied to each
        tick's own date — independent of the band's unit. This lets any
        supported unit produce date-style tick labels like "MMM D" or
        "MMMM DD". When no label_format/date_format is given, fall back to the
        segment's generated label.

        When ``allowed_label_dates`` is provided, only ticks whose date is in
        that set draw a label; the tick line is still drawn. The caller uses
        this to suppress duplicate labels when multiple bands tick on the
        same day.
        """
        if ticks is None:
            ticks = self._compute_band_ticks(config, band, start, end, db)
        if not ticks:
            return

        # Tick decoration: per-band overrides.
        _tick_style = config.get_line_style("ec-axis-tick")
        default_tick_h = max(6.0, config.timeline_axis_width * 2.5)
        tick_h = float(band.get("tick_length") or default_tick_h)
        tick_width = float(band.get("tick_width") or 1.0)
        tick_opacity = float(band.get("tick_opacity") if band.get("tick_opacity") is not None else 0.35)
        tick_color = str(band.get("tick_color") or _tick_style.color)
        tick_dash = band.get("tick_dasharray") or _tick_style.dasharray or None

        # Label styling.
        default_label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        label_size = float(
            band.get("label_font_size")
            or band.get("font_size")
            or default_label_size
        )
        draw_labels = bool(band.get("show_labels", True)) and len(ticks) <= int(
            band.get("max_label_count", 60)
        )
        tk_event_date = self._tk("text:event_date")
        label_color = str(
            band.get("label_color")
            or band.get("font_color")
            or tk_event_date.get("color")
            or _tick_style.color
        )
        label_opacity = float(
            band.get("label_opacity") if band.get("label_opacity") is not None else 0.8
        )
        font_name = str(
            band.get("font")
            or tk_event_date.get("font")
            or config.timeline_date_font
        )
        label_offset = band.get("label_offset_y")
        label_gap = band.get("label_gap")
        if label_offset is not None:
            label_offset_y = float(label_offset)
        elif label_gap is not None:
            label_offset_y = tick_h + float(label_gap)
        else:
            label_offset_y = tick_h + label_size * 1.5

        last_idx = len(ticks) - 1
        for idx, (tick_date, tick_label) in enumerate(ticks):
            tick_arrow = arrow.Arrow(tick_date.year, tick_date.month, tick_date.day)
            x = self._x_for_day(tick_arrow, start, end, axis_left, axis_right)
            self._draw_line(
                x,
                axis_y - tick_h,
                x,
                axis_y + tick_h,
                stroke=tick_color,
                stroke_width=tick_width,
                stroke_opacity=tick_opacity,
                stroke_dasharray=tick_dash,
                css_class="ec-axis-tick",
            )
            if (
                draw_labels
                and tick_label
                and (allowed_label_dates is None or tick_date in allowed_label_dates)
            ):
                if idx == 0:
                    label_anchor = "start"
                elif idx == last_idx:
                    label_anchor = "end"
                else:
                    label_anchor = "middle"
                self._draw_text(
                    x,
                    axis_y - label_offset_y,
                    tick_label,
                    font_name,
                    label_size,
                    fill=label_color,
                    fill_opacity=label_opacity,
                    anchor=label_anchor,
                    css_class="ec-label",
                )

    @staticmethod
    def _holiday_icon_size(config: "CalendarConfig") -> float:
        """Drawn height of one holiday icon; <= 0 suppresses the whole band."""
        return float(getattr(config, "timeline_holiday_icon_size", 10.0))

    @staticmethod
    def _holiday_date_font_size(config: "CalendarConfig") -> float:
        """Font size of the date printed under a holiday icon.

        Defaults to a fraction of the icon so the pair reads as one mark
        rather than as a label that happens to sit near an icon.
        """
        configured = getattr(config, "timeline_holiday_date_font_size", None)
        if configured:
            return float(configured)
        return max(6.0, TimelineRenderer._holiday_icon_size(config) * 0.68)

    def _holiday_marks(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        db: "CalendarDB",
    ) -> list[tuple[float, str, str]]:
        """Return (x, icon_name, date_label) for each government holiday.

        One mark per date: a day carrying several holidays is represented by
        the first one that is a nonworkday and has an icon, matching what the
        axis itself can show at that x.
        """
        date_format = (
            getattr(config, "timeline_holiday_date_format", None)
            or config.timeline_date_format
        )
        marks: list[tuple[float, str, str]] = []
        seen: set[str] = set()
        for day in arrow.Arrow.range("day", start.floor("day"), end.floor("day")):
            daykey = day.format("YYYYMMDD")
            if daykey in seen:
                continue
            seen.add(daykey)
            try:
                hols = db.get_holidays_for_date(daykey, config.country)
            except Exception:
                continue
            icon_name = next(
                (h.get("icon") for h in hols
                 if h.get("nonworkday") and h.get("icon")),
                None,
            )
            if not icon_name:
                continue
            marks.append(
                (
                    self._x_for_day(day, start, end, axis_left, axis_right),
                    str(icon_name),
                    format_arrow_date(day, date_format),
                )
            )
        return marks

    @staticmethod
    def _assign_holiday_date_rows(
        labels: list[tuple[float, float]],
        max_rows: int = 2,
    ) -> list[int]:
        """Place each date label on a row where it clears its neighbours.

        ``labels`` is (center_x, width) in axis order.  Holidays cluster —
        Christmas Eve and Christmas Day, Thanksgiving and the day after — so
        a single row would print those dates on top of each other.  Labels
        that fit nowhere return -1 and are left undrawn: the icon still marks
        the day, and a smeared date would say less than none.
        """
        gap = 3.0
        row_right: list[float] = []
        rows: list[int] = []
        for center_x, width in labels:
            left = center_x - width / 2.0
            for row in range(max_rows):
                if row == len(row_right):
                    row_right.append(left + width + gap)
                    rows.append(row)
                    break
                if left >= row_right[row]:
                    row_right[row] = left + width + gap
                    rows.append(row)
                    break
            else:
                rows.append(-1)
        return rows

    def _draw_holiday_icons(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        db: "CalendarDB",
    ) -> None:
        """Render each government holiday below the axis as an icon and,
        unless suppressed, the date it falls on."""
        size = self._holiday_icon_size(config)
        y_offset = float(getattr(config, "timeline_holiday_icon_y_offset", 4.0))
        if size <= 0:
            return
        color = getattr(config, "timeline_holiday_icon_color", None)
        baseline_y = axis_y + y_offset + (size * 0.80)

        marks = self._holiday_marks(
            config, start, end, axis_left, axis_right, db
        )
        for x, icon_name, _date_label in marks:
            self._draw_icon_svg(
                icon_name,
                x,
                baseline_y,
                size,
                anchor="middle",
                color=color,
                css_class="ec-holiday-icon",
            )

        if not getattr(config, "timeline_show_holiday_dates", True):
            return

        date_size = self._holiday_date_font_size(config)
        if date_size <= 0:
            return
        # ec-holiday-date is catalog-bound to text:event_date, so a theme that
        # styles event dates styles these too unless the holiday-specific
        # config field overrides it.
        _date_style = config.get_text_style("ec-holiday-date")
        font_name = _date_style.font or config.timeline_date_font
        font_path = self._safe_font_path(font_name)
        date_color = (
            getattr(config, "timeline_holiday_date_color", None)
            or _date_style.color
            or color
            or config.timeline_tick_color
        )
        # First date row clears the icon's descender; further rows stack below.
        first_baseline = axis_y + y_offset + size + (date_size * 0.95)
        row_stride = date_size * 1.15

        labelled = [(x, label) for x, _icon, label in marks if label]
        rows = self._assign_holiday_date_rows(
            [(x, string_width(label, font_path, date_size)) for x, label in labelled]
        )
        for (x, label), row in zip(labelled, rows):
            if row < 0:
                continue
            self._draw_text(
                x,
                first_baseline + (row * row_stride),
                label,
                font_name,
                date_size,
                fill=date_color,
                anchor="middle",
                css_class="ec-holiday-date",
            )

    def _holiday_band_extent(self, config: "CalendarConfig") -> float:
        """Height the holiday icons and their dates claim below the axis."""
        size = self._holiday_icon_size(config)
        if size <= 0 or not getattr(config, "timeline_show_holiday_icons", True):
            return 0.0
        y_offset = float(getattr(config, "timeline_holiday_icon_y_offset", 4.0))
        extent = y_offset + size
        if getattr(config, "timeline_show_holiday_dates", True):
            date_size = self._holiday_date_font_size(config)
            if date_size > 0:
                # Two rows are the most _assign_holiday_date_rows() will use,
                # and the last row's descenders hang below its baseline.
                extent += (date_size * 0.95) + (date_size * 1.15) + (date_size * 0.3)
        return extent

    def _draw_month_ticks(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
    ) -> None:
        """Draw month-boundary ticks on a horizontal axis; labels are
        suppressed beyond 18 ticks to avoid overlap."""
        # Default ticks to the first day of each month inside the visible range.
        month_start = start.floor("month")
        if month_start < start.floor("day"):
            month_start = month_start.shift(months=1)
        month_end = end.floor("month")
        ticks = (
            list(arrow.Arrow.range("month", month_start, month_end))
            if month_start <= month_end
            else []
        )
        if not ticks:
            return

        draw_labels = len(ticks) <= 18
        tick_h = self._axis_tick_height(config)
        label_size = self._axis_tick_label_size(config)

        _tick_style = config.get_line_style("ec-axis-tick")
        for m in ticks:
            x = self._x_for_day(m, start, end, axis_left, axis_right)
            self._draw_line(
                x,
                axis_y - tick_h,
                x,
                axis_y + tick_h,
                stroke=_tick_style.color,
                stroke_width=1.0,
                stroke_opacity=0.35,
                stroke_dasharray=_tick_style.dasharray or None,
                css_class="ec-axis-tick",
            )
            if draw_labels:
                self._draw_text(
                    x,
                    axis_y - (tick_h + label_size * 1.5),
                    format_arrow_date(m, config.timeline_tick_label_format),
                    self._tk("text:event_date").get("font") or config.timeline_date_font,
                    label_size,
                    fill=self._tk("text:event_date").get("color") or _tick_style.color,
                    fill_opacity=0.8,
                    anchor="middle",
                    css_class="ec-label",
                )

    def _draw_fiscal_bands(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
    ) -> None:
        """Draw fiscal period and/or quarter band rows above the timeline axis.

        Each band row is a sequence of colored rectangles with centered labels,
        positioned just above the month tick labels.
        """
        from shared.fiscal_renderer import (
            build_fiscal_period_segments,
            build_fiscal_quarter_segments,
        )

        tick_h = max(6.0, config.timeline_axis_width * 2.5)
        label_size = max(7.0, config.weekly_name_text_font_size * 0.8)
        band_h = label_size * 1.8
        band_gap = 2.0

        # y position: start just above the month tick label area
        # month tick labels are at axis_y - (tick_h + label_size * 1.5)
        top_of_month_labels = axis_y - (tick_h + label_size * 1.5 + label_size)
        band_bottom = top_of_month_labels - band_gap

        start_date = start.date()
        end_date = end.date()

        rows: list[list] = []
        if config.timeline_show_fiscal_quarters:
            rows.append(build_fiscal_quarter_segments(start_date, end_date, config))
        if config.timeline_show_fiscal_periods:
            rows.append(build_fiscal_period_segments(start_date, end_date, config))

        alt_colors = ["#e8eaf0", "#d4d8e8"]
        label_color = config.get_line_style("ec-axis-tick").color

        for row_idx, segments in enumerate(rows):
            row_top = band_bottom - (row_idx + 1) * (band_h + band_gap)
            row_bottom = row_top + band_h
            for seg_idx, seg in enumerate(segments):
                seg_start_arrow = arrow.get(seg.start)
                seg_end_arrow = arrow.get(seg.end_exclusive)
                x1 = self._x_for_day(seg_start_arrow, start, end, axis_left, axis_right)
                x2 = self._x_for_day(seg_end_arrow, start, end, axis_left, axis_right)
                x1 = max(x1, axis_left)
                x2 = min(x2, axis_right)
                if x2 <= x1:
                    continue
                fill = alt_colors[seg_idx % 2]
                self._draw_rect(
                    x1, row_top, x2 - x1, band_h,
                    fill=fill, fill_opacity=0.6,
                    stroke="#aaaaaa", stroke_width=0.5,
                    css_class="ec-callout-box",
                )
                cx = (x1 + x2) / 2.0
                cy = row_top + band_h / 2.0 + label_size * 0.35
                self._draw_text(
                    cx, cy, seg.label,
                    self._tk("text:event_date").get("font") or config.timeline_date_font,
                    label_size,
                    fill=label_color,
                    fill_opacity=0.9,
                    anchor="middle",
                    max_width=x2 - x1 - 4.0,
                    css_class="ec-label",
                )

    def _draw_today_marker(
        self,
        config: "CalendarConfig",
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
        axis_y: float,
        area_y: float,
        area_h: float,
    ) -> None:
        """Draw the vertical 'today' line (and its label) when today —
        or the ``timeline_today_date`` override — falls in range.
        ``timeline_today_line_direction`` (above/below/both) and
        ``_length`` (0 = full span) shape the line around the axis."""
        today = self._resolve_today(config)
        if today < start.floor("day") or today > end.floor("day"):
            return

        x = self._x_for_day(today, start, end, axis_left, axis_right)

        # Bounds within which the line may be drawn (SVG: top = small y, bottom = large y).
        area_top = area_y  # visually topmost edge (smallest SVG y)
        area_bottom = area_y + area_h  # visually bottommost edge (largest SVG y)

        direction = (config.timeline_today_line_direction or "both").strip().lower()
        length = max(0.0, config.timeline_today_line_length)

        if length == 0.0:
            # Full available span in the requested direction.
            if direction == "above":
                line_top = area_top
                line_bottom = axis_y
            elif direction == "below":
                line_top = axis_y
                line_bottom = area_bottom
            else:  # "both"
                line_top = area_top
                line_bottom = area_bottom
        else:
            if direction == "above":
                line_top = axis_y - length
                line_bottom = axis_y
            elif direction == "below":
                line_top = axis_y
                line_bottom = axis_y + length
            else:  # "both"
                half = length / 2.0
                line_top = axis_y - half
                line_bottom = axis_y + half

        # Clamp to page content area so the line never overruns the margins.
        line_top = max(line_top, area_top)
        line_bottom = min(line_bottom, area_bottom)

        _today_line_style = config.get_line_style("ec-today-line")
        _today_label_style = config.get_text_style("ec-today-label")
        self._draw_line(
            x,
            line_top,
            x,
            line_bottom,
            stroke=_today_line_style.color,
            stroke_width=1.0,
            stroke_opacity=0.55,
            stroke_dasharray=_today_line_style.dasharray or None,
            css_class="ec-today-line",
        )
        tk_today_label = self._tk("text:today_label")
        label_size = (
            tk_today_label.get("size")
            or max(7.0, config.weekly_name_text_font_size * 0.8)
        )
        preferred_y = line_top - max(0.0, config.timeline_today_label_offset_y)
        # Keep label baseline inside SVG bounds.
        min_y = label_size * 1.1
        max_y = self._page_height - (label_size * 0.6)
        if preferred_y < min_y:
            preferred_y = line_top + (label_size * 1.25)
        label_y = max(min_y, min(preferred_y, max_y))
        self._draw_text(
            x,
            label_y,
            config.timeline_today_label_text or "Today",
            tk_today_label.get("font") or _today_label_style.font or config.timeline_date_font,
            label_size,
            fill=tk_today_label.get("color") or _today_label_style.color,
            fill_opacity=0.85,
            anchor="middle",
            css_class="ec-today-label",
        )

    # _draw_circle() is inherited from BaseSVGRenderer.

    @staticmethod
    def _axis_tick_height(config: "CalendarConfig") -> float:
        """Half-length of a month tick mark, above and below the axis."""
        return max(6.0, config.timeline_axis_width * 2.5)

    @staticmethod
    def _axis_tick_label_size(config: "CalendarConfig") -> float:
        """Font size of the month tick labels."""
        return max(7.0, float(config.weekly_name_text_font_size or 10.0) * 0.8)

    def _axis_label_clearance(
        self, config: "CalendarConfig", start: arrow.Arrow, end: arrow.Arrow
    ) -> float:
        """Height the tick marks and their labels claim above the axis.

        The innermost callout row sits exactly ``layer_gap`` above the axis,
        so without this the month labels — which are drawn above the axis —
        end up printed inside that row's boxes.  Returns 0 when no labels
        will be drawn, leaving the theme's layer gap untouched.
        """
        month_start = start.floor("month")
        if month_start < start.floor("day"):
            month_start = month_start.shift(months=1)
        month_end = end.floor("month")
        tick_count = (
            len(list(arrow.Arrow.range("month", month_start, month_end)))
            if month_start <= month_end
            else 0
        )
        # Mirrors _draw_month_ticks: no ticks, or too many to label, means
        # nothing is drawn up there.
        if tick_count == 0 or tick_count > 18:
            return 0.0

        label_size = self._axis_tick_label_size(config)
        # Baseline sits at tick_h + 1.5 label heights above the axis; glyphs
        # rise about another 0.8 of the size above that baseline.
        return (
            self._axis_tick_height(config)
            + label_size * 2.3
            + _AXIS_LABEL_MARGIN
        )

    def _callout_date_label(
        self, config: "CalendarConfig", item: "TimelineCallout"
    ) -> str:
        """The date shown inside a callout box, or "" when it has none.

        Vertical timelines order their events along the axis, so the date is
        implicit there and the box carries only the name.
        """
        if item.orientation is not Orientation.HORIZONTAL:
            return ""
        return format_arrow_date(
            self._safe_day(item.event.start, fallback=arrow.now()),
            config.timeline_date_format,
        )

    def _callout_date_width(
        self, config: "CalendarConfig", date_label: str, font_size: float
    ) -> float:
        """Width the in-box date needs, including the gap before it.

        Kept in step with the layout: timeline_callout_date_extent() measures
        the same thing when sizing the box, so what is reserved here is what
        was budgeted there.
        """
        if not date_label:
            return 0.0
        return callout_date_extent(
            date_label, config.timeline_date_font, font_size
        )

    @staticmethod
    def _safe_day(date_str: str, fallback: arrow.Arrow) -> arrow.Arrow:
        try:
            return arrow.get(str(date_str)[:8], "YYYYMMDD")
        except Exception:
            return fallback

    @staticmethod
    def _resolve_today(config: "CalendarConfig") -> arrow.Arrow:
        """Resolve 'today' from config override (if set), otherwise use current date."""
        raw = (config.timeline_today_date or "").strip()
        if not raw:
            return arrow.now().floor("day")

        for fmt in ("YYYYMMDD", "YYYY-MM-DD"):
            try:
                return arrow.get(raw, fmt).floor("day")
            except Exception:
                continue
        try:
            return arrow.get(raw).floor("day")
        except Exception:
            return arrow.now().floor("day")

    @staticmethod
    def _x_for_day(
        day: arrow.Arrow,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_left: float,
        axis_right: float,
    ) -> float:
        span_days = max(1, (end.floor("day") - start.floor("day")).days)
        day_offset = (day.floor("day") - start.floor("day")).days
        clamped = max(0, min(day_offset, span_days))
        return axis_left + ((axis_right - axis_left) * (clamped / span_days))

    @staticmethod
    def _y_for_day(
        day: arrow.Arrow,
        start: arrow.Arrow,
        end: arrow.Arrow,
        axis_top: float,
        axis_bottom: float,
    ) -> float:
        """Vertical analogue of :meth:`_x_for_day`. Y increases downward
        with later dates (start at top, end at bottom)."""
        span_days = max(1, (end.floor("day") - start.floor("day")).days)
        day_offset = (day.floor("day") - start.floor("day")).days
        clamped = max(0, min(day_offset, span_days))
        return axis_top + ((axis_bottom - axis_top) * (clamped / span_days))

    @staticmethod
    def _safe_font_path(font_name: str) -> str:
        try:
            return get_font_path(font_name)
        except KeyError:
            return get_font_path("RobotoCondensed-Bold")

    def _callout_metrics(self, config: "CalendarConfig") -> tuple[float, float, float]:
        """Return (title_size, notes_size, date_size) for point-event callouts.

        Consults ``text:event_name`` / ``text:event_notes`` / ``text:event_date``
        tokens first; falls back to the legacy ``timeline_*_font_size`` fields
        and finally to the page-scaled ``weekly_name_text_font_size``.
        """
        title_size = (
            self._tk("text:event_name").get("size")
            or (
                float(config.timeline_name_text_font_size)
                if config.timeline_name_text_font_size is not None
                else max(10.0, config.weekly_name_text_font_size + 2.0)
            )
        )
        notes_size = (
            self._tk("text:event_notes").get("size")
            or (
                float(config.timeline_notes_text_font_size)
                if config.timeline_notes_text_font_size is not None
                else max(8.0, config.weekly_name_text_font_size * 0.9)
            )
        )
        date_size = (
            self._tk("text:event_date").get("size")
            or max(8.0, config.weekly_name_text_font_size * 0.95)
        )
        return title_size, notes_size, date_size
