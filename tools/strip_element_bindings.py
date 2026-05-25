#!/usr/bin/env python3
"""
Strip per-theme `apply_to: element` rules into `element_overrides:`.

Targeted, idempotent counterpart to tools/migrate_theme.py.  Where the full
migrator rewrites legacy themes into the unified schema and can lose keys
the runtime considers dead, this script touches only the binding rules:

  * Every `style_rules` entry with ``apply_to: element`` is removed.
  * If the rule binds the same ec-class → ``<kind>:<name>`` pair as the
    built-in catalog (config/element_catalog.yaml), it is silently dropped.
  * Otherwise, the binding becomes one entry under a new top-level
    ``element_overrides:`` mapping.  Non-`use` style keys (currently
    ``color`` only) carry through.

Comments are preserved by editing the YAML lexically when possible; the
output is the same file with binding rules deleted and the
``element_overrides:`` block appended (or merged with an existing one).

Usage::

    uv run python tools/strip_element_bindings.py [FILE.yaml ...]

With no files, every YAML under ``config/themes/`` is processed in place.
A ``.bak`` copy is left next to the original on the first run only.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

# Repo root for catalog import.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from config.element_catalog import load_catalog


class _OrderedDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):  # type: ignore[override]
        return super().increase_indent(flow, False)


def _represent_ordered_dict(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


_OrderedDumper.add_representer(OrderedDict, _represent_ordered_dict)
_OrderedDumper.add_representer(dict, _represent_ordered_dict)


class _OrderedLoader(yaml.SafeLoader):
    pass


def _construct_ordered_mapping(loader, node):
    loader.flatten_mapping(node)
    return OrderedDict(loader.construct_pairs(node))


_OrderedLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_ordered_mapping,
)


def _strip_one(data: Any, *, catalog) -> tuple[OrderedDict, int, int]:
    """Return (new_data, dropped, hoisted).

    ``data`` is the parsed YAML tree.  The function mutates a copy: the
    input remains untouched.
    """
    if not isinstance(data, dict):
        return OrderedDict(), 0, 0

    out = OrderedDict(data)
    rules = out.get("style_rules") or []
    if not isinstance(rules, list):
        return out, 0, 0

    overrides: OrderedDict[str, dict[str, Any]] = OrderedDict(
        out.get("element_overrides") or {}
    )
    kept: list[Any] = []
    dropped = 0
    hoisted = 0
    for rule in rules:
        if not isinstance(rule, dict):
            kept.append(rule)
            continue
        apply_to = rule.get("apply_to")
        targets = (
            [apply_to] if isinstance(apply_to, str)
            else list(apply_to) if isinstance(apply_to, list)
            else []
        )
        if "element" not in targets:
            kept.append(rule)
            continue

        select = rule.get("select") or {}
        ec_value = select.get("element") if isinstance(select, dict) else None
        if isinstance(ec_value, str):
            ec_names = [ec_value]
        elif isinstance(ec_value, list):
            ec_names = [e for e in ec_value if isinstance(e, str)]
        else:
            ec_names = []

        style = rule.get("style") or {}
        use = style.get("use") if isinstance(style, dict) else None
        extras = {
            k: v for k, v in (style or {}).items()
            if k != "use" and k in {"color"}
        }

        for ec in ec_names:
            entry = catalog.get(ec)
            override: dict[str, Any] = {}
            if isinstance(use, str) and ":" in use:
                use_kind, _, use_token = use.partition(":")
                if entry is None or (use_kind, use_token) != (entry.kind, entry.token):
                    override["use"] = use
            override.update(extras)
            if override:
                overrides[ec] = override
                hoisted += 1
            else:
                dropped += 1

    out["style_rules"] = kept
    if overrides:
        out["element_overrides"] = overrides
    return out, dropped, hoisted


def _process_file(path: Path, *, catalog) -> tuple[int, int]:
    raw = yaml.load(path.read_text(), Loader=_OrderedLoader) or OrderedDict()
    new_data, dropped, hoisted = _strip_one(raw, catalog=catalog)
    if dropped + hoisted == 0:
        return 0, 0
    serialized = yaml.dump(
        new_data,
        Dumper=_OrderedDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    path.write_text(serialized)
    return dropped, hoisted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("files", nargs="*", help="theme YAML files to process")
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Skip writing .bak files (default: write one next to each rewritten file)",
    )
    args = parser.parse_args(argv)

    catalog = load_catalog()

    if args.files:
        paths = [Path(p) for p in args.files]
    else:
        paths = sorted((Path(__file__).resolve().parent.parent / "config" / "themes").glob("*.yaml"))

    total_dropped = total_hoisted = 0
    for path in paths:
        if not args.no_backup:
            bak = path.with_suffix(path.suffix + ".bak")
            if not bak.exists():
                shutil.copy2(path, bak)
        dropped, hoisted = _process_file(path, catalog=catalog)
        total_dropped += dropped
        total_hoisted += hoisted
        if dropped + hoisted:
            print(f"{path.name}: dropped {dropped} default binding(s), hoisted {hoisted} override(s)")
    print(f"total: {total_dropped} dropped, {total_hoisted} hoisted across {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
