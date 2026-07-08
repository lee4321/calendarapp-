# System overview

EventCalendar turns a SQLite events database plus a YAML theme into SVG
calendars (and two Excel exports). Everything enters through
`ecalendar.py run()`.

```mermaid
flowchart LR
    subgraph CLI["cli/ + ecalendar.py"]
        ARGS["cli/args.py<br/>argparse + @atfiles"]
        RUN["ecalendar.run()"]
        ASM["cli/config_assembly.py<br/>args → CalendarConfig"]
    end

    subgraph CONF["config/"]
        CC["CalendarConfig<br/>(~536 fields: geometry,<br/>filters, fiscal, runtime)"]
        TE["theme_engine.ThemeEngine<br/>YAML → config + UnifiedTheme"]
        UT["UnifiedTheme<br/>resolve_token / find_rules"]
        CAT["element_catalog.yaml<br/>ec-* → token bindings"]
        PAL["palette_resolver"]
    end

    subgraph DATA["shared/"]
        DB[("calendar.db<br/>CalendarDB")]
        HOL["holidays pkg<br/>(in-memory gov holidays)"]
        EV["data_models.Event"]
        CLS["day_classifier"]
        RE["rule_engine<br/>StyleEngine / LaneEngine"]
    end

    subgraph VIZ["visualizers/"]
        FACT["VisualizerFactory"]
        LAY["<viz>/layout.py<br/>CoordinateDict"]
        REND["<viz>/renderer.py"]
    end

    BASE["renderers/svg_base.py<br/>BaseSVGRenderer:<br/>draw helpers, tokens,<br/>patterns, glyph text"]

    ARGS --> RUN --> ASM --> CC
    TE --> CC
    TE --> UT
    CAT --> TE
    RUN --> PAL --> CC
    RUN --> FACT --> LAY --> REND
    DB --> EV --> REND
    HOL --> DB
    CLS --> REND
    RE --> REND
    CC --> LAY
    CC --> REND
    UT -.tokens.-> BASE
    REND --> BASE --> OUT["SVG file(s)<br/>(+ _overflow / _details pages)"]
    RUN --> XLS["visualizers/excelheader.py<br/>excelblockplan.py → XLSX"]
    RUN --> SHEETS["visualizers/sheets.py<br/>palette/color/font/icon/pattern sheets"]
```

Key facts:

- **Text is geometry.** All text renders as `<path>` glyph outlines
  (fonttools + `renderers/glyph_cache.py`); no fonts are embedded. Text
  widths come from PIL `ImageFont.getlength()`.
- **Two coordinate systems.** Layouts produce PDF-style coordinates
  (origin bottom-left, Y up); `BaseSVGRenderer._svg_y()` flips to SVG
  (Y down). Day boxes are keyed `YYYYMMDD` in the CoordinateDict.
- **Government holidays are not in the DB.** `CalendarDB.load_python_holidays()`
  pulls them from the `holidays` package per country/date-range at run time.
  The DB holds events, company special days, icons, patterns, palettes,
  colors, paper sizes, and import history.
- **One shared base renderer.** Token cache (`_tk`), SVG pattern defs,
  header/footer/watermark chrome, the overflow table, and all draw
  primitives live on `BaseSVGRenderer`; visualizer renderers override
  `_render_content()`.
- **Guard rails.** `tools/refcorpus.sh check` diffs 34 reference SVGs
  (9 visualizers × 3 themes) byte-for-byte modulo `<desc>`; the test suite
  (~580 tests) runs in under 10 s.
