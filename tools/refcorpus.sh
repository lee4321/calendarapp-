#!/usr/bin/env bash
# Reference SVG corpus — rendering-regression guard for consolidation work.
#
# Renders every SVG visualizer across three themes with fixed date ranges so
# refactors can be verified against a known-good baseline.
#
# Usage:
#   tools/refcorpus.sh render   # (re)build the baseline in output/_refcorpus/
#   tools/refcorpus.sh check    # re-render into output/_refcorpus_check/ and
#                               # diff against the baseline, ignoring the
#                               # <desc> metadata block (timestamp + argv)
#
# Exit status of `check` is non-zero if any file differs or is missing.
set -euo pipefail
cd "$(dirname "$0")/.."

CORPUS_DIR="output/_refcorpus"
CHECK_DIR="output/_refcorpus_check"
THEMES=(default dark corporate)

render_one() {
  local viz="$1" start="$2" end="$3"
  shift 3
  local name="$1"
  shift
  PYTHONPATH=. uv run python ecalendar.py "$viz" "$start" "$end" \
    -of "$name" --quiet "$@" >/dev/null
}

render_all() {
  local dest="$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  rm -rf output/refcorpus_*

  for th in "${THEMES[@]}"; do
    render_one weekly      20260101 20260331 "refcorpus_weekly_${th}.svg"      -th "$th"
    render_one mini        20260101 20261231 "refcorpus_mini_${th}.svg"        -th "$th" --weeknumbers
    render_one mini-icon   20260101 20261231 "refcorpus_mini_icon_${th}.svg"   -th "$th"
    render_one candybar    20260101 20261231 "refcorpus_candybar_${th}.svg"    -th "$th"
    render_one timeline    20260101 20261231 "refcorpus_timeline_${th}.svg"    -th "$th"
    render_one blockplan   20260101 20261231 "refcorpus_blockplan_${th}.svg"   -th "$th"
    render_one compactplan 20260309 20260424 "refcorpus_compactplan_${th}.svg" -th "$th"
    render_one pit         20260101 20261231 "refcorpus_pit_${th}.svg"         -th "$th"
    render_one gantt       20260101 20260331 "refcorpus_gantt_${th}.svg"       -th "$th"
  done
  # text-mini has no theme support; render once
  render_one text-mini 20260101 20261231 "refcorpus_text_mini.txt"

  mv output/refcorpus_* "$dest"/
  echo "Rendered $(find "$dest" -type f | wc -l | tr -d ' ') files into $dest"
}

# Strip the <desc>...</desc> block and the details document's Generated
# line (creation timestamp and argv legitimately differ between runs).
normalized() {
  perl -0pe 's/<desc>.*?<\/desc>//gs; s/^- \*\*Generated:\*\*.*$//mg' "$1"
}

check() {
  render_all "$CHECK_DIR"
  local fail=0 ref rel new
  # Each visualization writes a run folder, so compare the trees file by file.
  while IFS= read -r -d '' ref; do
    rel="${ref#"$CORPUS_DIR"/}"
    new="$CHECK_DIR/$rel"
    if [[ ! -f "$new" ]]; then
      echo "MISSING  $rel"
      fail=1
    elif ! diff -q <(normalized "$ref") <(normalized "$new") >/dev/null; then
      echo "DIFFERS  $rel"
      fail=1
    fi
  done < <(find "$CORPUS_DIR" -type f -print0 | sort -z)
  while IFS= read -r -d '' new; do
    rel="${new#"$CHECK_DIR"/}"
    [[ -f "$CORPUS_DIR/$rel" ]] || { echo "EXTRA    $rel"; fail=1; }
  done < <(find "$CHECK_DIR" -type f -print0 | sort -z)
  if [[ "$fail" -eq 0 ]]; then
    echo "Corpus check PASSED ($(find "$CORPUS_DIR" -type f | wc -l | tr -d ' ') files identical modulo <desc>)"
  else
    echo "Corpus check FAILED"
  fi
  return "$fail"
}

case "${1:-render}" in
  render) render_all "$CORPUS_DIR" ;;
  check)  check ;;
  *) echo "usage: $0 [render|check]" >&2; exit 2 ;;
esac
