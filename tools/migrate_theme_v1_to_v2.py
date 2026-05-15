#!/usr/bin/env python3
"""
Migrate CalendarApp theme YAML files from legacy rule keys to the unified
style_rules / swimlane_rules format.

Conversions performed:
  weekly.day_box.hash_rules          → style_rules (apply_to: day_box)
  mini_calendar.day_box.hash_rules   → style_rules (apply_to: day_box)
  blockplan.swimlanes[].match        → swimlane_rules
  blockplan.vertical_lines           → style_rules (apply_to: vertical_line)

Uses text-level surgery so that YAML comments in the rest of the file are
preserved.  New rule blocks are appended at the end of the file.

Usage:
  uv run python tools/migrate_theme.py [file.yaml ...]
  uv run python tools/migrate_theme.py          # migrates all config/themes/*.yaml
"""

from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Any

import yaml

THEMES_DIR = Path(__file__).parent.parent / "config" / "themes"


# ── Criteria name mappings ────────────────────────────────────────────────────

_WHEN_TO_SELECT: dict[str, str] = {
    "milestone": "milestone",
    "nonworkday": "nonworkday",
    "federal_holiday": "federal_holiday",
    "notes": "notes",
    "percent_complete": "percent_complete",
    "resource_names": "resource_names",
    "resource_group": "resource_group",
    "resource_groups": "resource_group",   # plural alias
}

_MATCH_TO_SELECT: dict[str, str] = {
    "resource_groups": "resource_group",
    "groups": "resource_group",
    "resource_names_contains": "resource_names",
    "task_contains": "task_name",
    "notes_contains": "notes",
    "milestone": "milestone",
    "rollup": "rollup",
    "event_type": "event_type",
    "priority": "priority",
    "priority_min": "priority_min",
    "priority_max": "priority_max",
}


# ── Block extent helper ───────────────────────────────────────────────────────


def _block_extent(lines: list[str], header_idx: int) -> tuple[int, int]:
    """
    Return (start, end) where start == header_idx and end is the exclusive
    line index of the first non-blank non-comment line at indent ≤ header indent.
    """
    if header_idx >= len(lines):
        return header_idx, header_idx + 1
    header_indent = len(lines[header_idx]) - len(lines[header_idx].lstrip())
    end = header_idx + 1
    while end < len(lines):
        line = lines[end]
        stripped = line.rstrip()
        if stripped == "" or stripped.lstrip().startswith("#"):
            end += 1
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= header_indent:
            break
        end += 1
    return header_idx, end


# ── Rule conversion helpers ───────────────────────────────────────────────────


def _wbs_list_to_filter(v: Any) -> str:
    if isinstance(v, list):
        return ",".join(str(p) for p in v if str(p).strip())
    return str(v)


def _convert_hash_rule_when(when: dict) -> dict:
    select: dict = {}

    for old_key, new_key in _WHEN_TO_SELECT.items():
        if old_key not in when:
            continue
        val = when[old_key]
        if new_key in select:
            existing = select[new_key]
            new_list = val if isinstance(val, list) else [val]
            merged = existing if isinstance(existing, list) else [existing]
            for v in new_list:
                if v not in merged:
                    merged.append(v)
            select[new_key] = merged
        else:
            select[new_key] = val

    if "event_names" in when:
        select["task_name"] = when["event_names"]
        if "duration_names" not in when:
            select["event_type"] = "event"

    if "duration_names" in when:
        dur = when["duration_names"]
        if "task_name" not in select:
            select["task_name"] = dur
            select["event_type"] = "duration"
        else:
            existing = select["task_name"]
            new_list = dur if isinstance(dur, list) else [dur]
            merged = existing if isinstance(existing, list) else [existing]
            for v in new_list:
                if v not in merged:
                    merged.append(v)
            select["task_name"] = merged
            select.pop("event_type", None)

    if "wbs" in when:
        select["wbs"] = _wbs_list_to_filter(when["wbs"])

    if "percent_complete" in select:
        raw = select["percent_complete"]
        if raw is True or str(raw) in ("100", "100.0"):
            select["percent_complete"] = {"min": 100}

    return select


