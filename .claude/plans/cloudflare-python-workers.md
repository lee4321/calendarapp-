# Plan: running ecalendar on Cloudflare Python Workers

Written 2026-09-22, the day after Python Workers went GA.

## What the platform gives us (from the docs, Sep 2026)

- **Runtime.** CPython compiled to WebAssembly (Pyodide) inside a V8 isolate. Tooling is `uv` plus
  `pywrangler` (`uvx --from workers-py pywrangler init`, `uv run pywrangler dev|deploy`).
  Dependencies come from the worker's own `pyproject.toml` and are bundled into `python_modules/`.
- **Entry point.** `class Default(WorkerEntrypoint): async def fetch(self, request)`, with bindings on
  `self.env`. `workers.asgi`/`workers.wsgi` bridges exist for FastAPI, Flask and Django.
- **Cold start.** The module's top-level scope, including everything it imports, runs at *deploy* time
  and the Wasm memory is snapshotted. Heavy imports belong at the top level.
- **Stdlib.** Complete except curses/dbm/fcntl/pwd/termios/etc. `threading` and `multiprocessing` import
  but don't work. The filesystem is **ephemeral and in memory**. The docs neither list nor exclude
  `sqlite3`.
- **Limits** (the same on Free and Paid unless noted):

  | Limit | Value | Why it matters here |
  |---|---|---|
  | Worker size | 64 MiB uncompressed | `fonts/` alone is 75 MB and `calendar.db` is 28 MB |
  | Memory per isolate | 128 MB (JS heap + Wasm) | a native weekly render already peaks at ~110 MB RSS |
  | CPU per request | Free 10 ms · Paid 30 s default, 5 min max | a native render takes 0.3–0.7 s CPU, and Wasm is slower |
  | Global-scope startup | 1 s | covered by the snapshot |
  | Static assets | 25 MiB/file | an option for fonts |

  **→ This needs the Workers Paid plan.** The Free plan's 10 ms CPU limit rules it out.

## How the dependencies map

| Dep | Used by the render path? | In Pyodide 314? | Note |
|---|---|---|---|
| drawsvg, arrow, holidays, python-dateutil, pyyaml | yes | pure Python / built-in | fine |
| intervaltree (vendor/labella) + sortedcontainers | yes | pure Python / built-in | fine |
| fonttools | yes (glyph outlines) | 4.62.1 | the project pins `>=4.65` |
| **Pillow** | yes (text measurement) | 12.2.0 | the project pins `>=12.3` **and requires libraqm** |
| openpyxl (+ et_xmlfile) | excelblockplan only | pure Python | fine |
| pandas | **importers only** | 3.0.2 | leave it out of the worker |
| sqlite3 | yes (`shared/db_access.py`) | not documented | must be verified |

## Blocking risks (Phase 0 answers these)

1. **Text measurement without libraqm.** `pyproject.toml` builds Pillow from source because wheels
   without raqm "shift every rendered label" (guarded by `tests/test_text_layout_engine.py`). Pyodide's
   Pillow very likely has no raqm. If it doesn't, Worker output won't match desktop output. Options, in
   order of preference:
   (a) Check whether Pyodide ships `uharfbuzz`; if so, measure with it on both platforms.
   (b) Move measurement to fontTools advances plus kerning. This changes desktop output once and
       needs a refcorpus re-baseline.
   (c) Accept BASIC-engine output on the Worker and document it.
2. **Memory.** A native render peaks at ~110 MB RSS, and the limit is 128 MB. Fonts and the DB also sit
   in the in-memory FS, which counts toward the same limit. Phase 0 must measure the Wasm heap for
   weekly/blockplan/gantt over a full year.
3. **Size.** Fonts (75 MB) and the DB (28 MB, of which patterns are 16.8 MB and icons 10.5 MB) don't fit
   in 64 MiB alongside the dependencies.
4. **`sqlite3` availability.** If it isn't there, `CalendarDB` needs a non-sqlite backend. A
   SQLite-backed **Durable Object** covers that case without going async — see the next section.

## Where the data lives: Durable Objects vs sqlite3 vs D1

A Durable Object is a single addressable instance that owns both its compute and its own private
SQLite database, and the two sit on the same machine. Python Workers have supported them since May
2025.

