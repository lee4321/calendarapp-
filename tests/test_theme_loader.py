"""The version-3.0 theme loader: strict parsing against the schema dataclasses."""

from __future__ import annotations

import dataclasses
import re
from typing import ClassVar

import pytest

from config import theme_schema as schema
from config.theme_loader import ThemeError, UnsupportedThemeError, load_theme

FONTS = {"OfficinaSans-Book", "Roboto-Bold", "Roboto-Regular"}


def theme(**sections):
    return {"theme": {"name": "t", "version": "3.0"}, **sections}


def load(**sections):
    return load_theme(theme(**sections), font_registry=FONTS)


class TestVersionGate:
    def test_minimal_theme_loads_with_schema_defaults(self):
        t = load()
        assert t.theme.name == "t"
        assert t.lines.leader.route == "curve"
        assert t.durations.replace_icons_with_numbers is True
        assert t.timescale.primary == []

    @pytest.mark.parametrize("version", ["2.0", "3.1", 3, None])
    def test_other_versions_are_not_supported(self, version):
        data = {"theme": {"name": "old", "version": version}}
        with pytest.raises(UnsupportedThemeError, match="'old' is not supported"):
            load_theme(data, font_registry=FONTS)

    def test_missing_theme_block_is_not_supported(self):
        with pytest.raises(UnsupportedThemeError, match="not supported"):
            load_theme({"weekly": {}}, font_registry=FONTS)

    def test_message_names_no_converter(self):
        with pytest.raises(UnsupportedThemeError) as exc:
            load_theme({"theme": {"name": "old", "version": "2.0"}}, font_registry=FONTS)
        assert "convert" not in str(exc.value).lower()

    def test_missing_file_names_the_builtins(self):
        with pytest.raises(ThemeError, match="not found"):
            load_theme("no-such-theme")


class TestStrictKeys:
    def test_unknown_top_level_key(self):
        with pytest.raises(
            ThemeError, match=r"'time_bands' is not supported at the top level; valid keys here: .*timescale"
        ):
            load(time_bands={})

    def test_unknown_nested_key_names_its_path_and_the_valid_keys(self):
        with pytest.raises(
            ThemeError, match=r"'lines.axis.colour' is not supported inside 'lines.axis'; valid keys here: color, width"
        ):
            load(lines={"axis": {"colour": "red"}})

    def test_decoration_key_in_a_view_block_is_rejected(self):
        with pytest.raises(ThemeError, match=r"'timeline.axis_width' is not supported"):
            load(timeline={"axis_width": 3})

    def test_legacy_define_rule_is_rejected(self):
        rule = {"name": "d", "define": "text", "apply_to": "text:body"}
        with pytest.raises(ThemeError, match=r"style_rules\[0\]\.define' is not supported"):
            load(style_rules=[rule])

    def test_section_must_be_a_mapping(self):
        with pytest.raises(ThemeError, match="'lines' must be a mapping"):
            load(lines=[])

    def test_null_section_means_defaults(self):
        assert load(lines=None).lines.tick.width == 0.5


class TestValues:
    def test_int_is_accepted_for_float(self):
        assert load(lines={"axis": {"width": 3}}).lines.axis.width == 3.0

    def test_text_where_number_wanted(self):
        with pytest.raises(ThemeError, match=r"'lines.axis.width' must be a number, not str 'wide'"):
            load(lines={"axis": {"width": "wide"}})

    def test_bool_is_not_a_number(self):
        with pytest.raises(ThemeError, match="must be a number"):
            load(lines={"axis": {"width": True}})

    def test_number_is_not_a_bool(self):
        with pytest.raises(ThemeError, match="must be true or false"):
            load(today={"show": 1})

    def test_literal_rejects_other_values(self):
        with pytest.raises(ThemeError, match=r"'lines.axis.route' must be one of straight, curve, not 'wavy'"):
            load(lines={"axis": {"route": "wavy"}})

    def test_range_checks_name_the_section(self):
        with pytest.raises(ThemeError, match=r"theme section 'lines.axis': opacity must be between 0 and 1"):
            load(lines={"axis": {"opacity": 2}})

    def test_numbers_become_text_where_text_is_wanted(self):
        assert load(timescale={"primary": [{"unit": "date", "label": 5}]}).timescale.primary[0].label == "5"

    def test_palette_is_a_name_or_a_list(self):
        assert load(palettes={"month": "Blues"}).palettes.month == "Blues"
        assert load(palettes={"month": ["red", "blue"]}).palettes.month == ["red", "blue"]
        with pytest.raises(ThemeError, match=r"palettes\.month"):
            load(palettes={"month": 3.5})


