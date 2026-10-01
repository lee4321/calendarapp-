"""Read and replace a value in a parsed theme by its dotted path (``candybar.row_height``)."""

from __future__ import annotations

import dataclasses
from typing import Any


def get_path(theme: Any, path: str) -> Any:
    node = theme
    for part in path.split("."):
        node = getattr(node, part)
    return node


def set_path(theme: Any, path: str, value: Any) -> Any:
    """A copy of *theme* with *path* set to *value*; the original is untouched."""
    head, _, rest = path.partition(".")
    if not rest:
        return dataclasses.replace(theme, **{head: value})
    return dataclasses.replace(theme, **{head: set_path(getattr(theme, head), rest, value)})
