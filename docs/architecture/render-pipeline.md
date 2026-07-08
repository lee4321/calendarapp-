# Render pipeline — one `weekly` run

`PYTHONPATH=. uv run python ecalendar.py weekly 20260101 20260331 -th corporate -of out.svg`

Every SVG visualizer follows this sequence; only the layout/renderer pair
differs. (The `pit` and `timeline` visualizers add a labella callout-layout
step between layout and drawing — see `shared/labella_layout.py`.)

```mermaid
sequenceDiagram
    participant run as ecalendar.run()
    participant args as cli/args + config_assembly
    participant te as ThemeEngine
    participant db as CalendarDB
    participant fact as VisualizerFactory
    participant lay as WeeklyCalendarLayout
    participant rend as WeeklyCalendarRenderer

    run->>args: parse argv (@atfiles expanded)
    run->>db: _open_calendar_db(); load paper sizes
    run->>args: _apply_args_to_config(args, config)
    run->>run: calc_calendar_range()  # weekend-style week snapping
    run->>db: load_python_holidays(country, range)
    run->>run: build fiscal lookup (--fiscal)
    run->>te: load + apply theme (pass 1)
    Note over te: sections → config fields,<br/>style_rules → UnifiedTheme,<br/>element styles from catalog
    run->>run: setfontsizes()  # token size > page-height heuristic
    run->>te: re-apply theme (pass 2) + _inject_heuristic_size_tokens
    run->>args: _reapply_post_theme_cli_overrides  # CLI beats theme
    run->>run: _resolve_palette_overrides(config, db)
    run->>fact: create("weekly")
    fact->>lay: generate_coordinates(config)
    lay-->>fact: CoordinateDict {name → (x,y,w,h), PDF coords}
    fact->>rend: render(config, coordinates, events, db)
    rend->>rend: _populate_tokens(config)  # TOKENS → self._tokens
    rend->>rend: _render_content(): day boxes → events/durations → chrome
    rend-->>run: VisualizationResult (+ overflow entries)
    run->>rend: overflow page → <name>_overflow.svg (if any)
```

Points worth knowing:

- **Theme is applied twice.** Pass 1 exposes theme-declared font sizes to
  `setfontsizes()`; pass 2 re-applies after the heuristics so precedence
  ends up: token size → legacy field heuristic. CLI flags are re-applied
  last (`_reapply_post_theme_cli_overrides`) so the command line always
  wins over the theme.
- **The date range the user typed is not the range rendered.**
  `calc_calendar_range()` snaps to whole weeks per the weekend style;
  `config.userstart/userend` keep the typed range (the timeline axis and
  duration clamping use those).
- **Events arrive as dicts** from `CalendarDB` and are normalized to
  `shared.data_models.Event` (`from_dict` maps the PascalCase DB columns).
- **Overflow**: weekly emits events that didn't fit as a separate
  `_overflow.svg` table page; mini/candybar route extra content to the
  `_details` page instead; blockplan/timeline never overflow.