class TestFonts:
    def test_registered_font_is_accepted(self):
        assert load(fonts={"family": "Roboto-Bold"}).fonts.family == "Roboto-Bold"

    def test_unregistered_font_is_rejected_with_its_path(self):
        with pytest.raises(ThemeError, match=r"'text.heading.font': font 'Comic' is not registered"):
            load(text={"heading": {"font": "Comic"}})

    def test_row_text_font_is_checked(self):
        row = {"unit": "month", "text": {"font": "Comic"}}
        with pytest.raises(ThemeError, match="is not registered"):
            load(timescale={"primary": [row]})

    def test_excel_font_is_an_installed_font_not_a_registered_one(self):
        assert load(excelblockplan={"font_name": "Calibri"}).excelblockplan.font_name == "Calibri"


class TestTimescale:
    def test_rows_are_inline_with_every_facet(self):
        row = {
            "unit": "week",
            "every": 2,
            "label": "Week",
            "format": "Week {n}",
            "height": 10,
            "fill": "lightblue",
            "border": {"color": "grey", "width": 0.25},
            "text": {"size": 7, "align": "middle"},
            "tick": {"length": 4, "label_align": "middle"},
            "vline": {"color": "red"},
        }
        t = load(timescale={"primary": [row], "secondary": [{"unit": "month"}]})
        got = t.timescale.primary[0]
        assert (got.every, got.tick.label_align, got.vline.color, got.border.width) == (2, "middle", "red", 0.25)
        assert t.timescale.secondary[0].height == 12.0

    def test_unit_is_required(self):
        with pytest.raises(ThemeError, match="missing required key"):
            load(timescale={"primary": [{"every": 2}]})

    def test_unknown_unit(self):
        with pytest.raises(ThemeError, match=r"timescale.primary\[0\].unit' must be one of"):
            load(timescale={"primary": [{"unit": "fortnight"}]})

    def test_every_must_be_positive(self):
        with pytest.raises(ThemeError, match="every must be >= 1"):
            load(timescale={"primary": [{"unit": "date", "every": 0}]})

    def test_the_old_catalog_and_placement_keys_are_gone(self):
        for key in ("top_bands", "bottom_bands", "bands"):
            with pytest.raises(ThemeError, match="is not supported"):
                load(timescale={key: []})

    def test_defaults_when_omitted(self):
        t = load()
        assert t.timescale.min_segment_width == 3.0


class TestStyleRules:
    def test_conditional_rule_loads(self):
        rule = {"name": "a", "apply_to": "box:duration", "select": {"resource_group": "a"}, "style": {"fill": "red"}}
        assert load(style_rules=[rule]).style_rules[0].style == {"fill": "red"}

    def test_apply_to_may_be_a_list(self):
        rule = {"name": "a", "apply_to": ["box:event", "box:duration"], "style": {"fill": "red"}}
        assert len(load(style_rules=[rule]).style_rules[0].apply_to) == 2

    @pytest.mark.parametrize("selector", ["visualizer", "papersize", "band", "repeat"])
    def test_context_selectors_are_gone(self, selector):
        rule = {"name": "a", "apply_to": "box:duration", "select": {selector: "x"}, "style": {"fill": "red"}}
        with pytest.raises(ThemeError, match=f"unsupported selector.*{selector}"):
            load(style_rules=[rule])

    def test_unknown_role(self):
        rule = {"name": "a", "apply_to": "box:nonesuch", "style": {"fill": "red"}}
        with pytest.raises(ThemeError, match="there is no box role 'nonesuch'"):
            load(style_rules=[rule])

    def test_not_a_role_reference(self):
        with pytest.raises(ThemeError, match="not a role reference"):
            load(style_rules=[{"name": "a", "apply_to": "element", "style": {}}])

    def test_style_key_must_belong_to_the_role(self):
        rule = {"name": "a", "apply_to": "line:axis", "style": {"fill": "red"}}
        with pytest.raises(ThemeError, match=r"style' has key\(s\) fill"):
            load(style_rules=[rule])


