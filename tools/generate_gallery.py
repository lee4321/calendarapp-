#!/usr/bin/env python3
"""
Generate every SVG visualization in every theme for side-by-side review.

The script is a batch driver for ``ecalendar.py``: it runs one CLI invocation
per (visualization, theme) pair over the same date range and the same fixed
page setup, so the only variable between two output files is the view and the
theme.  That makes the resulting set directly comparable by a human reviewer.

Fixed defaults (all overridable):
    paper size    Tabloid
    orientation   landscape
    weekends      0 (work week only)
    countries     US,UA

Output naming::

    <visualization>_<theme>_<YYYYMMDD-HHMMSS>.svg

The timestamp is taken once at start-up so a whole batch shares one stamp and
sorts together.  ecalendar confines SVG output to the ``output/`` directory,
so that is where the files land.

Usage::

    uv run python tools/generate_gallery.py 20260105 20260630
    uv run python tools/generate_gallery.py 20260105 20260630 --themes default,dark
    uv run python tools/generate_gallery.py 20260105 20260630 --views weekly,timeline
    uv run python tools/generate_gallery.py 20260105 20260630 --include-nonsvg

An HTML contact sheet (``output/gallery_<stamp>.html``) is written at the end
so the whole batch can be browsed in one page; suppress it with ``--no-index``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as _dt
import html
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ECALENDAR = REPO_ROOT / "ecalendar.py"
OUTPUT_DIR = REPO_ROOT / "output"
THEMES_DIR = REPO_ROOT / "config" / "themes"

# Views that produce a themed SVG page — the evaluation set.
SVG_VIEWS = (
    "weekly",
    "mini",
    "mini-icon",
    "candybar",
    "timeline",
    "pit",
    "blockplan",
    "compactplan",
)

# Views that are not themed SVG pages.  text-mini has no --theme flag (plain
# text output, rendered once); the excel views are themed but emit .xlsx.
NONSVG_VIEWS = {
    "text-mini": {"themed": False, "ext": ".txt"},
    "excelheader": {"themed": True, "ext": ".xlsx"},
    "excelblockplan": {"themed": True, "ext": ".xlsx"},
}


@dataclass
class Job:
    """One ecalendar invocation: a view rendered with a single theme."""

    view: str
    theme: str | None
    filename: str
    argv: list[str]


@dataclass
class Result:
    """Outcome of a Job, including any extra files the run emitted."""

    job: Job
    returncode: int
    output: str
    files: list[Path]


def discover_themes() -> list[str]:
    """
    Return every theme name ecalendar can load.

    Asks the CLI first so the list always matches what ``ecalendar themes``
    reports; falls back to globbing config/themes/*.yaml if that fails.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(ECALENDAR), "themes"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=True,
        )
        names = [
            line.strip()
            for line in proc.stdout.splitlines()
            if line.startswith("  ") and line.strip()
        ]
        if names:
            return names
    except (subprocess.CalledProcessError, OSError):
        pass
    return sorted(p.stem for p in THEMES_DIR.glob("*.yaml"))


def validate_date(value: str) -> str:
    """Argparse type: accept only YYYYMMDD date strings."""
    try:
        _dt.datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid YYYYMMDD date"
        ) from exc
    return value


def build_jobs(args: argparse.Namespace, stamp: str) -> list[Job]:
    """Expand the requested views and themes into the full job list."""
    jobs: list[Job] = []

    def add(view: str, theme: str | None, ext: str) -> None:
        theme_part = theme if theme else "notheme"
        filename = f"{view}_{theme_part}_{stamp}{ext}"
        argv = [
            sys.executable,
            str(ECALENDAR),
            view,
            args.begin,
            args.end,
            "--weekends",
            str(args.weekends),
            "--country",
            args.country,
            "--outputfile",
            filename,
        ]
        if theme:
            argv += ["--theme", theme]
        if view in SVG_VIEWS:
            argv += [
                "--papersize",
                args.papersize,
                "--orientation",
                args.orientation,
            ]
        jobs.append(Job(view=view, theme=theme, filename=filename, argv=argv))

    for view in args.views:
        if view in SVG_VIEWS:
            for theme in args.themes:
                add(view, theme, ".svg")
        else:
            spec = NONSVG_VIEWS[view]
            if spec["themed"]:
                for theme in args.themes:
                    add(view, theme, spec["ext"])
            else:
                add(view, None, spec["ext"])
    return jobs


def run_job(job: Job) -> Result:
    """Run one ecalendar invocation and collect the files it produced."""
    stem = Path(job.filename).stem
    proc = subprocess.run(
        job.argv,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    # A run can emit more than the named file (e.g. weekly overflow pages,
    # paginated sheets); every extra shares the base stem.
    produced = sorted(
        {
            *OUTPUT_DIR.glob(f"{stem}*"),
            # excel views write relative to the working directory, not output/.
            *REPO_ROOT.glob(f"{stem}*"),
        }
    )
    return Result(
        job=job,
        returncode=proc.returncode,
        output=(proc.stdout + proc.stderr).strip(),
        files=produced,
    )


def write_index(results: list[Result], stamp: str, args: argparse.Namespace) -> Path:
    """Write an HTML contact sheet linking every generated file."""
    index_path = OUTPUT_DIR / f"gallery_{stamp}.html"
    by_view: dict[str, list[Result]] = {}
    for res in results:
        by_view.setdefault(res.job.view, []).append(res)

    parts = [
        "<!doctype html>",
        "<meta charset='utf-8'>",
        f"<title>EventCalendar gallery {stamp}</title>",
        "<style>",
        "body{font-family:system-ui,sans-serif;margin:2rem;background:#fafafa}",
        "h1{font-size:1.4rem} h2{margin-top:2rem;border-bottom:1px solid #ccc}",
        ".grid{display:grid;gap:1rem;"
        "grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}",
        ".card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:.5rem}",
        ".card img{width:100%;height:180px;object-fit:contain;background:#fff}",
        ".card .name{font-size:.8rem;font-family:monospace;word-break:break-all}",
        ".fail{border-color:#c00;background:#fff5f5}",
        ".meta{color:#555;font-size:.9rem}",
        "</style>",
        f"<h1>EventCalendar gallery — {html.escape(stamp)}</h1>",
        "<p class='meta'>"
        f"range {html.escape(args.begin)}–{html.escape(args.end)} · "
        f"{html.escape(args.papersize)} {html.escape(args.orientation)} · "
        f"weekends={args.weekends} · countries {html.escape(args.country)}"
        "</p>",
    ]

    for view in sorted(by_view):
        parts.append(f"<h2>{html.escape(view)}</h2><div class='grid'>")
        for res in sorted(by_view[view], key=lambda r: r.job.theme or ""):
            label = html.escape(res.job.theme or "(no theme)")
            failed = res.returncode != 0
            cls = "card fail" if failed else "card"
            parts.append(f"<div class='{cls}'>")
            if failed:
                parts.append(f"<div><b>{label}</b> — FAILED</div>")
                parts.append(
                    f"<pre class='meta'>{html.escape(res.output[-500:])}</pre>"
                )
            else:
                for path in res.files:
                    href = html.escape(path.name)
                    if path.suffix == ".svg":
                        parts.append(f"<a href='{href}'><img src='{href}'></a>")
                    parts.append(
                        f"<div class='name'><a href='{href}'>{href}</a></div>"
                    )
                parts.append(f"<div><b>{label}</b></div>")
            parts.append("</div>")
        parts.append("</div>")

    index_path.write_text("\n".join(parts), encoding="utf-8")
    return index_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate every visualization in every theme over one date range, "
            "for human side-by-side evaluation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Files are named <view>_<theme>_<YYYYMMDD-HHMMSS>.svg and written "
            "to output/ (ecalendar always confines SVG output there)."
        ),
    )
    parser.add_argument("begin", type=validate_date, help="Start date (YYYYMMDD)")
    parser.add_argument("end", type=validate_date, help="End date (YYYYMMDD)")
    parser.add_argument(
        "--themes",
        type=str,
        default=None,
        metavar="LIST",
        help="Comma-separated theme names (default: every installed theme)",
    )
    parser.add_argument(
        "--views",
        type=str,
        default=None,
        metavar="LIST",
        help=f"Comma-separated views (default: {','.join(SVG_VIEWS)})",
    )
    parser.add_argument(
        "--include-nonsvg",
        action="store_true",
        help=(
            "Also run the non-SVG views: "
            f"{', '.join(sorted(NONSVG_VIEWS))} (text-mini has no theme flag "
            "and is rendered once)"
        ),
    )
    parser.add_argument(
        "--papersize", type=str, default="Tabloid", help="Paper size (default: Tabloid)"
    )
    parser.add_argument(
        "--orientation",
        type=str,
        default="landscape",
        choices=["portrait", "landscape"],
        help="Page orientation (default: landscape)",
    )
    parser.add_argument(
        "--weekends",
        type=int,
        default=0,
        choices=[0, 1, 2, 3, 4],
        help="Weekend style (default: 0, work week only)",
    )
    parser.add_argument(
        "--country",
        type=str,
        default="US,UA",
        help="Holiday country codes (default: US,UA)",
    )
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=4,
        metavar="N",
        help="Parallel ecalendar processes (default: 4)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the commands that would run, then exit",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip writing the HTML contact sheet",
    )
    args = parser.parse_args(argv)

    if args.end < args.begin:
        parser.error("END_DATE must not be earlier than START_DATE")

    available = discover_themes()
    if not available:
        parser.error(f"no themes found (looked in {THEMES_DIR})")
    if args.themes:
        requested = [t.strip() for t in args.themes.split(",") if t.strip()]
        unknown = [t for t in requested if t not in available]
        if unknown:
            parser.error(
                f"unknown theme(s): {', '.join(unknown)}. "
                f"Available: {', '.join(available)}"
            )
        args.themes = requested
    else:
        args.themes = available

    valid_views = list(SVG_VIEWS) + sorted(NONSVG_VIEWS)
    if args.views:
        requested = [v.strip() for v in args.views.split(",") if v.strip()]
        unknown = [v for v in requested if v not in valid_views]
        if unknown:
            parser.error(
                f"unknown view(s): {', '.join(unknown)}. "
                f"Available: {', '.join(valid_views)}"
            )
        args.views = requested
    else:
        args.views = list(SVG_VIEWS)
        if args.include_nonsvg:
            args.views += sorted(NONSVG_VIEWS)

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    jobs = build_jobs(args, stamp)

    print(
        f"{len(jobs)} run(s): {len(args.views)} view(s) x "
        f"{len(args.themes)} theme(s) — {args.begin}..{args.end}, "
        f"{args.papersize} {args.orientation}, weekends={args.weekends}, "
        f"countries {args.country}"
    )

    if args.dry_run:
        for job in jobs:
            print("  " + " ".join(job.argv))
        return 0

    OUTPUT_DIR.mkdir(exist_ok=True)

    results: list[Result] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for res in pool.map(run_job, jobs):
            results.append(res)
            status = "ok " if res.returncode == 0 else "FAIL"
            names = ", ".join(p.name for p in res.files) or res.job.filename
            print(f"  [{status}] {names}")
            if res.returncode != 0:
                for line in res.output.splitlines()[-5:]:
                    print(f"         {line}")

    failures = [r for r in results if r.returncode != 0]
    produced = sum(len(r.files) for r in results if r.returncode == 0)
    print(f"\n{produced} file(s) written to {OUTPUT_DIR}")

    if not args.no_index:
        index = write_index(results, stamp, args)
        print(f"contact sheet: {index}")

    if failures:
        print(f"{len(failures)} run(s) failed:")
        for res in failures:
            print(f"  {res.job.view} / {res.job.theme}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
