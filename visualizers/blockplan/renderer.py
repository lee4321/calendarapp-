"""
Blockplan SVG renderer — a spreadsheet-like program plan.

Page anatomy (top to bottom):

    ┌────────────┬──────────────────────────────────────────┐
    │ heading    │  top time bands (one row per band dict)  │
    ├────────────┼──────────────────────────────────────────┤
    │ lane label │  swimlane 1: durations / events sections │
    │ lane label │  swimlane 2: …                           │
    ├────────────┼──────────────────────────────────────────┤
    │ heading    │  bottom time bands                       │
    └────────────┴──────────────────────────────────────────┘

The swimlane label cells occupy ``blockplan_label_column_ratio`` of the
width and the band heading cells ``blockplan_band_label_column_ratio``
(default: the same).  The timeline starts after the wider of the two and
each set of cells ends where it starts; everything right of that is the
timeline area, where X positions
come from `Span.boundary()`: each *visible* day (see
``shared.date_utils.visible_days``) gets an equal slice, so hidden
weekends take no space.

Inputs: raw event dicts (converted to ``shared.data_models.Event``),
band dicts from ``blockplan_top/bottom_time_bands``, and swimlane defs
from ``blockplan_swimlanes`` — all typically authored in a theme's
``blockplan:`` section.  Style precedence per drawn item is
token (`_tk`) → element style (``config.get_*_style``) → legacy
``blockplan_*`` config fields.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import arrow
import drawsvg

from config import role_styles
from config.config import get_font_path, resolve_continuation_icon
from renderers.svg_base import BaseSVGRenderer
from renderers.text_utils import string_width, text_center_baseline
from renderers.timescale import ScaleContext, draw_cells, draw_headings, draw_vfills, draw_vlines, plan_rows
from renderers.today_line import draw_today
from shared.data_models import Event
from shared.date_utils import format_arrow_date, visible_days
from shared.item_order import TYPE_TOKENS, sort_events, sort_key_for_stable
from shared.palettes import event_colors
from shared.rule_engine import StyleEngine, StyleResult
from shared.span import Frame, Span
from shared.wbs_filter import wbs_group, wbs_group_colors, wbs_sort_key


def _blockplan_style_rules(config: CalendarConfig) -> list:
    """The theme's conditional style rules, for the StyleEngine."""
    return role_styles.style_rules(config.theme_v3)


if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB
    from visualizers.base import CoordinateDict


