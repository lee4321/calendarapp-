"""
Base classes and protocols for visualization components.

This module defines the abstract interfaces that all visualizers must implement,
enabling a pluggable architecture for different calendar visualization formats.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB


# Type aliases for coordinate tuples
# Coordinates are in SVG space: origin top-left, Y increases downward.
# y is the top edge of the element.
Coordinate = tuple[float, float, float, float]  # (x, y, width, height)
CoordinateDict = dict[str, Coordinate]


def filter_events(events: list[dict], config: "CalendarConfig") -> list[dict]:
    """
    Return only the events from *events* that should appear in a rendered output.

    This is the single authoritative filter used by every visualizer and by the
    ``exportdata`` CLI subcommand, so both code paths always produce identical
    results.

    Filters applied (in order):

    * Holidays (``Notes`` in ``'HOLIDAY'``, ``'USFederal'``, ``'CanFED'``) are
      always excluded — they are rendered as day-box decorations, not event rows.
    * ``config.ignorecomplete`` — skip items with ``Percent_Complete == 1``.
    * ``config.milestones``     — keep **only** items where ``Milestone`` is truthy.
    * ``config.rollups``        — keep **only** items where ``Rollup`` is truthy.
    * ``config.WBS``            — WBS pattern filter (``WBSFilter`` expression).
    * ``config.includeevents``  — skip single-day items when ``False``.
    * ``config.includedurations`` — skip multi-day items when ``False``.

    The WBS compiled filter is cached on the config object (``_wbs_filter`` /
    ``_wbs_filter_raw``) to avoid re-parsing on every call.
    """
    from shared.wbs_filter import WBSFilter  # local import avoids circular deps

    # Compile (and cache) the WBS filter once per config.WBS value.
    # CalendarConfig is a plain (non-frozen) dataclass so setattr is safe.
    wbs_compiled = None
    if config.WBS:
        if getattr(config, "_wbs_filter_raw", None) != config.WBS:
            setattr(config, "_wbs_filter", WBSFilter.parse(config.WBS))
            setattr(config, "_wbs_filter_raw", config.WBS)
        wbs_compiled = getattr(config, "_wbs_filter", None)

    result: list[dict] = []
    for ev in events:
        # --- holidays always excluded ---
        if ev.get("Notes") in ("HOLIDAY", "USFederal", "CanFED"):
            continue

        # --- config-level content filters ---
        if config.ignorecomplete and ev.get("Percent_Complete") == 1:
            continue
        if config.milestones and not ev.get("Milestone"):
            continue
        if config.rollups and not ev.get("Rollup"):
            continue
        if wbs_compiled and not wbs_compiled.matches(ev.get("WBS")):
            continue

        # --- event-type filters ---
        start = ev.get("Start") or ev.get("Start_Date", "")
        end = ev.get("End") or ev.get("Finish_Date", "")
        is_duration = start != end
        if is_duration and not config.includedurations:
            continue
        if not is_duration and not config.includeevents:
            continue

        result.append(ev)
    return result


@dataclass
class VisualizationResult:
    """Result of visualization generation."""

    output_path: str
    page_count: int = 1
    event_count: int = 0
    overflow_count: int = 0
    warnings: list[str] = field(default_factory=list)


@runtime_checkable
class Visualizer(Protocol):
    """Protocol defining the visualization interface."""

    @property
    def name(self) -> str:
        """Human-readable name of the visualization type."""
        ...

    @property
    def supported_options(self) -> list[str]:
        """List of CLI option names this visualizer supports."""
        ...

    def validate_config(self, config: CalendarConfig) -> list[str]:
        """
        Validate configuration for this visualizer.

        Args:
            config: Calendar configuration to validate

        Returns:
            List of warning/error messages (empty if valid)
        """
        ...

    def generate(
        self,
        config: CalendarConfig,
        db: CalendarDB,
    ) -> VisualizationResult:
        """
        Generate the visualization and return result.

        Args:
            config: Calendar configuration
            db: Database access instance

        Returns:
            Result containing output path and statistics
        """
        ...


class BaseLayout(ABC):
    """Abstract base class for layout calculation."""

    @abstractmethod
    def calculate(self, config: CalendarConfig) -> CoordinateDict:
        """
        Calculate all coordinates for the visualization.

        Args:
            config: Calendar configuration with page size, margins, etc.

        Returns:
            Dict mapping element names to coordinate tuples (x, y, width, height)
            where y is the top edge in SVG space (origin top-left, Y increases downward).
        """
        pass

    def _to_svg_coords(
        self, coords: CoordinateDict, page_height: float
    ) -> CoordinateDict:
        """
        Convert CoordinateDict from PDF space (y=bottom edge, Y-up) to SVG space
        (y=top edge, Y-down).

        Apply once at the end of calculate() after all internal layout math is done
        in the familiar PDF coordinate system.
        """
        return {
            key: (x, page_height - y - h, w, h) for key, (x, y, w, h) in coords.items()
        }

    def _calculate_margins(self, config: CalendarConfig) -> dict:
        """
        Calculate page margins - shared logic for all layouts.

        Args:
            config: Calendar configuration

        Returns:
            Dict with margin dimensions and usable area
        """
        from config.config import resolve_page_margins

        return resolve_page_margins(config)

    def _calculate_header_footer(
        self,
        config: CalendarConfig,
        margins: dict,
    ) -> dict:
        """
        Calculate header and footer positions - shared logic.

        Args:
            config: Calendar configuration
            margins: Margin dimensions from _calculate_margins

        Returns:
            Dict with header_height and footer_height
        """
        result = {"header_height": 0.0, "footer_height": 0.0}

        if config.include_header:
            result["header_height"] = round(config.pageY * config.header_percent, 2)

        if config.include_footer:
            result["footer_height"] = round(config.pageY * config.footer_percent, 2)

        return result

    def _generate_three_column_coords(
        self,
        margin: float,
        page_width: float,
        y: float,
        height: float,
        prefix: str,
        right_margin: float | None = None,
    ) -> dict:
        """
        Generate coordinates for a three-column header or footer.

        Args:
            margin: Left page margin width
            page_width: Total page width
            y: Y coordinate for the row
            height: Height of the row
            prefix: Label prefix, e.g. "Header" or "Footer"
            right_margin: Right page margin width (defaults to left margin)

        Returns:
            Dict with keys like "HeaderLeft", "HeaderCenter", "HeaderRight"
        """
        rmargin = margin if right_margin is None else right_margin
        usable_width = page_width - margin - rmargin
        col_width = round(usable_width / 3, 2)
        return {
            f"{prefix}Left": (margin, y, col_width, height),
            f"{prefix}Center": (round(margin + col_width, 2), y, col_width, height),
            f"{prefix}Right": (
                round(margin + 2 * col_width, 2),
                y,
                col_width,
                height,
            ),
        }


class BaseVisualizer(ABC):
    """
    Abstract base class implementing common visualizer functionality.

    Uses the Template Method pattern to define the visualization workflow
    while allowing subclasses to customize specific steps.
    """

    def __init__(self):
        """Initialize the visualizer."""
        self._layout: BaseLayout | None = None
        self._renderer = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the visualization type."""
        pass

    @property
    def supported_options(self) -> list[str]:
        """
        Default common options supported by all visualizers.

        Override to add view-specific options.
        """
        return [
            "papersize",
            "orientation",
            "margin",
            "header",
            "footer",
            "watermark_text",
            "watermark_image",
        ]

    def validate_config(self, config: CalendarConfig) -> list[str]:
        """
        Base validation - can be extended by subclasses.

        Args:
            config: Calendar configuration to validate

        Returns:
            List of warning messages
        """
        warnings = []

        if not config.adjustedstart or not config.adjustedend:
            warnings.append("Date range not calculated")

        if config.pageX <= 0 or config.pageY <= 0:
            warnings.append("Invalid page dimensions")

        return warnings

    @abstractmethod
    def _create_layout(self) -> BaseLayout:
        """
        Factory method for layout calculator.

        Returns:
            Layout calculator instance for this visualization type
        """
        pass

    @abstractmethod
    def _create_renderer(self):
        """
        Factory method for renderer.

        Returns:
            Renderer instance for this visualization type
        """
        pass

    def generate(
        self,
        config: CalendarConfig,
        db: CalendarDB,
    ) -> VisualizationResult:
        """
        Template Method pattern for visualization workflow.

        Steps:
        1. Prepare data (query DB, filter events)
        2. Calculate layout (coordinates)
        3. Render to SVG
        4. Return result

        Args:
            config: Calendar configuration
            db: Database access instance

        Returns:
            Result containing output path and statistics
        """
        # Step 1: Prepare data
        events = self._prepare_data(config, db)

        # Step 2: Calculate layout
        self._layout = self._create_layout()
        coordinates = self._layout.calculate(config)

        # Step 3: Render
        self._renderer = self._create_renderer()
        result = self._renderer.render(
            config=config,
            coordinates=coordinates,
            events=events,
            db=db,
        )

        return result

    def _prepare_data(
        self,
        config: CalendarConfig,
        db: CalendarDB,
    ) -> list:
        """
        Prepare event data from database.

        Args:
            config: Calendar configuration
            db: Database access instance

        Returns:
            List of filtered event dictionaries
        """
        events = db.get_all_events_in_range(
            config.adjustedstart,
            config.adjustedend,
        )
        return self._filter_events(events, config)

    def _filter_events(
        self,
        events: list,
        config: CalendarConfig,
    ) -> list:
        """Delegate to the module-level :func:`filter_events` helper."""
        return filter_events(events, config)

    def _should_include_event(
        self,
        event: dict,
        config: CalendarConfig,
    ) -> bool:
        """
        Check if a single event passes all active filters.

        Delegates to :func:`filter_events` for consistency; kept for
        backwards-compatibility with any subclass that may override it.
        """
        return bool(filter_events([event], config))
