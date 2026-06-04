# -*- coding: utf-8 -*-

"""
Vendored subset of labella.py.

Upstream:  https://github.com/GjjvdBurg/labella.py
Author:    G.J.J. van den Burg
License:   Apache-2.0 (see LICENSE in this directory)
Upstream commit: master @ 2026-06-04 vendoring

Vendoring modifications by CalendarApp:
- Dropped `tex.py` (LaTeX text measurement and TikZ export — required `latexmk`).
- Dropped `timeline.py` (TimelineSVG / TimelineTex orchestrators — we use the
  lower-level primitives directly).
- Dropped `scale.py` (TimeScale / LinearScale — CalendarApp supplies its own
  date-to-position mapping).
- Replaced this `__init__.py` to skip `from .__version__ import __version__`
  (the `__version__` module was not vendored).

Public API:
    Force    — VPSC-based label position optimizer
    Node     — label node with idealPos / currentPos / width
    Renderer — leader-path generator (curved bezier connectors)
"""

from .force import Force
from .node import Node
from .renderer import Renderer

__all__ = ["Force", "Node", "Renderer"]
