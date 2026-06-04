# Vendored labella.py

This directory contains a vendored subset of [labella.py](https://github.com/GjjvdBurg/labella.py)
by G.J.J. van den Burg, used by CalendarApp's timeline visualizer for
VPSC-based label placement and curved leader lines.

**License:** Apache License 2.0. See [LICENSE](LICENSE).

## Why vendored

Upstream labella.py has a soft dependency on a working LaTeX installation
(`latexmk`) for text-width measurement, even when only SVG output is needed.
CalendarApp measures text via PIL (`renderers/text_utils.py::string_width`),
so we bypass labella's text-measurement path entirely and only use the
geometric primitives.

## Modifications from upstream

- **Removed `tex.py`** — LaTeX/TikZ rendering and `latexmk`-based text measurement.
- **Removed `timeline.py`** — `TimelineSVG` / `TimelineTex` orchestrators. We
  call `Force`, `Node`, and `Renderer` directly from
  `visualizers/timeline/labella_adapter.py`.
- **Removed `scale.py`** — `TimeScale` / `LinearScale`. CalendarApp supplies its
  own date-to-axis-position mapping.
- **Replaced `__init__.py`** — original imported `__version__` from a module we
  did not vendor; replacement exposes only `Force`, `Node`, `Renderer`.

All other files (`force.py`, `node.py`, `renderer.py`, `metrics.py`,
`utils.py`, `distributor.py`, `removeOverlap.py`, `vpsc.py`) are
**unmodified** from upstream master at the time of vendoring (2026-06-04).
Their original per-file docstrings preserve the upstream author and license
attribution.

## External dependency

`distributor.py` imports `intervaltree`. This is a CalendarApp project
dependency listed in `pyproject.toml`.

## Public API

```python
from vendor.labella import Force, Node, Renderer
```
