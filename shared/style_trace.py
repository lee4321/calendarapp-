"""
Style trace: a step-by-step account of how theme rules change what is drawn.

Enabled by ``--trace-style`` (or ``enable()``).  Lines go to stderr through
the ``ecalendar.style_trace`` logger, independent of ``-v``/``-q``, so a theme
developer sees only the trace, not every DEBUG message in the program.

One line per decision, each naming the element it concerns:

    day 20260704  rule 'federal holiday'  APPLY  fill=#FFD0D0 (was '#EEE' from rule 'month shade')
    event 'Launch' [20260310]  rule 'milestones'  SKIP  select: event fields did not match
    day 20260705  RESULT  no style rule matched; renderer/theme defaults apply
"""

from __future__ import annotations

import logging
import sys
from typing import Any

TRACE = logging.getLogger("ecalendar.style_trace")


def enable() -> None:
    """Route trace lines to stderr, whatever the root logger's level."""
    if TRACE.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("TRACE %(message)s"))
    TRACE.addHandler(handler)
    TRACE.setLevel(logging.DEBUG)
    TRACE.propagate = False


def enabled() -> bool:
    return TRACE.isEnabledFor(logging.DEBUG)


def emit(subject: str, what: str, detail: str = "") -> None:
    """Log one trace line: ``subject  what  detail`` (no-op when disabled)."""
    if enabled():
        TRACE.debug("%s  %s%s", subject, what, f"  {detail}" if detail else "")


def rule_label(rule: dict, index: int | None = None) -> str:
    name = rule.get("name")
    if name:
        return f"rule {str(name)!r}"
    return f"rule #{index}" if index is not None else "rule <unnamed>"


def fmt(value: Any) -> str:
    return repr(value) if isinstance(value, str) else str(value)


def layer_changes(before: dict, after: dict, rule_fields: dict, owners: dict, label: str) -> str:
    """Describe what one rule did to an accumulating result.

    ``before``/``after`` are flattened snapshots around the merge,
    ``rule_fields`` the rule's own snapshot, ``owners`` the field → rule-label
    provenance (updated in place).
    """
    parts: list[str] = []
    for key, new in rule_fields.items():
        old = before.get(key)
        if after.get(key) == old:
            parts.append(f"{key}={fmt(new)} (no change; already set by {owners.get(key, 'an earlier rule')})")
        elif old is None:
            parts.append(f"{key}={fmt(after[key])}")
        else:
            parts.append(f"{key}={fmt(after[key])} (was {fmt(old)} from {owners.get(key, 'an earlier rule')})")
        owners[key] = label
    return "; ".join(parts) if parts else "matched, but its style sets nothing"


def summary(owners: dict, final: dict) -> str:
    if not final:
        return "no style rule matched; renderer/theme defaults apply"
    return "; ".join(f"{k}={fmt(v)} [{owners.get(k, '?')}]" for k, v in final.items())
