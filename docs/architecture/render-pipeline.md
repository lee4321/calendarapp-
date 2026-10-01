# Render pipeline — one `weekly` run

`PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260331 -th config/themes/default.yaml -of out.svg`

Every SVG visualizer follows this sequence; only the layout/renderer pair
differs. (The `pit` and `timeline` visualizers add a labella callout-layout
step between layout and drawing — see `shared/labella_layout.py`.)

```mermaid
sequenceDiagram
    participant run as ecalendar.run()
    participant args as cli/args + config_assembly
    participant te as theme_loader
    participant db as CalendarDB
    participant fact as VisualizerFactory
    participant lay as WeeklyCalendarLayout
    participant rend as WeeklyCalendarRenderer

    run->>args: parse argv (@atfiles expanded)
    run->>db: _open_calendar_db(); load paper sizes
    run->>te: load_run_theme -> config.theme_v3 (before any option)
    run->>args: _apply_args_to_config(args, config)  # options beat the theme
    run->>run: calc_calendar_range()  # weekend-style week snapping
    run->>db: load_python_holidays(country, range)
    run->>run: build fiscal lookup (--fiscal)
    run->>run: setfontsizes()  # page-layout ratios
    run->>run: resolve_theme_palettes(config, db)
    run->>fact: create("weekly")
    fact->>lay: generate_coordinates(config)
    lay-->>fact: CoordinateDict {name → (x,y,w,h), PDF coords}
    fact->>rend: render(config, coordinates, events, db)
    rend->>rend: _populate_tokens(config)  # TOKENS → self._tokens
    rend->>rend: _render_content(): day boxes → events/durations → chrome
    rend->>rend: _write_run_details(): <stem>.md, <stem>.csv, icons/
    rend-->>run: VisualizationResult
```

Points worth knowing:

- **The theme loads first.** `load_run_theme` runs before any option is
  applied, so a CLI option that overlaps the theme always wins
  (`_CLI_CONFIG_OVERRIDES`).
- **The date range the user typed is not the range rendered.**
  `calc_calendar_range()` snaps to whole weeks per the weekend style;
  `config.userstart/userend` keep the typed range (the timeline axis and
  duration clamping use those).
- **Events arrive as dicts** from `CalendarDB` and are normalized to
  `shared.data_models.Event` (`from_dict` maps the PascalCase DB columns).
- **Run details**: while a renderer draws, it fills a render record
  (`renderers/details_record.py`) -- every event, the icons and marks it
  drew for each, assigned colors, and every exception (weekly overflow,
  clipped bars, unplaced labels ...). `renderers/run_details.py` writes the
  run folder's details document, event CSV and icon files from it.
