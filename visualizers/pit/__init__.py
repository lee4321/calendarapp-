"""
PIT (Points in Time) visualizer.

A labella-driven SVG timeline focused on single-day events and milestones,
with both horizontal and vertical axis directions. Sibling to the existing
`timeline` visualizer, which retains duration-bar / rollup / icon-band
support.

Public entry points are reached through the VisualizerFactory; this
module is not intended to be imported directly by user code.
"""

from __future__ import annotations