def _convert_hash_rules(hash_rules: list, source: str) -> list[dict]:
    out = []
    for i, rule in enumerate(hash_rules):
        if not isinstance(rule, dict):
            continue
        pattern_name = rule.get("pattern")
        if not pattern_name:
            continue
        when = rule.get("when") or {}
        if not when:
            continue
        select = _convert_hash_rule_when(when)
        if not select:
            continue
        style: dict = {"pattern": str(pattern_name)}
        if "color" in rule:
            style["pattern_color"] = rule["color"]
        if "opacity" in rule:
            style["pattern_opacity"] = rule["opacity"]
        entry: dict = {
            "name": f"{source}_{i}",
            "select": select,
            "apply_to": "day_box",
            "style": style,
        }
        if "min_match" in rule:
            entry["min_match"] = rule["min_match"]
        out.append(entry)
    return out


def _parse_lane_name(lines: list[str], search_from: int) -> str:
    """Find the nearest parent swimlane name by scanning backward."""
    for i in range(search_from, max(search_from - 25, -1), -1):
        m = re.match(r"(\s+)- name:", lines[i])
        if m:
            # Parse this line + following lines as a YAML mapping to get the real name
            # (handles YAML string escapes like \n correctly)
            snippet = lines[i].lstrip("- ").lstrip()  # "name: ..."
            try:
                parsed = yaml.safe_load(snippet)
                if isinstance(parsed, dict) and "name" in parsed:
                    return str(parsed["name"])
            except yaml.YAMLError:
                pass
            # Fallback: regex strip
            raw_m = re.match(r"\s+- name:\s+(.+)", lines[i])
            if raw_m:
                return raw_m.group(1).strip().strip("\"'")
        if re.match(r"^[a-z]", lines[i]):
            break
    return ""


def _convert_swimlane_match(lane_name: str, match_dict: dict) -> dict | None:
    if not lane_name or not match_dict:
        return None
    select: dict = {}
    for old_key, new_key in _MATCH_TO_SELECT.items():
        if old_key not in match_dict:
            continue
        val = match_dict[old_key]
        if new_key in select:
            existing = select[new_key]
            merged = existing if isinstance(existing, list) else [existing]
            for v in (val if isinstance(val, list) else [val]):
                if v not in merged:
                    merged.append(v)
            select[new_key] = merged
        else:
            select[new_key] = val
    if "wbs_prefixes" in match_dict:
        select["wbs"] = _wbs_list_to_filter(match_dict["wbs_prefixes"])
    if not select:
        return None
    first_line = lane_name.splitlines()[0] if lane_name else ""
    return {
        "name": f"Route {first_line}",
        "select": select,
        "apply_to": lane_name,
    }


# ── vertical_lines conversion ─────────────────────────────────────────────────


_VLINE_DAY_KEYS: frozenset[str] = frozenset(
    {"weekend", "federal_holiday", "company_holiday", "nonworkday", "workday", "date"}
)


def _convert_vertical_lines(items: list, source: str) -> list[dict]:
    """Convert legacy ``blockplan.vertical_lines`` entries into ``style_rules``.

    Each input item maps to one rule with ``apply_to: vertical_line``.
    Selection keys (band/value/repeat) and the day-class keys hoisted from
    ``match:`` go into ``select:``. Rendering keys (color/width/opacity/
    dash_array/fill_color/fill_opacity/align) go into ``style:`` using the
    unified ``stroke_*`` / ``fill_*`` names.
    """
    out: list[dict] = []
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue

        select: dict = {}
        if item.get("band") is not None or item.get("band_label") is not None:
            band = item.get("band") if item.get("band") is not None else item.get("band_label")
            select["band"] = band
        if "value" in item and item["value"] is not None:
            select["value"] = item["value"]
        if bool(item.get("repeat", False)):
            select["repeat"] = True

        match = item.get("match")
        if isinstance(match, dict):
            for k in _VLINE_DAY_KEYS:
                if k in match:
                    select[k] = match[k]

        style: dict = {}
        if "align" in item and item["align"] is not None:
            style["align"] = item["align"]
        if "color" in item and item["color"] is not None:
            style["stroke_color"] = item["color"]
        if "width" in item and item["width"] is not None:
            style["stroke_width"] = item["width"]
        if "opacity" in item and item["opacity"] is not None:
            style["stroke_opacity"] = item["opacity"]
        # Accept either dash_array or dasharray (renderer accepted both).
        for k in ("dash_array", "dasharray"):
            if k in item and item[k] is not None:
                style["stroke_dasharray"] = item[k]
                break
        if "fill_color" in item and item["fill_color"] is not None:
            style["fill_color"] = item["fill_color"]
        if "fill_opacity" in item and item["fill_opacity"] is not None:
            style["fill_opacity"] = item["fill_opacity"]

        if not select:
            continue
        entry: dict = {
            "name": f"{source}_{i}",
            "apply_to": "vertical_line",
            "select": select,
            "style": style,
        }
        out.append(entry)
    return out