The reason they matter here is the **synchronous SQL API**: inside a Durable Object,
`self.ctx.storage.sql.exec("SELECT ...", *params)` returns its rows immediately, with no `await`.
That is the same shape as `sqlite3.Cursor.execute()`. D1, by contrast, is only reachable over the
network with `await`, which is what forces the prefetch design. Cloudflare's own Python example:

```python
from workers import DurableObject, Response, WorkerEntrypoint

class MyDurableObject(DurableObject):
    def __init__(self, ctx, env):
        self.ctx = ctx
        self.env = env

    def fetch(self, request):
        result = self.ctx.storage.sql.exec("SELECT 'Hello, World!' as greeting").one()
        return Response(result.greeting)
```

```toml
[[durable_objects.bindings]]
name = "CALENDAR_STORE"
class_name = "CalendarStore"

[[migrations]]
tag = "v1"
new_sqlite_classes = ["CalendarStore"]
```

### The three options

| | sqlite3 file (bundled) | **Durable Object** | D1 |
|---|---|---|---|
| Availability | undocumented; Phase 0 must verify | documented, with a Python example | documented |
| API | sync | **sync** (`sql.exec`) | async only |
| Changes to `shared/db_access.py` | none | swap the driver for an adapter; SQL unchanged | prefetch layer, or make the pipeline async |
| Writable | no (in-memory FS is wiped per isolate) | yes, durable | yes |
| Per-tenant event data | request body only | yes, one object per tenant | yes, shared |
| Counts against the 64 MiB bundle | yes (28 MB) | no | no |
| Counts against the 128 MB isolate memory | yes, the whole file | no; only the rows read | no |
| Limits | — | 10 GB/object, 2 MB per row, 100 KB per SQL statement, ~1,000 req/s per object | — |
| Cost | none | billed per row read/written and per GB stored | same model |

Our data fits: the largest pattern SVG is 954 KB and the largest icon 26 KB, both under the 2 MB row
cap. The SQL in `shared/db_access.py` is plain `SELECT`s with `?` parameters, `lower()` and
`COLLATE NOCASE` — all supported. Nothing uses transactions, PRAGMA or custom functions.

**Recommendation: render *inside* the Durable Object.** A stateless `WorkerEntrypoint` validates the
request and routes it to a `CalendarStore` object; that object runs the whole render against its own
synchronous SQL and returns the SVG or zip. This keeps `CalendarDB` and every caller synchronous, and
it takes both the 28 MB database and its memory footprint out of the Worker bundle. The prefetch
adapter stays on the plan only as the D1 fallback.

### What this costs

- **A `CalendarDB` adapter.** `shared/db_access.py` opens a connection, sets `row_factory =
  sqlite3.Row` and does `dict(row)`. The Durable Object cursor returns JS objects instead, so the
  adapter wraps `sql.exec(...).toArray()` and converts to dicts. The SQL strings don't change. Extract
  a driver seam: `execute(sql, params) -> list[dict]`, with a `sqlite3` implementation and a
  Durable Object one.
- **Per-query FFI overhead.** The module's own docstring says a render issues thousands of small
  queries, and each one now crosses the Python→JS boundary. Phase 0 should measure this. The fix, if
  it matters, is to load the small static tables (colors, palettes, papersizes, and the icon and
  pattern names) once per object into Python dicts in `__init__`, fetching only the large SVG blobs on
  demand. That is Cloudflare's documented in-memory caching pattern and it survives across requests to
  the same object.
- **Seeding.** The object needs its schema and reference rows on first use. Ship
  `calendar.db.sql` (already in the repo) as a data file, run it inside `blockConcurrencyWhile()` on
  first boot, and chunk the inserts to stay under the 100 KB statement limit — bind the big SVGs as
  parameters rather than inlining them. Version the seed so redeploys can migrate.
- **Concurrency.** A Durable Object handles one request at a time, so renders on one object serialize.
  Since a render takes roughly a second, use one object per tenant or user, or a small pool of
  read-only "renderer" objects keyed by a hash, rather than a single global object.
