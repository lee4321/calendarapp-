"""Text measurement must use Pillow's RAQM layout engine.

PyPI's Pillow wheels ship without libraqm, and Pillow then silently falls back
to the BASIC engine: advances are rounded to whole pixels and kerning is
ignored, which shifts every rendered label.  pyproject.toml builds Pillow from
source (``[tool.uv] no-binary-package``) against the system libraqm; these
tests fail if that build lost it.
"""

from __future__ import annotations

import pytest
from PIL import ImageFont, features

from config.config import get_font_path
from renderers.text_utils import string_width


def test_pillow_has_raqm():
    assert features.check("raqm"), (
        "Pillow was built without libraqm - install it (macOS: "
        "`brew install libraqm`) and rebuild: "
        "`uv sync --reinstall-package pillow`"
    )


def test_font_loads_use_the_raqm_engine():
    font = ImageFont.truetype(get_font_path("Roboto-Bold"), 12)
    assert font.layout_engine == ImageFont.Layout.RAQM


@pytest.mark.parametrize(
    ("text", "width"),
    [
        ("Wednesday", 62.078125),  # BASIC rounds to 62.0
        ("AV Ty", 31.078125),  # kerned pairs; BASIC ignores kerning: 32.0
    ],
)
def test_string_width_is_fractional_and_kerned(text, width):
    assert string_width(text, get_font_path("Roboto-Bold"), 12) == width
