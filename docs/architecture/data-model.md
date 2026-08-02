# Data model

## calendar.db

```mermaid
erDiagram
    import_history ||--o{ events : "import_id"
    import_history ||--o{ specialdays : "import_id"
    import_sequence ||--|| import_history : "never-reused ids"

    events {
        int id PK
        int import_id FK
        text name
        text start_date "YYYYMMDD"
        text end_date "YYYYMMDD"
        text status "active/draft/on-hold/…"
        num priority
        text wbs
        int rollup
        int milestone
        real percent_complete
        text resource_names
        text resource_group
        text notes
        text icon
        text color
        text tags
    }
    specialdays {
        text id
        text company
        text country
        text startdate "YYYYMMDD"
        text enddate
        text name
        int nonworkday "1 = shaded"
        text icon
        text daycolor
        num pattern
        text patterncolor
    }
    import_history {
        int id PK
        text userid
        text filename
        text filehash "sha256 dedup"
        text command
    }
```

Standalone lookup tables (no relations): `icon` (name → SVG),
`patterns` (name → SVG tile), `palettes` (name → ordered colors),
`colors` (named colors), `papersizes`.

**Government holidays are not stored.** `CalendarDB.load_python_holidays()`
loads them per country and date range from the `holidays` Python package
into memory. Every category the package reports for a country is loaded
(discovered from `supported_categories`, not a fixed list): public,
government, bank and de-facto kinds are marked `nonworkday=1`; all other
kinds — optional, half-day, unofficial, school, workday, armed-forces and
the religious/ethnic ones — get titles without shading. Country-wide
holidays only; subdivision (state/province) holidays are not loaded.

## From rows to renderers

```mermaid
flowchart LR
    EV[("events rows<br/>(PascalCase-ish cols)")] -->|"Event.from_dict()"| E["shared/data_models.Event<br/>snake_case; is_duration =<br/>start != end"]
    SD[("specialdays rows")] --> CLS["shared/day_classifier<br/>classify_day() → {weekend,<br/>federal_holiday, company_holiday}"]
    PH["holidays pkg"] --> CLS
    E --> W["weekly / mini / candybar<br/>(events placed on days)"]
    E --> T["timeline / pit<br/>(callouts + duration lanes)"]
    E --> B["blockplan / compactplan<br/>(swimlanes / activity bands)"]
    E --> X["excelheader / excelblockplan<br/>exportdata CSV"]
    CLS --> W
    CLS --> B
```

Notes:

- `Event.from_dict()` accepts both DB column spellings (`Task_Name`,
  `Start`, `End`/`Finish`, `Datekey`) and snake_case; everything downstream
  uses the dataclass, never raw dicts.
- Dates are `YYYYMMDD` strings end to end; they sort lexicographically,
  which the row-packing algorithms rely on.
- `--status` filters events by the `status` column; non-active statuses
  render dimmed (see `_STATUS_OPACITY` in the weekly renderer).
- Import provenance: every imported row carries `import_id`;
  `import_history.filehash` (SHA-256) is the duplicate-import guard, and
  `import_sequence` guarantees ids are never reused even after removals.