- **Reference vs tenant data.** Two classes are cleaner than one: a `ReferenceStore` seeded from
  `calendar.db.sql` and holding the static tables, and a per-tenant `CalendarStore` holding events and
  specialdays. But two objects means one of them is remote and async again. The simpler shape is one
  object class per tenant, each seeded with the reference tables — roughly 27 MB per tenant against a
  10 GB cap, which is affordable while tenants are few. Revisit if that changes.

## Phases

### Phase 0: Feasibility spike (1–2 days, go/no-go)
- Create a throwaway `worker/` project with `pywrangler init`. Its pyproject gets relaxed pins
  (pillow, fonttools) and no pandas.
- Copy in `ecalendar.py`, `cli/`, `config/`, `renderers/`, `shared/`, `visualizers/` and `vendor/`, a
  Roboto/RobotoCondensed font subset and a DB trimmed to reference tables only.
- `fetch` calls `ecalendar.run([... "weekly", "20260101", "20261231", "--outputfile", "spike.svg"])`
  and returns the SVG.
- Also stand up a one-table SQLite-backed Durable Object in the same spike, seeded from
  `calendar.db.sql`, and run the same render against it through a throwaway driver adapter.
- Record: `PIL.features.check("raqm")`, `check("freetype2")`, whether `import sqlite3` works, whether
  non-.py files under `src/` are uploaded and readable with `open()`, bundle size, snapshot success,
  CPU ms and peak memory for weekly, mini, blockplan and gantt, and an SVG diff against the refcorpus.
- Durable Object measurements that decide Phase 2: per-`sql.exec` round-trip cost from Python, the
  render's total query count, whether the class is snapshotted like the entrypoint module, how long
  seeding 27 MB of reference rows takes, and the row-read billing for one render.

### Phase 1: Make the core host-agnostic (in the main repo, testable locally)
- **Resource locator.** Make the fonts dir, DB path, themes dir and `OUTPUT_ROOT` (`shared/run_paths.py`)
  configurable through one settings object or env instead of CWD-relative constants. `FONT_REGISTRY` is
  built at import by scanning `fonts/`, so it needs to tolerate a subset or lazily fetched fonts.
- **Output sink.** Writers currently put SVG/MD/CSV/icons into `output/<stem>/`. Keep `RunPaths`, but let
  the root be a per-request temp dir. Add a helper that zips the run folder into bytes, and clean up
  after each request, because the in-memory FS counts against memory.
- **Library entry point.** Add `render(request: RenderRequest) -> RunResult` beside `run(argv)`. It
  should take no `sys.argv` or `sys.exit`, return the files, and raise the typed exceptions `run()`
  already maps to exit codes.
- **Per-request state audit.** Glyph LRU caches are fine to share across requests (and warm in the
  snapshot). Module-level mutable state that carries *config* between runs is not (pattern caches,
  palette overrides, anything that `setfontsizes` mutates globally). Add a test that runs two different
  renders in one process and compares each to a fresh-process render.
- **Text measurement decision** from risk 1 lands here, with a refcorpus re-baseline if needed.

### Phase 2: Data layer, on a Durable Object
- **Driver seam.** Split `shared/db_access.py` in two: the ~20 query methods stay as they are, and a
  small driver underneath exposes `execute(sql, params) -> list[dict]`. Two implementations: `sqlite3`
  for desktop and CI, and `sql.exec(...).toArray()` for the Durable Object. The SQL strings and every
  caller stay untouched, and both drivers run against the same test suite.
- **`CalendarStore` Durable Object.** One object per tenant, holding the reference tables plus that
  tenant's events and specialdays. It seeds itself from `calendar.db.sql` on first boot inside
  `blockConcurrencyWhile()`, with chunked inserts and the large SVGs bound as parameters. It caches
  the small static tables in Python dicts in `__init__`, which then persist across requests to that
  object.
- **Render inside the object**, so the whole pipeline stays synchronous. The entrypoint Worker only
  validates, routes and returns.
- **Event ingestion** becomes an RPC method on the object: a CSV or JSON body in the
  `importers/import_events.py` schema, written into its `events` table. That replaces the "events in
  every request" design, though the object can still accept one-shot events for a stateless render.
