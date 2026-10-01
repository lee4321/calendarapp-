"""Does a rule's ``select`` hold for a context of selector facts?

Used where a rule is checked against a plain dictionary (an icon's event context)
rather than against an event, which :mod:`shared.rule_engine` matches.
"""

from __future__ import annotations

from typing import Any


def select_matches(select: dict[str, Any], context: dict[str, Any]) -> bool:
    """True if every key in ``select`` is satisfied by ``context``.

    Empty ``select`` matches everything.  Predicate semantics:

    * String key with list-valued ``select`` value matches if ``context[key]``
      is in the list.
    * String key with scalar value matches on equality.
    * ``priority_min`` / ``priority_max`` / ``percent_complete: {min, max}``
      are recognized as range predicates.  A ``<field>_min`` / ``<field>_max``
      selector key resolves against ``context[<field>]`` when the literal key
      is absent — so ``select: { priority_min: 1 }`` matches a context that
      binds ``priority`` (the design's documented form).

    A rule with a constraint on key ``X`` does *not* apply unless the context
    binds ``X`` (or its base field for range predicates).  Rules opt into
    contexts; they don't fall through unmatched.  An empty ``select`` is the
    explicit "always applies" form and is how token definitions are written.
    """
    for key, want in select.items():
        if key in context:
            have = context[key]
        elif key.endswith(("_min", "_max")) and key[:-4] in context:
            have = context[key[:-4]]
        else:
            # Constraint not satisfied — context hasn't bound this key
            # (or its base field for range predicates).
            return False
        if not _value_matches(want, have, key=key):
            return False
    return True


def _value_matches(want: Any, have: Any, *, key: str) -> bool:
    # Range predicate
    if isinstance(want, dict):
        lo = want.get("min")
        hi = want.get("max")
        try:
            n = float(have)
        except (TypeError, ValueError):
            return False
        if lo is not None and n < float(lo):
            return False
        return not (hi is not None and n > float(hi))

    # priority_min / priority_max keys
    if key.endswith("_min"):
        try:
            return float(have) >= float(want)
        except (TypeError, ValueError):
            return False
    if key.endswith("_max"):
        try:
            return float(have) <= float(want)
        except (TypeError, ValueError):
            return False

    # List-valued selector — substring match on string contexts, exact-match
    # on others.  Case-insensitive for strings.
    if isinstance(want, list):
        return any(_scalar_matches(item, have, key=key) for item in want)

    return _scalar_matches(want, have, key=key)


# Selector keys matched whole, as shared.rule_engine matches them: a
# resource group of "a" is not every group with an "a" in its name.
_EXACT_KEYS: frozenset[str] = frozenset({"resource_group"})


def _scalar_matches(want: Any, have: Any, *, key: str = "") -> bool:
    if key in _EXACT_KEYS and isinstance(want, str) and isinstance(have, str):
        return want.strip().lower() == have.strip().lower()
    if isinstance(want, str) and isinstance(have, str):
        return want.lower() in have.lower()
    return want == have