class TestSchema:
    def test_every_default_round_trips(self):
        """Defaults -> mapping -> load gives back the same theme: every annotation is loadable."""
        base = schema.Theme(theme=schema.ThemeMeta(name="rt"))
        again = load_theme(dataclasses.asdict(base), font_registry=FONTS | {"OfficinaSans-Book"})
        assert again == base

    def test_a_populated_theme_round_trips(self):
        row = schema.TimescaleRow(unit="month", tick=schema.RowTick(), vline=schema.LineSpec(color="red"))
        base = schema.Theme(
            theme=schema.ThemeMeta(name="rt"),
            timescale=schema.Timescale(primary=[row], secondary=[schema.TimescaleRow(unit="date", every=7)]),
            style_rules=[schema.StyleRule(name="r", apply_to="box:duration", style={"fill": "red"})],
        )
        assert load_theme(dataclasses.asdict(base), font_registry=FONTS) == base

    def test_every_dataclass_field_has_a_supported_annotation(self):
        # _coerce raises TypeError for an annotation it cannot load; the round trip above
        # covers values, this covers every class by building each from an empty mapping.
        from config.theme_loader import _parse

        for name, cls in vars(schema).items():
            if dataclasses.is_dataclass(cls) and isinstance(cls, type):
                required = [
                    f.name
                    for f in dataclasses.fields(cls)
                    if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
                ]
                if not required:
                    _parse(cls, {}, name, font_registry=FONTS)

    #: Words that mean decoration; they belong in a shared block, never in a view block.
    DECORATION = re.compile(r"band|tick|axis|leader|today|holiday|palette|number_duration|fiscal|font|_color$|opacity")

    #: View-block keys that look like decoration but are structure or Excel-only.  Keep short.
    ALLOWED: ClassVar[set[tuple[str, str]]] = {
        ("MiniCalendar", "adjacent_month_color"),
        ("MiniCalendar", "adjacent_month_opacity"),
        ("MiniCalendar", "event_icon_opacity"),
        ("WeeklyDayBox", "hash_pattern_opacity"),
        ("Pit", "leader_label_anchor"),
        ("CompactPlan", "show_axis_legend"),
        ("CompactPlan", "legend_axis_text"),
        ("Blockplan", "band_label_column_ratio"),
        ("ExcelBlockplan", "font_name"),
        ("ExcelBlockplan", "font_size"),
        ("Gantt", "float_opacity_scale"),
    }

    @pytest.mark.parametrize(
        "cls",
        [
            schema.Weekly,
            schema.WeeklyDayBox,
            schema.MiniCalendar,
            schema.TextMini,
            schema.Candybar,
            schema.Timeline,
            schema.TimelineEvents,
            schema.TimelineDurations,
            schema.Pit,
            schema.PitLabel,
            schema.CompactPlan,
            schema.Blockplan,
            schema.Gantt,
            schema.GanttMarks,
            schema.ExcelBlockplan,
        ],
        ids=lambda c: c.__name__,
    )
    def test_view_blocks_hold_structure_only(self, cls):
        offenders = [
            f.name
            for f in dataclasses.fields(cls)
            if self.DECORATION.search(f.name) and (cls.__name__, f.name) not in self.ALLOWED
        ]
        assert offenders == []

    def test_view_blocks_are_the_only_view_sections_of_the_theme(self):
        names = {f.name for f in dataclasses.fields(schema.Theme)}
        views = {
            "weekly",
            "mini_calendar",
            "text_mini",
            "candybar",
            "timeline",
            "pit",
            "compact_plan",
            "blockplan",
            "gantt",
            "excelblockplan",
        }
        assert views <= names
        assert not {"time_bands", "base", "colors", "timeline_events", "timeline_durations"} & names
