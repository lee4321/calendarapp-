"""The ``excelblockplan:`` theme section styles the excelblockplan workbook.

It replaced the ``excelheader:`` section when the excelheader command was
removed; a theme still using the old name is rejected, naming the valid sections.
"""

from __future__ import annotations

import pytest

from config.theme_loader import ThemeError, load_theme

_META = {"theme": {"name": "Excel", "version": "3.0"}}


def test_section_keys_reach_the_theme():
    theme = load_theme({**_META, "excelblockplan": {"font_name": "Arial", "font_size": 11}})
    assert (theme.excelblockplan.font_name, theme.excelblockplan.font_size) == (
        "Arial",
        11,
    )


def test_the_old_section_name_is_rejected():
    with pytest.raises(ThemeError, match="excelheader"):
        load_theme({**_META, "excelheader": {"font_size": 9}})
