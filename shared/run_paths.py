"""
Per-run output folder.

Every visualization run writes one folder under ``output/`` named after
its output stem, holding everything the run produced::

    output/<stem>/
        <stem>.svg          the visualization (``.txt`` for text-mini)
        <stem>_p2.svg       continuation pages, when the view paginates
        <stem>.md           the details document
        <stem>.csv          the event data the run included
        icons/              one uniform-size SVG per icon the run drew

:class:`RunPaths` names each of those once, so no writer builds a path
of its own.  The folder is reused when a run is repeated; ``prepare()``
clears only what a run writes, never anything else someone put there.
"""

from __future__ import annotations

import glob
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

#: Where every run folder is created.
OUTPUT_ROOT = Path("output")

#: Folder, under the run folder, that icon files are written to.
ICONS_DIRNAME = "icons"

_SLUG_UNSAFE = re.compile(r"[^a-z0-9-]+")


def slugify(text: str, fallback: str = "icon") -> str:
    """*text* reduced to ``[a-z0-9-]``: safe as a filename on any system."""
    slug = _SLUG_UNSAFE.sub("-", str(text or "").strip().lower()).strip("-")
    return slug or fallback


@dataclass(frozen=True)
class RunPaths:
    """Every path one run writes.

    Attributes:
        folder: The run folder, ``output/<stem>``.
        stem: The output name without its extension.
        main: The visualization file itself.
    """

    folder: Path
    stem: str
    main: Path

    @classmethod
    def for_output(cls, filename: str, root: Path = OUTPUT_ROOT) -> RunPaths:
        """The run paths for an ``--outputfile`` value.

        Only the basename is used: a directory in *filename* is discarded,
        so a run can never write outside its folder under *root*.  Callers
        validate the name first (see ``cli.args._to_run_paths``).
        """
        name = Path(filename).name
        stem = Path(name).stem or name
        folder = Path(root) / stem
        return cls(folder=folder, stem=stem, main=folder / name)

    def page(self, number: int) -> Path:
        """Page *number* of the visualization; page 1 is :attr:`main`."""
        if number == 1:
            return self.main
        suffix = self.main.suffix or ".svg"
        return self.folder / f"{self.stem}_p{number}{suffix}"

    @property
    def markdown(self) -> Path:
        return self.folder / f"{self.stem}.md"

    @property
    def csv(self) -> Path:
        return self.folder / f"{self.stem}.csv"

    @property
    def icons_dir(self) -> Path:
        return self.folder / ICONS_DIRNAME

    def icon(self, filename: str) -> Path:
        """An icon file's path; any directory in *filename* is discarded."""
        return self.icons_dir / Path(filename).name

    def owned_paths(self) -> list[Path]:
        """What a run writes into its folder, as it stands on disk now."""
        stem = glob.escape(self.stem)
        owned = {self.main, self.markdown, self.csv, self.icons_dir}
        owned.add(self.folder / f"{self.stem}.svg")
        owned.add(self.folder / f"{self.stem}.txt")
        if self.folder.is_dir():
            for pattern in (
                f"{stem}_p[0-9]*.*",
                # Companion pages from before the details document.
                f"{stem}_details*.svg",
                f"{stem}_key*.svg",
                f"{stem}_overflow*.svg",
            ):
                owned.update(self.folder.glob(pattern))
        return sorted(owned)

    def prepare(self) -> None:
        """Create the folder, clearing what an earlier run left in it.

        A shorter re-run must not leave the longer run's extra pages or
        icons beside its own, so everything this run could write is
        removed first.  Files it would never write are left alone.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        for path in self.owned_paths():
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    def files(self) -> list[Path]:
        """Every file now in the run folder, icons included."""
        if not self.folder.is_dir():
            return []
        return sorted(p for p in self.folder.rglob("*") if p.is_file())
