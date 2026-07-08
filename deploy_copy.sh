#!/usr/bin/env bash
# deploy_copy.sh — copy only the files ecalendar.py needs at runtime into a
# destination folder, so the program can be moved to another computer.
#
# Usage: ./deploy_copy.sh <destination-folder>
#
# On the new machine (with uv installed), run from inside the folder:
#   uv run python ecalendar.py --help
# The first run creates the virtualenv from pyproject.toml + uv.lock.
#
# Deliberately excluded: tests/, tools/, tui/, "db utils/", docs,
# SVG/txt outputs, sample import data (importers/*.csv, palettes.txt,
# importers/calendar.db), backups, caches.

set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:?Usage: $0 <destination-folder>}"

mkdir -p "$DEST"

# --- Entry point and uv project files -------------------------------------
cp "$SRC/ecalendar.py" "$SRC/pyproject.toml" "$SRC/uv.lock" "$DEST/"

# Pin the Python minor version only. The local .python-version pins a full
# platform triple (macos-aarch64) that would not resolve on other machines.
echo "3.14" > "$DEST/.python-version"

# --- Event/holiday/pattern/icon database (read from CWD by default) -------
cp "$SRC/calendar.db" "$DEST/"

# --- Python packages: code files only, keep directory structure -----------
# slint_ui (the GUI) also needs its *.slint markup, loaded relative to the
# module file at runtime; importers ship code only — their input files
# (CSVs, icon folders) are supplied by the user via CLI arguments.
for pkg in cli config shared renderers visualizers vendor importers slint_ui; do
  rsync -a --prune-empty-dirs \
    --exclude='__pycache__/' \
    --include='*/' \
    --include='*.py' \
    --include='*.slint' \
    --exclude='*' \
    "$SRC/$pkg/" "$DEST/$pkg/"
done

# --- Data files loaded by the config package at runtime --------------------
cp "$SRC/config/element_catalog.yaml" \
   "$SRC/config/element_catalog_defaults.yaml" \
   "$DEST/config/"

mkdir -p "$DEST/config/themes"
cp "$SRC"/config/themes/*.yaml "$DEST/config/themes/"

# --- Fonts: scanned at import time by config.config._build_font_registry() -
mkdir -p "$DEST/fonts"
cp "$SRC"/fonts/*.ttf "$SRC"/fonts/*.otf "$DEST/fonts/"

echo "Done. Copied runtime files to: $DEST"
echo "Verify on the target machine with: cd '$DEST' && uv run python ecalendar.py --help"
