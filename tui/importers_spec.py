"""Adapters describing each importer entry-point for the shared import wizard.

Events and special days share a grammar (file/dir, dry-run, replace,
skip-errors, list/remove, logging) so they share a wizard, differing only by the
fields declared here.  Content importers (icons/patterns/colors) are simpler.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImportField:
    dest: str
    label: str
    kind: str  # path | dir | text | int | flag | choice
    option: str | None = None  # None => positional 'files'
    default: object = None
    choices: list[str] | None = None
    help: str = ""
    generator_only: bool = False


@dataclass
class ImporterSpec:
    key: str
    title: str
    script: str  # path passed to `uv run <script>`
    summary: str
    fields: list[ImportField] = field(default_factory=list)
    supports_generate: bool = False
    supports_history: bool = False
    remove_flag: str | None = None  # "--remove" or "--clear"


def _shared_fields(*, country_lang: bool, generate: bool) -> list[ImportField]:
    out = [
        ImportField("files", "Source file / folder", "path", None,
                    help="XLSX/CSV file or a directory of them"),
        ImportField("database", "Target database", "path", "--database", "calendar.db",
                    help="SQLite database to write into"),
    ]
    if country_lang:
        out += [
            ImportField("country", "Country", "text", "--country",
                        help="ISO country code tag for imported rows"),
            ImportField("language", "Language", "text", "--language",
                        help="Language tag for imported rows"),
    ]
    out += [
        ImportField("replace", "Replace prior import", "flag", "--replace", False,
                    help="Delete previously imported rows from this file first"),
        ImportField("dry_run", "Dry run (validate only)", "flag", "--dry-run", True,
                    help="Validate without writing"),
        ImportField("skip_errors", "Skip bad rows", "flag", "--skip-errors", False,
                    help="Continue when individual rows fail"),
        ImportField("verbose", "Verbose", "flag", "--verbose", False),
        ImportField("log_level", "Log level", "choice", "--log-level", "info",
                    choices=["debug", "info", "warning", "error"]),
    ]
    return out


def events_spec() -> ImporterSpec:
    fields = [
        ImportField("files", "Source file / folder", "path", None,
                    help="XLSX/CSV file or directory (leave blank when generating)"),
        ImportField("database", "Target database", "path", "--database", "calendar.db"),
        ImportField("user_id", "User ID", "int", "--user-id", 1,
                    help="Owner user id for imported events"),
        ImportField("generate", "Generator script", "path", "--generate",
                    help="Python script with generate_events() -> DataFrame",
                    generator_only=False),
        ImportField("start_date", "Generator start date", "text", "--start-date",
                    help="e.g. 2026-01-01", generator_only=True),
        ImportField("end_date", "Generator end date", "text", "--end-date",
                    help="e.g. 2026-12-31", generator_only=True),
        ImportField("param", "Generator params (KEY=VALUE)", "text", "--param",
                    help="Repeatable; one KEY=VALUE per line", generator_only=True),
        ImportField("replace", "Replace prior import", "flag", "--replace", False),
        ImportField("dry_run", "Dry run (validate only)", "flag", "--dry-run", True),
        ImportField("skip_errors", "Skip bad rows", "flag", "--skip-errors", False),
        ImportField("verbose", "Verbose", "flag", "--verbose", False),
        ImportField("log_level", "Log level", "choice", "--log-level", "info",
                    choices=["debug", "info", "warning", "error"]),
    ]
    return ImporterSpec(
        key="events",
        title="Events",
        script="importers/import_events.py",
        summary="Project tasks / durations / milestones (XLSX/CSV or generator)",
        fields=fields,
        supports_generate=True,
        supports_history=True,
        remove_flag="--remove",
    )


def specialdays_spec() -> ImporterSpec:
    return ImporterSpec(
        key="specialdays",
        title="Special days",
        script="importers/import_specialdays.py",
        summary="Company nonworkdays, observances, custom day styling",
        fields=[
            ImportField("user_id", "User ID", "int", "--user-id", 1),
            *_shared_fields(country_lang=True, generate=False),
        ],
        supports_history=True,
        remove_flag="--remove",
    )


def content_specs() -> list[ImporterSpec]:
    return [
        ImporterSpec(
            key="icons", title="Icons", script="importers/import_icons.py",
            summary="Folder of .svg -> icon table",
            fields=[ImportField("folder", "SVG folder", "dir", None,
                                help="Directory containing .svg files")],
        ),
        ImporterSpec(
            key="patterns", title="Patterns", script="importers/import_patterns.py",
            summary="Folder of .svg -> patterns table (day-box decoration)",
            fields=[ImportField("folder", "SVG folder", "dir", None)],
        ),
        ImporterSpec(
            key="colors", title="Colors", script="importers/import_rcairo_colors.py",
            summary="Rcairocolors.csv -> colors table",
            fields=[
                ImportField("db", "Database", "path", "--db", "calendar.db"),
                ImportField("csv", "CSV file", "path", "--csv", "Rcairocolors.csv"),
            ],
        ),
    ]


def all_importers() -> dict[str, ImporterSpec]:
    specs = [events_spec(), specialdays_spec(), *content_specs()]
    return {s.key: s for s in specs}


def build_import_argv(spec: ImporterSpec, values: dict[str, object]) -> list[str]:
    """Assemble argv tail (without the script path) for an importer run."""
    is_generate = spec.supports_generate and bool(
        str(values.get("generate") or "").strip()
    )
    argv: list[str] = []
    positional: list[str] = []

    for f in spec.fields:
        if f.generator_only and not is_generate:
            continue
        v = values.get(f.dest)

        if f.option is None:  # positional (files / folder)
            text = str(v or "").strip()
            if text:
                positional.append(text)
            continue

        if f.kind == "flag":
            if v:
                argv += [f.option]
            continue

        if f.dest == "param":  # repeatable KEY=VALUE lines
            for line in str(v or "").splitlines():
                line = line.strip()
                if line:
                    argv += [f.option, line]
            continue

        text = str(v if v is not None else "").strip()
        if text == "" or text == str(f.default):
            continue
        argv += [f.option, text]

    return positional + argv