class BlockPlanRenderer(BaseSVGRenderer):
    """Renderer for the blockplan spreadsheet-like visualization.

    Per-render state: `_render_content()` populates the token cache
    (``self._tokens`` via ``TOKENS`` below) and ``self._style_engine``
    (a ``StyleEngine`` over the theme's ``style_rules``); everything
    else is passed as arguments — there is no other instance state to
    initialize.  Entry point is ``render()`` on the base class, which
    calls `_render_content()` here.
    """

    # Tokens pre-resolved once per render; see BaseSVGRenderer._populate_tokens.
    TOKEN_VISUALIZER = "blockplan"
    TOKENS = (
        "text:event_name",
        "text:event_notes",
        "text:event_date",
        "text:duration_date",
        "text:band_label",
        "text:swimlane_label",
        "text:label",
        "text:heading",
        "box:band",
        "box:duration",
        "box:event",
        "box:milestone",
        "line:grid",
        "icon:event",
        "icon:milestone",
    )

    def _render_content(
        self,
        config: CalendarConfig,
        coordinates: CoordinateDict,
        events: list,
        db: CalendarDB,
    ) -> tuple[int, list]:
        """Assemble the page: bands, vertical lines, then swimlanes.

        Draw order matters — later calls paint on top:
        background → top bands → rule-driven vertical lines / column
        fills (swimlane region only) → top separator → swimlanes
        (frames, labels, durations, events) → bottom separator →
        bottom bands.  Returns ``(0, [])``: blockplan never overflows.
        """
        area_x, area_y, area_w, area_h = coordinates.get("BlockPlanArea", (0.0, 0.0, config.pageX, config.pageY))

        range_start = str(config.userstart or config.adjustedstart)
        range_end = str(config.userend or config.adjustedend)
        start = arrow.get(range_start, "YYYYMMDD").date()
        end = arrow.get(range_end, "YYYYMMDD").date()
        if end < start:
            start, end = end, start

        visible_days = self._visible_days(start, end, int(config.weekend_style))
        if not visible_days:
            return 0, []

        self._populate_tokens(config)
        self._style_engine = StyleEngine(_blockplan_style_rules(config))

        swimlanes = [dict(lane) for lane in config.theme_v3.blockplan.swimlanes]

        def _label_col_w(ratio: float) -> float:
            return min(area_w * 0.45, max(80.0, area_w * ratio))

        lane_label_w = _label_col_w(float(config.theme_v3.blockplan.label_column_ratio))
        band_ratio = config.theme_v3.blockplan.band_label_column_ratio
        band_label_w = lane_label_w if band_ratio is None else _label_col_w(float(band_ratio))
        # Bands and lanes share one timeline: it starts after the wider label
        # column, and each set of label cells ends where it starts.
        label_col_w = max(lane_label_w, band_label_w)
        timeline_x = area_x + label_col_w
        timeline_w = max(1.0, area_w - label_col_w)
        band_left_x = timeline_x - band_label_w
        lane_left_x = timeline_x - lane_label_w

        # The shared timescale: primary rows above the swimlanes, secondary below.
        # Their combined height is capped so the swimlane region keeps positive height.
        theme = config.theme_v3
        event_objects = [Event.from_dict(e) for e in events]
        span = Span(visible_days, timeline_x, timeline_x + timeline_w)
        frame = Frame(span)
        scale_ctx = ScaleContext(theme, config, db, event_objects)
        primary = plan_rows(theme.timescale.primary, span, scale_ctx, full_days=visible_days, max_height=area_h)
        secondary = plan_rows(
            theme.timescale.secondary, span, scale_ctx, full_days=visible_days, max_height=area_h - primary.height
        )
        top_bands_h = primary.height
        bottom_bands_h = secondary.height

        lanes_top = area_y + top_bands_h
        lanes_bottom = area_y + area_h - bottom_bands_h

        self._load_icon_svg_cache(db)

        # ── top rows ──────────────────────────────────────────────────────────
        draw_cells(self, primary, frame, area_y)
        draw_headings(
            self, primary, band_left_x, band_label_w, area_y, theme.timescale.heading_align, theme.boxes.header
        )

        # ── vertical lines and column fills (swimlane region only) ────────────
        for stack in (primary, secondary):
            draw_vfills(self, stack, frame, lanes_top, lanes_bottom)
            draw_vlines(self, stack, frame, lanes_top, lanes_bottom)

        # ── separator between top bands and swimlanes ─────────────────────────
        _grid_color, _grid_w, _grid_op, _grid_dash = self._grid_stroke(config)
        self._draw_line(
            area_x,
            lanes_top,
            area_x + area_w,
            lanes_top,
            stroke=_grid_color,
            stroke_width=_grid_w,
            stroke_opacity=_grid_op,
            stroke_dasharray=_grid_dash,
            css_class="ec-separator",
        )

        # ── swimlanes ─────────────────────────────────────────────────────────
        self._event_palette = event_colors(theme, db, config.get_text_style("ec-event-name").color)
        self._duration_group_colors = self._wbs_group_colors(config, event_objects, self._event_palette)
        for group, group_color in self._duration_group_colors.items():
            self._note_color(group_color, group, "wbs group")
        self._note_visible_days(day.strftime("%Y%m%d") for day in visible_days)
        lane_events = self._assign_events_to_lanes(config, event_objects, swimlanes)
        self._note_lanes(event_objects, lane_events, swimlanes)
        self._draw_swimlanes(
            config=config,
            lane_defs=lane_events,
            start=start,
            end=end,
            visible_days=visible_days,
            left_x=lane_left_x,
            timeline_x=timeline_x,
            timeline_w=timeline_w,
            top_y=lanes_top,
            bottom_y=lanes_bottom,
        )

        draw_today(self, theme, frame, lanes_top, lanes_bottom)

        # ── separator + bottom rows (drawn after swimlanes) ───────────────────
        if secondary.rows:
            self._draw_line(
                area_x,
                lanes_bottom,
                area_x + area_w,
                lanes_bottom,
                stroke=_grid_color,
                stroke_width=_grid_w,
                stroke_opacity=_grid_op,
                stroke_dasharray=_grid_dash,
                css_class="ec-separator",
            )
            draw_cells(self, secondary, frame, lanes_bottom)
            draw_headings(
                self,
                secondary,
                band_left_x,
                band_label_w,
                lanes_bottom,
                theme.timescale.heading_align,
                theme.boxes.header,
            )

        return 0, []

    def _grid_stroke(
        self,
        config: CalendarConfig,
    ) -> tuple[str, float, float, str | None]:
        """Stroke attrs for blockplan grid lines: ``line:grid``, else ``ec-grid-line``.

        The dash comes from ``line:grid`` alone; a theme may bind ``ec-grid-line``
        to a dashed calendar grid that blockplan never drew with.
        """
        tk_grid = self._tk("line:grid")
        element = config.get_line_style("ec-grid-line")
        color = tk_grid.get("color") or element.color
        width = tk_grid.get("width") if tk_grid.get("width") is not None else element.width
        opacity = tk_grid.get("opacity") if tk_grid.get("opacity") is not None else element.opacity
        dasharray = tk_grid.get("dasharray") or None
        return color, float(width), float(opacity), dasharray

    @staticmethod
    def _resolve_color_list(
        fill_color: Any,
        fill_palette: Any,
        db: CalendarDB,
    ) -> list[str]:
        """Return an ordered color list for cycling across band segments.

        Resolution priority:
        1. ``fill_color`` when it is already a list of color strings.
        2. ``fill_color`` when it is a named palette in the database.
        3. ``fill_palette`` when it is already a list of color strings.
        4. ``fill_palette`` when it is a named palette in the database.
        5. Empty list — caller should fall back to ``fill_color`` as a plain
           single-color string.
        """
        _resolver = getattr(db, "resolve_color_name", None) if db is not None else None

        def _resolve(c: str) -> str:
            return _resolver(c) if _resolver else c

        # fill_color as explicit list
        if isinstance(fill_color, list):
            colors = [_resolve(str(c)) for c in fill_color if c]
            if colors:
                return colors
        # fill_color as named palette
        if isinstance(fill_color, str) and fill_color:
            resolved = db.get_palette(fill_color)
            if resolved:
                return resolved
        # fill_palette as explicit list
        if isinstance(fill_palette, list):
            colors = [_resolve(str(c)) for c in fill_palette if c]
            if colors:
                return colors
        # fill_palette as named palette
        if isinstance(fill_palette, str) and fill_palette:
            resolved = db.get_palette(fill_palette)
            if resolved:
                return resolved
        return []

    @staticmethod
    def _event_matches_lane(event: Event, lane: dict[str, Any]) -> bool:
        """Legacy lane matcher for swimlane defs carrying a ``match:`` dict.

        Criteria (all present keys must pass; an empty match accepts
        everything): ``wbs_prefixes``, ``resource_groups``/``groups``,
        ``resource_names_contains``, ``task_contains``,
        ``notes_contains``, ``milestone``, ``rollup``,
        ``event_type`` ("duration"/"event"/"any"), and ``priority``
        (int or list) / ``priority_min`` / ``priority_max``.

        """
        match = lane.get("match", {}) if isinstance(lane, dict) else {}
        if not isinstance(match, dict) or not match:
            return True

        def _lc(v: Any) -> str:
            return str(v or "").strip().lower()

        def _list(v: Any) -> list[str]:
            if not isinstance(v, list):
                return []
            return [_lc(x) for x in v if _lc(x)]

        wbs_prefixes = _list(match.get("wbs_prefixes"))
        if wbs_prefixes:
            wbs = _lc(event.wbs)
            if not any(wbs.startswith(prefix) for prefix in wbs_prefixes):
                return False

        groups = _list(match.get("resource_groups") or match.get("groups"))
        if groups:
            group = _lc(event.resource_group)
            if group not in groups:
                return False

        resource_terms = _list(match.get("resource_names_contains"))
        if resource_terms:
            names = _lc(event.resource_names)
            if not any(term in names for term in resource_terms):
                return False

        task_terms = _list(match.get("task_contains"))
        if task_terms:
            name = _lc(event.task_name)
            if not any(term in name for term in task_terms):
                return False

        note_terms = _list(match.get("notes_contains"))
        if note_terms:
            notes = _lc(event.notes)
            if not any(term in notes for term in note_terms):
                return False

        if "milestone" in match and bool(match.get("milestone")) != bool(event.milestone):
            return False
        if "rollup" in match and bool(match.get("rollup")) != bool(event.rollup):
            return False

        event_type = _lc(match.get("event_type", "any"))
        if event_type == "duration" and not event.is_duration:
            return False
        if event_type == "event" and event.is_duration:
            return False

        # Priority filtering: exact list, exact int, or min/max range.
        priority_filter = match.get("priority")
        if priority_filter is not None:
            allowed = [int(p) for p in priority_filter] if isinstance(priority_filter, list) else [int(priority_filter)]
            if event.priority not in allowed:
                return False
        priority_min = match.get("priority_min")
        if priority_min is not None and event.priority < int(priority_min):
            return False
        priority_max = match.get("priority_max")
        return not (priority_max is not None and event.priority > int(priority_max))

    def _note_lanes(
        self,
        events: list[Event],
        lane_events: list[dict[str, Any]],
        swimlanes: list[dict[str, Any]],
    ) -> None:
        """Record each item's lane, and report every item no lane took."""
        from renderers.details_record import KIND_UNASSIGNED_LANE

        record = self._details
        if record is None:
            return
        placed: set[int] = set()
        for lane in lane_events:
            name = str(lane.get("name") or "")
            for event in [*lane["events"], *lane["durations"]]:
                placed.add(id(event))
                note = record.note_for(event)
                if name and name not in (note.lane or "").split(", "):
                    note.lane = f"{note.lane}, {name}" if note.lane else name
        if not swimlanes:
            return
        for event in events:
            if id(event) not in placed:
                record.add_exception(
                    KIND_UNASSIGNED_LANE,
                    event.task_name or "",
                    str(event.start)[:8],
                    detail="no swimlane matched it, and the unmatched lane is off",
                    event=event,
                )

    def _note_lane_bar(
        self,
        event: Event,
        color: str,
        style: StyleResult,
        group_color: str | None,
        continues_left: bool,
        continues_right: bool,
    ) -> None:
        """Record a drawn duration bar: its color, its source, and its clipping."""
        from renderers.details_record import DRAWN_PARTIAL

        note = self._details_note(event)
        if note is None:
            return
        note.assigned_color = color
        if style.fill_color:
            note.color_source = "style rule"
        elif group_color:
            note.color_source = "wbs group"
        elif event.color:
            note.color_source = "event color"
        else:
            note.color_source = "palette"
        with self._event_scope(event):
            self._note_mark("bar", color)
        if continues_left or continues_right:
            note.continues_before = note.continues_before or continues_left
            note.continues_after = note.continues_after or continues_right
            note.mark_drawn(DRAWN_PARTIAL)

    def _assign_events_to_lanes(
        self,
        config: CalendarConfig,
        events: list[Event],
        lanes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Bucket events into swimlanes; returns one dict per lane.

        Routing uses each lane def's ``match:`` dict, honoring
        ``blockplan_lane_match_mode`` ("first" or "all" — "all" lets one
        event appear in several lanes).  Events matched to no lane land
        in the optional unmatched lane
        (``blockplan_show_unmatched_lane`` / ``blockplan_unmatched_lane_name``).
        Each returned dict: {name, lane (the def), events, durations}.

        With no lane defs there are no swimlanes: every item goes into a
        single unlabeled lane.
        """
        if not lanes:
            return [
                {
                    "name": "",
                    "lane": {},
                    "events": [e for e in events if not e.is_duration and config.includeevents],
                    "durations": [e for e in events if e.is_duration and config.includedurations],
                }
            ]

        result: list[dict[str, Any]] = []
        for lane in lanes:
            name = str(lane.get("name", "Lane")).strip() or "Lane"
            result.append(
                {
                    "name": name,
                    "lane": lane,
                    "events": [],
                    "durations": [],
                }
            )

        mode = str(config.theme_v3.blockplan.lane_match_mode or "first").lower()
        unmatched_events: list[Event] = []

        for event in events:
            matched = False
            for lane in result:
                if self._event_matches_lane(event, lane["lane"]):
                    matched = True
                    if event.is_duration and config.includedurations:
                        lane["durations"].append(event)
                    elif (not event.is_duration) and config.includeevents:
                        lane["events"].append(event)
                    if mode != "all":
                        break
            if not matched:
                unmatched_events.append(event)

        if config.theme_v3.blockplan.show_unmatched_lane and unmatched_events:
            unmatched = {
                "name": config.theme_v3.blockplan.unmatched_lane_name,
                "lane": {"name": config.theme_v3.blockplan.unmatched_lane_name},
                "events": [e for e in unmatched_events if (not e.is_duration and config.includeevents)],
                "durations": [e for e in unmatched_events if (e.is_duration and config.includedurations)],
            }
            result.append(unmatched)

        return result

    @staticmethod
    def _wbs_group_colors(config: CalendarConfig, events: list[Event], palette: list[str]) -> dict[str, str]:
        """One ``palettes.event`` color per WBS group of the page's duration bars.

        Built once per page over every lane, so a family keeps its color
        across swimlanes.  Bars without a WBS are left out and keep the
        event-color / priority assignment.  ``{}`` when grouping is off.
        """
        depth = int(config.theme_v3.durations.wbs_group_depth)
        grouped = [e for e in events if e.is_duration and (e.wbs or "").strip()]
        return wbs_group_colors(grouped, depth, palette)

    @staticmethod
    def _duration_rows(
        events: list[Event],
        lane_top: float,
        lane_bottom: float,
        wbs_group_depth: int = 0,
        order: list[str | dict[str, Any]] | None = None,
    ) -> list[tuple[Event, int]]:
        """Row packing for duration bars: each bar takes the first row
        where it overlaps no bar (dates compare as YYYYMMDD strings).
        Returns (event, row_index) pairs; row count drives the per-row
        height in `_draw_lane_durations`.

        With ``wbs_group_depth`` 0 bars are placed in ``order`` (the shared
        item_placement_order).  Above 0, bars sharing their first
        ``wbs_group_depth`` WBS segments form a family, placed in WBS order
        (numeric, WBS-less bars last) — this family/leader assignment is
        blockplan's own higher-order placement and sits above the common
        sort.  A family's leaders — its rollups, or the bar whose WBS is the
        family code — go first, and its other bars are kept in rows below
        every leader, so the root reads as the family's header, with
        ``order`` as the tiebreak both within a family and for its leaders.
        Rows skipped for that stay open to other families.
        """
        if not events:
            return []

        order = order if order is not None else ["wbs", "start_date"]

        def item_key(e: Event) -> tuple:
            return sort_key_for_stable(e, order)

        groups: dict[int, str] = {}
        if wbs_group_depth > 0:
            groups = {id(e): wbs_group(e.wbs, wbs_group_depth) for e in events}

        def is_leader(e: Event) -> bool:
            group = groups.get(id(e), "")
            return bool(group) and (bool(e.rollup) or (e.wbs or "").strip() == group)

        if groups:
            ordered = sorted(
                events,
                key=lambda e: (
                    0 if groups[id(e)] else 1,
                    wbs_sort_key(groups[id(e)]),
                    0 if is_leader(e) else 1,
                    wbs_sort_key(e.wbs),
                    item_key(e),
                ),
            )
        else:
            ordered = sorted(events, key=item_key)

        row_spans: list[list[tuple[str, str]]] = []
        leader_rows: dict[str, int] = {}
        placed: list[tuple[Event, int]] = []
        for event in ordered:
            group = groups.get(id(event), "")
            row = leader_rows.get(group, -1) + 1 if group and not is_leader(event) else 0
            while row < len(row_spans) and any(
                event.start <= span_end and span_start <= event.end for span_start, span_end in row_spans[row]
            ):
                row += 1
            while len(row_spans) <= row:
                row_spans.append([])
            row_spans[row].append((event.start, event.end))
            if is_leader(event):
                leader_rows[group] = max(leader_rows.get(group, -1), row)
            placed.append((event, row))
        return placed

    @staticmethod
    def _event_rows(
        events: list[Event],
        min_separation_days: int = 2,
        order: list[str | dict[str, Any]] | None = None,
    ) -> list[tuple[Event, int]]:
        """Row packing for point events (markers + labels): an event
        joins a row only when it starts ``min_separation_days`` after
        the row's previous event, so labels don't collide."""
        if not events:
            return []
        order = order if order is not None else ["wbs", "start_date"]
        ordered = sorted(events, key=lambda e: sort_key_for_stable(e, order))
        last_start: list[str] = []
        placed: list[tuple[Event, int]] = []
        for event in ordered:
            row = 0
            while row < len(last_start):
                try:
                    d0 = arrow.get(last_start[row], "YYYYMMDD").date()
                    d1 = arrow.get(event.start, "YYYYMMDD").date()
                    if (d1 - d0).days >= min_separation_days:
                        break
                except Exception:
                    break
                row += 1
            if row == len(last_start):
                last_start.append(event.start)
            else:
                last_start[row] = event.start
            placed.append((event, row))
        return placed

    def _draw_swimlanes(
        self,
        *,
        config: CalendarConfig,
        lane_defs: list[dict[str, Any]],
        start: date,
        end: date,
        visible_days: list[date],
        left_x: float,
        timeline_x: float,
        timeline_w: float,
        top_y: float,
        bottom_y: float,
    ) -> None:
        """Draw the swimlane region: equal-height lanes between the bands.

        Each lane splits horizontally at ``split_ratio`` (per-lane
        ``split_ratio`` key, else ``blockplan_lane_split_ratio``) into an
        upper and lower content section; ``item_placement_order`` decides
        whether durations or events/milestones take the upper one.  A
        ratio of 0.0 or 1.0 removes the divider — the sections are then
        sized proportionally to how many packed rows each type needs.
        """
        lane_count = max(1, len(lane_defs))
        total_h = max(1.0, bottom_y - top_y)
        lane_h = total_h / lane_count

        # Determine from item_placement_order which content type occupies the upper section.
        # The first type token present decides; no type token → durations on top (default).
        order = list(config.theme_v3.events.item_placement_order)
        type_tokens_in_order = [t for t in order if isinstance(t, str) and t in TYPE_TOKENS]
        durations_upper = not type_tokens_in_order or type_tokens_in_order[0] == "durations"

        global_split_ratio = float(config.theme_v3.blockplan.lane_split_ratio)

        for idx, lane in enumerate(lane_defs):
            lane_top = top_y + (idx * lane_h)
            lane_bottom = lane_top + lane_h

            # Per-lane split_ratio overrides the global default.
            lane_cfg = lane.get("lane", {})
            raw_sr = lane_cfg.get("split_ratio", None)
            split_ratio = float(raw_sr if raw_sr is not None else global_split_ratio)
            split_ratio = max(0.0, min(1.0, split_ratio))

            # split = Y position of dividing line.
            # split_ratio = fraction of lane_h for the upper section.
            split = lane_top + lane_h * split_ratio
            show_split_line = 0.0 < split_ratio < 1.0

            # Per-lane visual style overrides (fall back to global config values).
            _lane_heading_cell_style = config.get_box_style("ec-heading-cell")
            _lg_color, _lg_w, _lg_op, _lg_dash = self._grid_stroke(config)
            heading_fill = lane_cfg.get("fill_color") or _lane_heading_cell_style.fill
            timeline_fill = lane_cfg.get("timeline_fill_color") or "none"

            # Lane framing
            self._draw_rect(
                left_x,
                lane_top,
                timeline_x - left_x,
                lane_h,
                fill=heading_fill,
                fill_opacity=_lane_heading_cell_style.fill_opacity,
                stroke=_lg_color,
                stroke_width=_lg_w,
                stroke_opacity=_lg_op,
                stroke_dasharray=_lg_dash,
                css_class="ec-heading-cell",
            )
            self._draw_rect(
                timeline_x,
                lane_top,
                timeline_w,
                lane_h,
                fill=timeline_fill,
                fill_opacity=config.get_box_style("ec-band-cell").fill_opacity,
                stroke=_lg_color,
                stroke_width=_lg_w,
                stroke_opacity=_lg_op,
                stroke_dasharray=_lg_dash,
                css_class="ec-band-cell",
            )
            if show_split_line:
                self._draw_line(
                    timeline_x,
                    split,
                    timeline_x + timeline_w,
                    split,
                    stroke=_lg_color,
                    stroke_width=_lg_w,
                    stroke_opacity=_lg_op,
                    stroke_dasharray=_lg_dash,
                    css_class="ec-separator",
                )

            # Lane label (single or multiline), with configurable alignment.
            self._draw_lane_label(
                config=config,
                lane_name=lane["name"],
                lane_cfg=lane_cfg,
                left_x=left_x,
                right_x=timeline_x,
                lane_bottom=lane_bottom,
                lane_top=lane_top,
            )

            durations = lane.get("durations", [])
            events = lane.get("events", [])
            if not show_split_line:
                # No divider line (ratio 0.0 or 1.0).  When both content types
                # are present, split the lane proportional to the number of rows
                # each type needs so items from different types never overlap.
                # When only one type is present, it gets the full lane.
                if durations and events:
                    dur_placed = self._duration_rows(
                        durations,
                        lane_top,
                        lane_bottom,
                        int(config.theme_v3.durations.wbs_group_depth),
                        config.theme_v3.events.item_placement_order,
                    )
                    dur_row_count = max((r for _, r in dur_placed), default=0) + 1
                    evt_row_count = (
                        max(
                            (r for _, r in self._event_rows(events, order=config.theme_v3.events.item_placement_order)),
                            default=0,
                        )
                        + 1
                    )
                    shared_row_h = lane_h / (dur_row_count + evt_row_count)
                    if durations_upper:
                        dur_sect_top = lane_top
                        dur_sect_bot = lane_top + dur_row_count * shared_row_h
                        evt_sect_top = dur_sect_bot
                        evt_sect_bot = lane_bottom
                    else:
                        evt_sect_top = lane_top
                        evt_sect_bot = lane_top + evt_row_count * shared_row_h
                        dur_sect_top = evt_sect_bot
                        dur_sect_bot = lane_bottom
                    self._draw_lane_durations(
                        config=config,
                        events=durations,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=dur_sect_top,
                        bottom=dur_sect_bot,
                    )
                    self._draw_lane_events(
                        config=config,
                        events=events,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=evt_sect_top,
                        bottom=evt_sect_bot,
                    )
                else:
                    # Only one type present — give it the full lane.
                    self._draw_lane_durations(
                        config=config,
                        events=durations,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=lane_top,
                        bottom=lane_bottom,
                    )
                    self._draw_lane_events(
                        config=config,
                        events=events,
                        start=start,
                        end=end,
                        visible_days=visible_days,
                        timeline_x=timeline_x,
                        timeline_w=timeline_w,
                        top=lane_top,
                        bottom=lane_bottom,
                    )
            elif durations_upper:
                self._draw_lane_durations(
                    config=config,
                    events=durations,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=lane_top,
                    bottom=split,
                )
                self._draw_lane_events(
                    config=config,
                    events=events,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=split,
                    bottom=lane_bottom,
                )
            else:
                self._draw_lane_events(
                    config=config,
                    events=events,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=lane_top,
                    bottom=split,
                )
                self._draw_lane_durations(
                    config=config,
                    events=durations,
                    start=start,
                    end=end,
                    visible_days=visible_days,
                    timeline_x=timeline_x,
                    timeline_w=timeline_w,
                    top=split,
                    bottom=lane_bottom,
                )

    def _draw_lane_durations(
        self,
        *,
        config: CalendarConfig,
        events: list[Event],
        start: date,
        end: date,
        visible_days: list[date],
        timeline_x: float,
        timeline_w: float,
        top: float,
        bottom: float,
    ) -> None:
        """Draw one lane section's duration bars with name/notes/dates.

        Bars are packed into rows (`_duration_rows`), clamped to the
        visible range with continuation icons when an event extends
        beyond it, and labeled inside or beside the bar depending on
        available width.
        """
        if not events:
            return
        rows = self._duration_rows(
            events,
            top,
            bottom,
            int(config.theme_v3.durations.wbs_group_depth),
            config.theme_v3.events.item_placement_order,
        )
        max_row = max((r for _, r in rows), default=0)
        row_count = max(1, max_row + 1)
        row_h = (bottom - top) / row_count
        # Bars are centred in their rows, so the space between adjacent rows'
        # bars is row_h - bar_h.  A configured row gap caps bar_h to keep it.
        row_gap = config.theme_v3.blockplan.duration_row_gap
        if row_gap is None:
            bar_h = min(float(config.theme_v3.blockplan.duration_bar_height), row_h * 0.95)
        else:
            bar_h = max(
                0.5, min(float(config.theme_v3.blockplan.duration_bar_height), row_h - max(0.0, float(row_gap)))
            )

        span = Span(visible_days, timeline_x, timeline_x + timeline_w)
        for event, row in rows:
            try:
                ev_start = arrow.get(event.start, "YYYYMMDD").date()
                ev_end = arrow.get(event.end, "YYYYMMDD").date()
            except Exception:
                continue
            if ev_end < start or ev_start > end:
                continue
            draw_start = max(ev_start, start)
            draw_end = min(ev_end, end)
            x0 = span.boundary(draw_start)
            x1 = span.boundary(draw_end + timedelta(days=1))
            w = max(2.0, x1 - x0)
            if x1 <= x0:
                continue
            has_notes = bool(event.notes and str(event.notes).strip())
            weekly_style_with_notes = bool(config.include_notes and has_notes)

            tk_event_name = self._tk("text:event_name")
            tk_event_notes = self._tk("text:event_notes")
            tk_dur_box = self._tk("box:duration")
            if weekly_style_with_notes:
                notes_font_size = float(tk_event_notes.get("size"))
            y = top + (row * row_h) + ((row_h - bar_h) / 2.0)

            _dur_bar_style = config.get_line_style("ec-duration-bar")
            _event_name_style = config.get_text_style("ec-event-name")
            _event_notes_style = config.get_text_style("ec-event-notes")
            _palette = self._event_palette or [_event_name_style.color]
            _group_colors: dict[str, str] = getattr(self, "_duration_group_colors", {})
            _group_color = _group_colors.get(wbs_group(event.wbs, int(config.theme_v3.durations.wbs_group_depth)))
            color = _group_color or event.color or _palette[event.priority % len(_palette)]
            _style_engine = getattr(self, "_style_engine", None)
            _sr = _style_engine.evaluate_event(event) if _style_engine is not None else StyleResult()
            if _sr.fill_color:
                color = _sr.fill_color
            _dur_stroke_color = tk_dur_box.get("stroke") or _dur_bar_style.color
            _dur_stroke_dash = tk_dur_box.get("dasharray") or _dur_bar_style.dasharray
            # A theme without box:duration opacities/width gets the old built-ins.
            _dur_fill_opacity = tk_dur_box.get("fill_opacity")
            if _dur_fill_opacity is None:
                _dur_fill_opacity = 0.35
            _dur_stroke_opacity = tk_dur_box.get("stroke_opacity")
            if _dur_stroke_opacity is None:
                _dur_stroke_opacity = 0.9
            _dur_stroke_width = tk_dur_box.get("stroke_width")
            if _dur_stroke_width is None:
                _dur_stroke_width = 1.0
            rect_kwargs = _sr.rect_overrides(
                fill=color,
                fill_opacity=_dur_fill_opacity,
                stroke=_dur_stroke_color,
                stroke_opacity=float(_dur_stroke_opacity),
                stroke_width=float(_dur_stroke_width),
                stroke_dasharray=_dur_stroke_dash,
            )
            self._draw_rect(
                x0,
                y,
                w,
                bar_h,
                css_class="ec-duration-bar",
                **rect_kwargs,
            )

            continues_left = ev_start < start
            continues_right = ev_end > end
            self._note_lane_bar(event, color, _sr, _group_color, continues_left, continues_right)
            if (continues_left or continues_right) and bool(config.theme_v3.continuation.show):
                cont_h = min(
                    float(config.theme_v3.continuation.icon_height),
                    bar_h,
                )
                cont_color_cfg = config.theme_v3.continuation.icon_color
                cont_color = cont_color_cfg if cont_color_cfg else color
                cont_baseline = y + bar_h * 0.5 + cont_h * 0.3
                with self._event_scope(event):
                    if continues_left:
                        self._draw_icon_svg(
                            resolve_continuation_icon(
                                config.theme_v3.continuation.icon_before,
                                "horizontal",
                                "arrow-left",
                            ),
                            x0,
                            cont_baseline,
                            cont_h,
                            anchor="start",
                            color=cont_color,
                            css_class="ec-duration-icon",
                            details_role="continuation_before",
                        )
                    if continues_right:
                        self._draw_icon_svg(
                            resolve_continuation_icon(
                                config.theme_v3.continuation.icon_after,
                                "horizontal",
                                "arrow-right",
                            ),
                            x0 + w,
                            cont_baseline,
                            cont_h,
                            anchor="end",
                            color=cont_color,
                            css_class="ec-duration-icon",
                            details_role="continuation_after",
                        )
            has_dates = bool(config.theme_v3.durations.dates.show_start or config.theme_v3.durations.dates.show_end)
            _dur_date_style = config.get_text_style("ec-duration-date")
            tk_dur_date = self._tk("text:duration_date")
            if has_dates:
                date_font_size = float(tk_dur_date.get("size"))
                date_color = tk_dur_date.get("color") or _dur_date_style.color
                date_fmt = config.theme_v3.durations.dates.format
                date_font = tk_dur_date.get("font") or _dur_date_style.font
                date_font, _, date_color, date_opacity = _sr.text_override(
                    "duration_start_date",
                    font=date_font,
                    color=date_color,
                    opacity=self._tk_opacity("text:duration_date", _dur_date_style),
                )
                try:
                    _dur_date_font_path = get_font_path(date_font)
                except Exception:
                    _dur_date_font_path = ""
                # Dates sit vertically centred on the bar.
                bar_center_y = y + bar_h / 2.0
                date_baseline_y = (
                    text_center_baseline(bar_center_y, _dur_date_font_path, date_font_size)
                    if _dur_date_font_path
                    else bar_center_y + date_font_size * 0.35
                )
            dur_text_color = tk_event_name.get("color") or _event_name_style.color
            dur_notes_color = tk_event_notes.get("color") or _event_notes_style.color
            _dur_notes_font_name = tk_event_notes.get("font") or _event_notes_style.font
            _dur_name_font, _, dur_text_color, dur_text_opacity = _sr.text_override(
                "duration_name",
                font=tk_event_name.get("font") or _event_name_style.font,
                color=dur_text_color,
                opacity=self._tk_opacity("text:event_name", _event_name_style),
            )
            _dur_notes_font_name, _, dur_notes_color, dur_notes_opacity = _sr.text_override(
                "duration_notes",
                font=_dur_notes_font_name,
                color=dur_notes_color,
                opacity=self._tk_opacity("text:event_notes", _event_notes_style),
            )
            show_icon = bool(config.theme_v3.durations.show_icons) and bool(event.icon)
            event_icon_to_draw = _sr.icon if _sr.icon is not None else event.icon
            event_icon_color = _sr.icon_color or dur_text_color

            # --- shared icon-layout helper ---
            # The loop values are bound as defaults so the helper can only
            # ever see this iteration's duration.
            def _draw_icon_and_text(
                center_y: float,
                font_size: float,
                max_w: float,
                *,
                event=event,
                x0=x0,
                w=w,
                show_icon=show_icon,
                event_icon_to_draw=event_icon_to_draw,
                event_icon_color=event_icon_color,
                _event_name_style=_event_name_style,
                _dur_name_font=_dur_name_font,
                dur_text_color=dur_text_color,
                dur_text_opacity=dur_text_opacity,
            ) -> None:
                """Draw icon (if show_icon) + task name, both vertically centred on *center_y*."""
                try:
                    baseline_y = text_center_baseline(center_y, get_font_path(_dur_name_font), font_size)
                except Exception:
                    baseline_y = center_y + font_size * 0.35
                if show_icon:
                    icon_size = font_size
                    try:
                        _fp = get_font_path(_event_name_style.font)
                        text_w = string_width(event.task_name, _fp, font_size)
                    except Exception:
                        text_w = len(event.task_name) * font_size * 0.55
                    gap = 2.0
                    total_w = icon_size + gap + text_w
                    available_w = max(8.0, max_w)
                    icon_scale_x = min(1.0, available_w / total_w) if total_w > available_w else 1.0
                    effective_icon_w = icon_size * icon_scale_x
                    group_x0 = (
                        x0
                        + (
                            w
                            - (
                                effective_icon_w
                                + gap
                                + min(
                                    text_w * icon_scale_x,
                                    available_w - effective_icon_w - gap,
                                )
                            )
                        )
                        / 2.0
                    )
                    draw_x = max(x0, group_x0)
                    icon_baseline_y = self._icon_baseline(center_y, icon_size)
                    icon_transform = None
                    if icon_scale_x < 1.0:
                        icon_transform = (
                            f"translate({draw_x:.4f} {icon_baseline_y:.4f}) "
                            f"scale({icon_scale_x:.6f} 1) "
                            f"translate({-draw_x:.4f} {-icon_baseline_y:.4f})"
                        )
                    with self._event_scope(event):
                        icon_drawn = self._draw_icon_svg(
                            event_icon_to_draw,
                            draw_x,
                            icon_baseline_y,
                            icon_size,
                            anchor="start",
                            color=event_icon_color,
                            fallback_name=config.theme_v3.icons.missing.name,
                            fallback_size=config.theme_v3.icons.missing.size,
                            fallback_color=event_icon_color,
                            transform=icon_transform,
                            css_class="ec-event-icon",
                            box_token="box:duration",
                            box_ctx=self._event_ctx(event),
                            details_role="duration",
                        )
                    text_x = draw_x + effective_icon_w + gap if icon_drawn else x0 + (w / 2.0)
                    self._draw_text(
                        text_x,
                        baseline_y,
                        event.task_name,
                        _dur_name_font,
                        font_size,
                        fill=dur_text_color,
                        fill_opacity=dur_text_opacity,
                        anchor="start" if icon_drawn else "middle",
                        max_width=max(8.0, x0 + w - text_x - 2),
                        css_class="ec-event-name",
                    )
                else:
                    self._draw_text(
                        x0 + (w / 2.0),
                        baseline_y,
                        event.task_name,
                        _dur_name_font,
                        font_size,
                        fill=dur_text_color,
                        fill_opacity=dur_text_opacity,
                        anchor="middle",
                        max_width=max(8.0, max_w),
                        css_class="ec-event-name",
                    )

            if weekly_style_with_notes:
                # Name centred in the bar's upper half, notes in its lower half.
                _draw_icon_and_text(y + (bar_h * 0.25), notes_font_size, w - 4)
                _notes_size = float(tk_event_notes.get("size"))
                _notes_center_y = y + (bar_h * 0.75)
                try:
                    _notes_baseline_y = text_center_baseline(
                        _notes_center_y, get_font_path(_dur_notes_font_name), _notes_size
                    )
                except Exception:
                    _notes_baseline_y = _notes_center_y + _notes_size * 0.35
                self._draw_text(
                    x0 + (w / 2.0),
                    _notes_baseline_y,
                    str(event.notes),
                    _dur_notes_font_name,
                    float(tk_event_notes.get("size")),
                    fill=dur_notes_color,
                    fill_opacity=dur_notes_opacity,
                    anchor="middle",
                    max_width=max(8.0, w - 4),
                    css_class="ec-event-notes",
                )
            else:
                _draw_icon_and_text(
                    y + (bar_h / 2.0),
                    float(tk_event_name.get("size")),
                    w - 4,
                )

            # --- Start/end dates at the bar's ends — shared for both layout modes ---
            if has_dates:
                show_start = config.theme_v3.durations.dates.show_start
                show_end = config.theme_v3.durations.dates.show_end
                both = show_start and show_end
                half_w = max(8.0, w / 2.0 - 4)

                start_label = end_label = ""
                if show_start:
                    try:
                        start_label = format_arrow_date(arrow.get(ev_start), date_fmt)
                    except Exception:
                        start_label = str(ev_start)
                if show_end:
                    try:
                        end_label = format_arrow_date(arrow.get(ev_end), date_fmt)
                    except Exception:
                        end_label = str(ev_end)

                # Compute a shared scale so both dates squish uniformly.
                shared_scale = 1.0
                if both and _dur_date_font_path:
                    s_w = string_width(start_label, _dur_date_font_path, date_font_size) if start_label else 0.0
                    e_w = string_width(end_label, _dur_date_font_path, date_font_size) if end_label else 0.0
                    scale_s = min(1.0, half_w / s_w) if s_w > half_w else 1.0
                    scale_e = min(1.0, half_w / e_w) if e_w > half_w else 1.0
                    shared_scale = min(scale_s, scale_e)

                if show_start:
                    sx = x0 + 2.0
                    xform = None
                    if both and shared_scale < 1.0:
                        xform = (
                            f"translate({sx:.4f} {date_baseline_y:.4f}) "
                            f"scale({shared_scale:.6f} 1) "
                            f"translate({-sx:.4f} {-date_baseline_y:.4f})"
                        )
                    self._draw_text(
                        sx,
                        date_baseline_y,
                        start_label,
                        date_font,
                        date_font_size,
                        fill=date_color,
                        fill_opacity=date_opacity,
                        anchor="start",
                        max_width=None if both else half_w,
                        transform=xform,
                        css_class="ec-duration-date",
                    )
                if show_end:
                    ex = x0 + w - 2.0
                    xform = None
                    if both and shared_scale < 1.0:
                        xform = (
                            f"translate({ex:.4f} {date_baseline_y:.4f}) "
                            f"scale({shared_scale:.6f} 1) "
                            f"translate({-ex:.4f} {-date_baseline_y:.4f})"
                        )
                    self._draw_text(
                        ex,
                        date_baseline_y,
                        end_label,
                        date_font,
                        date_font_size,
                        fill=date_color,
                        fill_opacity=date_opacity,
                        anchor="end",
                        max_width=None if both else half_w,
                        transform=xform,
                        css_class="ec-duration-date",
                    )

    def _draw_lane_events(
        self,
        *,
        config: CalendarConfig,
        events: list[Event],
        start: date,
        end: date,
        visible_days: list[date],
        timeline_x: float,
        timeline_w: float,
        top: float,
        bottom: float,
    ) -> None:
        """Draw one lane section's point events: marker/icon + stacked
        name, optional notes, and date text at the event's day position.
        Row packing via `_event_rows` keeps nearby labels apart."""
        if not events or self._drawing is None:
            return

        ordered = sort_events(events, config.theme_v3.events.item_placement_order)
        _evt_name_style = config.get_text_style("ec-event-name")
        _evt_notes_style = config.get_text_style("ec-event-notes")
        _evt_date_style = config.get_text_style("ec-event-date")
        tk_event_name = self._tk("text:event_name")
        tk_event_notes = self._tk("text:event_notes")
        tk_event_date = self._tk("text:event_date")
        event_size = float(tk_event_name.get("size"))
        notes_size = float(tk_event_notes.get("size"))
        date_size = float(tk_event_date.get("size") or max(6.0, event_size * 0.9))
        show_date = bool(config.theme_v3.events.date.show)
        icon_r = max(1.5, float(config.theme_v3.events.marker.radius))
        _evt_name_font = tk_event_name.get("font") or _evt_name_style.font
        try:
            event_font_path = get_font_path(_evt_name_font)
        except Exception:
            event_font_path = ""
        _event_notes_font_name = tk_event_notes.get("font") or _evt_notes_style.font
        _event_notes_color = tk_event_notes.get("color") or _evt_notes_style.color
        try:
            notes_font_path = get_font_path(_event_notes_font_name)
        except Exception:
            notes_font_path = event_font_path
        _evt_date_font = tk_event_date.get("font") or _evt_date_style.font
        try:
            date_font_path = get_font_path(_evt_date_font)
        except Exception:
            date_font_path = event_font_path

        # Each row keeps the occupied [x0,x1] spans already placed on that row.
        row_spans: list[list[tuple[float, float]]] = []
        placements: list[tuple[Event, int, float, bool, bool, str]] = []
        visible_set = set(visible_days)
        span = Span(visible_days, timeline_x, timeline_x + timeline_w)

        for event in ordered:
            try:
                ev_day = arrow.get(event.start, "YYYYMMDD").date()
            except Exception:
                continue
            if ev_day < start or ev_day > end:
                continue
            if ev_day not in visible_set:
                continue
            x = span.boundary(ev_day)
            has_notes = bool(config.include_notes and event.notes and str(event.notes).strip())
            has_date = show_date
            date_text = ""
            if has_date:
                try:
                    date_text = format_arrow_date(
                        arrow.get(event.start, "YYYYMMDD"),
                        config.theme_v3.events.date.format,
                    )
                except Exception:
                    date_text = str(event.start)
            name_w = (
                string_width(event.task_name, event_font_path, event_size)
                if event_font_path
                else (len(event.task_name) * event_size * 0.55)
            )
            notes_w = (
                string_width(str(event.notes), notes_font_path, notes_size)
                if (has_notes and notes_font_path)
                else (len(str(event.notes or "")) * notes_size * 0.52)
            )
            date_w = (
                string_width(date_text, date_font_path, date_size)
                if (has_date and date_font_path)
                else (len(date_text) * date_size * 0.52)
            )
            label_w = max(name_w, notes_w if has_notes else 0.0, date_w if has_date else 0.0)
            span_x0 = x - icon_r - 2.0
            span_x1 = x + icon_r + 4.0 + label_w
            pad = 4.0

            target_row = 0
            while True:
                if target_row >= len(row_spans):
                    row_spans.append([])
                overlaps = any(not ((span_x1 + pad) <= x0 or span_x0 >= (x1 + pad)) for x0, x1 in row_spans[target_row])
                if not overlaps:
                    row_spans[target_row].append((span_x0, span_x1))
                    placements.append((event, target_row, x, has_notes, has_date, date_text))
                    break
                target_row += 1

        row_count = max(1, len(row_spans))
        row_h = (bottom - top) / row_count

        _style_engine = getattr(self, "_style_engine", None)
        for event, row, x, has_notes, has_date, date_text in placements:
            y_center = top + ((row + 0.5) * row_h)
            marker_drawn = False
            icon_size = max(6.0, event_size * 1.1)

            event_color = tk_event_name.get("color") or _evt_name_style.color
            _sr = _style_engine.evaluate_event(event) if _style_engine is not None else StyleResult()
            if _sr.fill_color:
                event_color = _sr.fill_color
            ev_name_font, _, ev_name_color, ev_name_opacity = _sr.text_override(
                "event_name",
                font=_evt_name_font,
                color=event_color,
                opacity=self._tk_opacity("text:event_name", _evt_name_style),
            )
            ev_notes_font, _, ev_notes_color, ev_notes_opacity = _sr.text_override(
                "event_notes",
                font=_event_notes_font_name,
                color=_event_notes_color,
                opacity=self._tk_opacity("text:event_notes", _evt_notes_style),
            )
            ev_date_font, _, ev_date_color, ev_date_opacity = _sr.text_override(
                "event_date",
                font=_evt_date_font,
                color=tk_event_date.get("color") or _evt_date_style.color,
                opacity=self._tk_opacity("text:event_date", _evt_date_style),
            )
            ev_icon_to_draw = _sr.icon if _sr.icon is not None else event.icon
            ev_icon_color = _sr.icon_color or event_color
            ev_marker_stroke = _sr.stroke_color if _sr.stroke_color is not None else event_color
            if has_notes and has_date:
                name_baseline = y_center - (event_size * 0.70)
                notes_baseline = y_center + (notes_size * 0.15)
                date_baseline = y_center + (notes_size * 1.30)
            elif has_notes:
                date_baseline = None
                name_baseline = y_center - (event_size * 0.35)
                notes_baseline = y_center + (notes_size * 0.85)
            elif has_date:
                # Date sits above the name (smaller Y in SVG = higher on page)
                date_baseline = y_center - (date_size * 0.85)
                name_baseline = y_center + (event_size * 0.35)
                notes_baseline = None
            else:
                date_baseline = None
                name_baseline = y_center + (event_size * 0.35)
                notes_baseline = None
            if ev_icon_to_draw:
                with self._event_scope(event):
                    marker_drawn = self._draw_icon_svg(
                        ev_icon_to_draw,
                        x,
                        name_baseline,
                        icon_size,
                        anchor="start",
                        color=ev_icon_color,
                        fallback_name=config.theme_v3.icons.missing.name,
                        fallback_size=config.theme_v3.icons.missing.size,
                        fallback_color=config.theme_v3.icons.missing.color,
                        css_class="ec-event-icon",
                        box_token="box:milestone" if getattr(event, "milestone", False) else "box:event",
                        box_ctx=self._event_ctx(event),
                        details_role="milestone" if getattr(event, "milestone", False) else "event",
                    )

            if not marker_drawn:
                _circle = drawsvg.Circle(
                    x,
                    y_center,
                    icon_r,
                    fill=event_color,
                    stroke=ev_marker_stroke,
                    class_="ec-milestone-marker",
                )
                self.drawing.append(_circle)
                with self._event_scope(event):
                    self._note_mark("dot", event_color, "milestone" if event.milestone else "event")
            marker_extent = icon_size if marker_drawn else icon_r
            label_x = x + marker_extent + 2.0
            max_width = max(8.0, (timeline_x + timeline_w) - x - 6)
            if has_date and date_baseline is not None:
                self._draw_text(
                    label_x,
                    date_baseline,
                    date_text,
                    ev_date_font,
                    date_size,
                    fill=ev_date_color,
                    fill_opacity=ev_date_opacity,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-date",
                )
            if has_notes:
                self._draw_text(
                    label_x,
                    name_baseline,
                    event.task_name,
                    ev_name_font,
                    event_size,
                    fill=ev_name_color,
                    fill_opacity=ev_name_opacity,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-name",
                )
                self._draw_text(
                    label_x,
                    notes_baseline if notes_baseline is not None else y_center - (notes_size * 0.85),
                    str(event.notes),
                    ev_notes_font,
                    notes_size,
                    fill=ev_notes_color,
                    fill_opacity=ev_notes_opacity,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-notes",
                )
            else:
                self._draw_text(
                    label_x,
                    name_baseline,
                    event.task_name,
                    ev_name_font,
                    event_size,
                    fill=ev_name_color,
                    fill_opacity=ev_name_opacity,
                    anchor="start",
                    max_width=max_width,
                    css_class="ec-event-name",
                )

    # Day-axis visibility lives in shared/date_utils.visible_days().
    _visible_days = staticmethod(visible_days)

    def _draw_lane_label(
        self,
        *,
        config: CalendarConfig,
        lane_name: str,
        lane_cfg: dict[str, Any],
        left_x: float,
        right_x: float,
        lane_bottom: float,
        lane_top: float,
    ) -> None:
        """Draw the heading-column lane label (multi-line supported).

        Alignment comes from per-lane ``label_align_h``/``label_align_v``
        falling back to the global ``blockplan_lane_label_align_*``;
        color from per-lane ``label_color`` → ``text:swimlane_label``
        token → the ec-label element style.  ``label_rotation`` (per-lane
        or global) rotates around the cell center.
        """
        text = str(lane_name or "")
        lines = [ln for ln in text.splitlines() if ln != ""]
        if not lines:
            return

        tk_swimlane_label = self._tk("text:swimlane_label")
        tk_event_name = self._tk("text:event_name")
        fs = float(tk_swimlane_label.get("size") or tk_event_name.get("size") or 9.0)
        line_gap = fs * 1.20
        total_baseline_span = (len(lines) - 1) * line_gap

        # ── rotation ───────────────────────────────────────────────────────────
        raw_rot = lane_cfg.get("label_rotation")
        if raw_rot is None:
            raw_rot = config.theme_v3.blockplan.lane_label_rotation
        rotation = float(raw_rot or 0.0)
        cell_cx = (left_x + right_x) / 2.0
        cell_cy = (lane_top + lane_bottom) / 2.0
        xform = f"rotate({rotation:.6g},{cell_cx:.4f},{cell_cy:.4f})" if rotation else None
        # For ±90° rotations the text runs along the lane height, so clamp
        # max_width to the lane height rather than the narrow column width.
        cross_axis = 45.0 < abs(rotation % 180.0) < 135.0

        align_h = (
            str(
                lane_cfg.get("label_align_h", config.theme_v3.blockplan.lane_label_align_h)
                or config.theme_v3.blockplan.lane_label_align_h
            )
            .strip()
            .lower()
        )
        align_v = (
            str(
                lane_cfg.get("label_align_v", config.theme_v3.blockplan.lane_label_align_v)
                or config.theme_v3.blockplan.lane_label_align_v
            )
            .strip()
            .lower()
        )
        align_h = {"start": "left", "middle": "center", "end": "right"}.get(align_h, align_h)
        if align_h not in {"left", "center", "right"}:
            align_h = "left"
        if align_v not in {"top", "middle", "bottom"}:
            align_v = "middle"

        if align_h == "center":
            x = left_x + ((right_x - left_x) * 0.5)
            anchor = "middle"
        elif align_h == "right":
            x = right_x - 6.0
            anchor = "end"
        else:
            x = left_x + 6.0
            anchor = "start"

        if align_v == "top":
            first_baseline = lane_top + (fs * 0.85)
        elif align_v == "bottom":
            last_baseline = lane_bottom - (fs * 0.25)
            first_baseline = last_baseline - total_baseline_span
        else:
            lane_mid = (lane_top + lane_bottom) / 2.0
            first_baseline = lane_mid - (total_baseline_span * 0.5)

        _lane_label_style = config.get_text_style("ec-heading")
        label_color = lane_cfg.get("label_color") or tk_swimlane_label.get("color") or _lane_label_style.color
        label_font = tk_swimlane_label.get("font") or _lane_label_style.font
        # Lane labels take the band-heading token's opacity; a per-lane
        # label_opacity would mirror band.label_opacity if one is ever wanted.
        label_opacity = self._tk_opacity("text:swimlane_label", _lane_label_style)
        max_width = max(8.0, lane_bottom - lane_top - 10.0) if cross_axis else max(8.0, right_x - left_x - 10.0)
        for i, line in enumerate(lines):
            y = first_baseline + (i * line_gap)
            self._draw_text(
                x,
                y,
                line,
                label_font,
                fs,
                fill=label_color,
                fill_opacity=label_opacity,
                anchor=anchor,
                max_width=max_width,
                transform=xform,
                css_class="ec-heading",
            )

    @staticmethod
    def _normalize_halign(value: str | None, default: str = "left") -> str:
        v = str(value or default).strip().lower()
        return v if v in {"left", "center", "right"} else default