- **Fallbacks, in order**, if Phase 0 rules the Durable Object out on FFI cost or memory:
  - a bundled read-only `reference.db` via `sqlite3`, with events in the request body;
  - **D1** with a prefetch adapter — `await` one query for the date range before the render, then run
    synchronously against the in-memory result.
  All three sit behind the same driver seam, so the choice is swappable.

### Phase 3: Fonts
- Bundle the fonts the built-in themes use (RobotoCondensed-*, Roboto-*, JuliaMono-Regular, FiraSans,
  SairaExtraCondensed, PlaywriteDEGrund) within a size budget. Put the rest in **R2** and fetch each one
  on first use into the in-memory FS.
  - This is an async fetch before the sync render. Font names can be found by resolving the theme first.
  - The alternative is Static Assets (25 MiB/file), fetched the same way.
- **Licensing check.** Calibri, AmericanTypewriter and OfficinaSans are commercial or Apple fonts.
  Serving renders from a public service embeds their glyph outlines in delivered SVGs. Exclude them from
  the Worker font set unless their licenses allow it.
- Fonts could also live in the Durable Object as rows, which would keep them out of the bundle and off
  the async path. They are binary and up to 3.6 MB each, under the 2 MB row cap only if chunked, so R2
  is the better fit unless Phase 0 shows the extra `await` is a problem.

### Phase 4: HTTP API and security
- `POST /render/{view}` with a JSON body (dates, theme, papersize, orientation, filters, events). An
  **allowlist** maps it to argv. Never pass raw argv from the internet: `--database PATH`, `@file`
  expansion and arbitrary theme file paths must be unreachable.
- `GET /themes`, `/fonts`, `/papersizes`, `/palettes`, `/patterns` map to the existing listing commands.
- The entrypoint picks the object: `env.CALENDAR_STORE.idFromName(tenant)` from the authenticated
  identity, never from a caller-supplied field, then `get(id)` and an RPC call. One object serializes
  its requests, so route a tenant's concurrent renders across a small keyed pool if that becomes a
  bottleneck.
- `POST /events` ingests a tenant's event data into its object.
- Responses:
  - `?format=svg` returns the main SVG directly.
  - The default returns a zip of the run folder (SVG pages, `.md`, `.csv`, `icons/`).
  - Large or async results can go to R2, with a signed URL returned.
- Auth with Cloudflare Access or a bearer token in a Secret. Add a rate-limiting binding, and set a
  `limits.cpu_ms` cap in `wrangler.toml`.
- Optional: use `workers.asgi` with FastAPI for request validation and OpenAPI docs. This costs snapshot
  size and memory, so measure it against the spike numbers first.

### Phase 5: Build, test and deploy
- `tools/build_worker.py` assembles `worker/src/` from the main packages plus the trimmed data and
  fonts, so there is one source of truth and no copy drift. It fails when the bundle exceeds a budget,
  e.g. 55 MiB.
- Tests:
  - Unit tests for the API→argv allowlist and the backends run in the normal pytest suite.
  - The driver seam gets one shared test suite run against both drivers — `sqlite3` locally, the
    Durable Object under `pywrangler dev` — so the two can't drift.
  - An integration test runs `pywrangler dev`, renders a small set of views and compares them against
    a Worker-specific refcorpus (desktop's refcorpus if the risk 1 fix makes them identical).
- Durable Object migrations are append-only: every schema change needs a new `[[migrations]]` tag, and
  the seed carries a version row so a redeploy can tell "seed me" from "migrate me".
- Keep the pre-commit gate (ty, ruff, pytest) covering the shared code. Worker deploys stay manual:
  `uv run pywrangler deploy`.

## Out of scope for the Worker
Importers (pandas), `tools/`, the `*sheet` gallery generators beyond the simple ones, and anything that
writes to the canonical `calendar.db`.

## Open questions for you
- Who calls it: only you, a team, or public users? This decides the auth model and whether the font
  licensing risk applies.
- Where do events live: in the request (stateless), or in a per-tenant Durable Object?
- If Durable Objects: how many tenants? Each one carries its own ~27 MB copy of the reference tables,
  which is fine for a handful and wasteful for hundreds. At that point the reference data moves to a
  bundled read-only file or a shared object.
- Must Worker output be byte-identical to desktop output, which forces risk 1 option (a) or (b)?