# ── YAML text generation ──────────────────────────────────────────────────────


def _rules_to_yaml_text(rules: list[dict], top_key: str) -> str:
    """Render a list of rule dicts as top-level YAML text."""
    if not rules:
        return f"{top_key}: []\n"
    body = yaml.dump(
        rules, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    indented = "".join(
        "  " + line if line.strip() else line for line in body.splitlines(keepends=True)
    )
    return f"{top_key}:\n{indented}"


# ── Per-file migration ────────────────────────────────────────────────────────


def migrate_text(text: str) -> tuple[str, list[str]]:
    """
    Apply all migrations to raw YAML text, preserving comments.
    Returns (new_text, list_of_change_descriptions).
    """
    lines = text.splitlines(keepends=True)
    changes: list[str] = []
    new_style_rules: list[dict] = []
    new_swimlane_rules: list[dict] = []

    # ── hash_rules (inline [] and null variants) ──────────────────────────────
    # Pattern: "    hash_rules: []"  or  "    hash_rules: null"
    inline_re = re.compile(r"^(\s+)hash_rules:\s*(\[\]|null)?\s*$")
    i = 0
    while i < len(lines):
        m = inline_re.match(lines[i])
        if m:
            val_part = (m.group(2) or "").strip()
            if val_part in ("[]", "null", ""):
                # Might be a block form or an empty inline form
                _, end = _block_extent(lines, i)
                block_text = "".join(lines[i:end])
                try:
                    parsed = yaml.safe_load(block_text)
                except yaml.YAMLError:
                    parsed = None

                label = "hash_rules"
                # Identify context
                for j in range(i - 1, max(i - 40, -1), -1):
                    cm = re.match(r"^(mini_calendar|weekly):", lines[j])
                    if cm:
                        label = cm.group(1).replace("mini_calendar", "mini") + "_hash"
                        break

                converted: list[dict] = []
                if isinstance(parsed, dict) and "hash_rules" in parsed:
                    rules_list = parsed.get("hash_rules") or []
                    if rules_list:
                        converted = _convert_hash_rules(rules_list, label)
                        if converted:
                            new_style_rules.extend(converted)
                            changes.append(
                                f"{label.replace('_hash', '.day_box.hash_rules')}: "
                                f"converted {len(converted)} rule(s) → style_rules"
                            )

                if not converted:
                    changes.append(
                        f"hash_rules (line {i+1}): removed empty/null"
                    )

                del lines[i:end]
                # Don't increment i — re-check the same position
            else:
                i += 1
        else:
            i += 1

    # ── blockplan.swimlanes[].match ───────────────────────────────────────────
    match_re = re.compile(r"^(\s+)match:\s*")
    i = 0
    while i < len(lines):
        m = match_re.match(lines[i])
        if not m:
            i += 1
            continue

        # Verify this match: is inside a swimlane (not a vertical_line match)
        in_swimlane = False
        for j in range(i - 1, max(i - 25, -1), -1):
            if re.match(r"\s+- name:", lines[j]):
                in_swimlane = True
                break
            if re.match(r"^[a-z]", lines[j]):
                break
        if not in_swimlane:
            i += 1
            continue

        lane_name = _parse_lane_name(lines, i - 1)
        _, end = _block_extent(lines, i)
        block_text = "".join(lines[i:end])
        try:
            parsed = yaml.safe_load(block_text)
        except yaml.YAMLError:
            parsed = None

        if isinstance(parsed, dict) and "match" in parsed:
            match_dict = parsed["match"] or {}
            entry = _convert_swimlane_match(lane_name, match_dict)
            if entry:
                new_swimlane_rules.append(entry)
                changes.append(f"swimlane[{lane_name!r}].match → swimlane_rules")

        del lines[i:end]
        # Don't increment i

    # ── blockplan.vertical_lines ──────────────────────────────────────────────
    vlines_re = re.compile(r"^(\s+)vertical_lines:\s*(\[\]|null)?\s*$")
    i = 0
    while i < len(lines):
        m = vlines_re.match(lines[i])
        if not m:
            i += 1
            continue

        # Confirm this is under `blockplan:` (not e.g. excelheader:).
        in_blockplan = False
        for j in range(i - 1, max(i - 200, -1), -1):
            cm = re.match(r"^([a-z_][a-z_0-9]*):\s*$", lines[j])
            if cm:
                in_blockplan = cm.group(1) == "blockplan"
                break
        if not in_blockplan:
            i += 1
            continue

        _, end = _block_extent(lines, i)
        block_text = "".join(lines[i:end])
        try:
            parsed = yaml.safe_load(block_text)
        except yaml.YAMLError:
            parsed = None

        if isinstance(parsed, dict) and "vertical_lines" in parsed:
            items = parsed.get("vertical_lines") or []
            if items:
                converted = _convert_vertical_lines(items, "blockplan_vline")
                if converted:
                    new_style_rules.extend(converted)
                    changes.append(
                        f"blockplan.vertical_lines: converted {len(converted)} "
                        "rule(s) → style_rules"
                    )
            else:
                changes.append(
                    f"blockplan.vertical_lines (line {i+1}): removed empty/null"
                )

        del lines[i:end]
        # Don't increment i — re-check the same position.

    # ── Assemble output ───────────────────────────────────────────────────────
    if not changes:
        return text, []

    new_text = "".join(lines).rstrip("\n") + "\n"

    if new_style_rules:
        new_text = _append_to_top_level_list(
            new_text, "style_rules", new_style_rules
        )
    if new_swimlane_rules:
        new_text = _append_to_top_level_list(
            new_text, "swimlane_rules", new_swimlane_rules
        )

    return new_text, changes


def _append_to_top_level_list(text: str, top_key: str, items: list[dict]) -> str:
    """Append ``items`` to an existing top-level ``top_key:`` list block, or
    create the block if it does not yet exist.

    Avoids producing duplicate top-level keys when the migrator is run multiple
    times (each pass needs to add to the same list, not start a new one).
    """
    body = yaml.dump(
        items, default_flow_style=False, allow_unicode=True, sort_keys=False
    )
    indented = "".join(
        "  " + line if line.strip() else line for line in body.splitlines(keepends=True)
    )

    pattern = re.compile(
        rf"^{re.escape(top_key)}:\s*$", re.MULTILINE
    )
    matches = list(pattern.finditer(text))
    if not matches:
        # Block doesn't exist — create it at end.
        sep = "" if text.endswith("\n") else "\n"
        return f"{text}{sep}\n{top_key}:\n{indented}"

    # Append into the existing block (the last occurrence, so later runs
    # extend it rather than the empty placeholder some themes start with).
    last = matches[-1]
    block_end = _find_top_level_block_end(text, last.end())
    insertion = indented if text[block_end - 1:block_end] == "\n" else "\n" + indented
    return text[:block_end] + insertion + text[block_end:]


def _find_top_level_block_end(text: str, start: int) -> int:
    """Return the index in *text* just after the last line of the top-level
    block that begins at *start*. A top-level block ends at the next line that
    has indent == 0 and starts with a non-blank, non-comment character.
    """
    pos = start
    n = len(text)
    while pos < n:
        nl = text.find("\n", pos)
        if nl == -1:
            return n
        line = text[pos:nl]
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not line.startswith((" ", "\t")):
            return pos
        pos = nl + 1
    return n


def migrate_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, changes = migrate_text(text)
    if not changes:
        print(f"  OK   {path.name}: nothing to migrate")
        return
    if new_text == text:
        print(f"  OK   {path.name}: no textual change")
        return
    path.write_text(new_text, encoding="utf-8")
    for change in changes:
        print(f"  MIGRATED {path.name}: {change}")


def main(argv: list[str]) -> None:
    if argv:
        paths = [Path(p) for p in argv]
    else:
        paths = sorted(THEMES_DIR.glob("*.yaml"))
    for path in paths:
        migrate_file(path)


if __name__ == "__main__":
    main(sys.argv[1:])
