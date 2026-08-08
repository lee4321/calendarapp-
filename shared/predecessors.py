"""Parse the dependency strings schedule tools write into structured links.

MS Project and its lookalikes export the predecessor and successor columns
as one delimited list per task: ``"12"``, ``"12FS+3d"``, ``"7SS,9FF-2d"``.
Each token names another task, optionally the link type, optionally a lag.
This module owns that grammar so every consumer -- the Gantt renderer, the
details page, exportdata -- reads :class:`Link` objects and never the raw
text.

References are ``events.source_id`` values, the identifier the source
system assigned, not the local ``events.id`` autoincrement key.  A token
that is nothing but digits is still a ``source_id``, not a row number.

Two deliberate limitations, both surfaced rather than hidden:

* ``,`` is always a list separator, so a decimal-comma lag (``"3FS+1,5d"``)
  splits into two tokens.  Exports that use a decimal comma use ``;`` as
  their list separator, which is handled.
* A lag that cannot be parsed does not discard the link.  The dependency
  is the primary information and lag is advisory, so the link survives
  with ``lag_days == 0.0``, the raw text is kept in ``lag_text``, and the
  token is reported through :func:`parse_links_with_rejects`.
* An untyped reference ending in a signed number ("TASK-3") is read as a
  reference plus lag only when the trailing part parses as a duration.
  Hex GUIDs stay intact because their tails do not; an identifier that
  genuinely ends "-3" will split.  Give such systems a typed link
  ("TASK-3FS") or a non-numeric tail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.duration_parser import parse_duration

#: The four MS Project dependency types.
LINK_TYPES: frozenset[str] = frozenset({"FS", "SS", "FF", "SF"})

#: Assumed when a token omits the type -- and the only type the v1 Gantt
#: renderer draws.
DEFAULT_LINK_TYPE: str = "FS"


@dataclass(frozen=True)
class Link:
    """One parsed dependency token.

    Attributes:
        ref: The predecessor's ``source_id``, exactly as written.
        type: ``"FS"``, ``"SS"``, ``"FF"`` or ``"SF"``, upper-cased.
        lag_days: Signed lag in days, or ``0.0`` when absent or
            unparseable.  Weeks and hours are converted through
            :func:`shared.duration_parser.parse_duration`, so the working
            calendar (8h day, 5d week) applies.
        lag_percent: Signed percentage lag (``"+50%"``) when the lag was
            written that way, else ``None``.  Mutually exclusive with a
            non-zero ``lag_days``.
        lag_elapsed: True for MS Project *elapsed* units (``"+3ed"``),
            which count calendar days rather than working days.
        lag_text: The lag exactly as written (``"+3d"``), or ``None``.
            Kept so an unparseable lag can still be reported.
    """

    ref: str
    type: str = DEFAULT_LINK_TYPE
    lag_days: float = 0.0
    lag_percent: float | None = None
    lag_elapsed: bool = False
    lag_text: str | None = None


#: List separators.  See the module docstring on the comma.
_SEPARATOR_RE = re.compile(r"[,;\n\r]+")

#: All whitespace is removed inside a token before matching, so
#: ``"12 FS + 3 d"`` and ``"12FS+3d"`` parse identically.
_WHITESPACE_RE = re.compile(r"\s+")

#: ``<ref><type>[±lag]``.  The type is only believed when it sits at the
#: end of the token or immediately before a sign, and when the reference
#: it follows ends in an alphanumeric -- so "12FS+3d" is typed but the
#: identifier "TASK-FS-3" is not.
_TYPED_RE = re.compile(
    r"""
    ^
    (?P<ref>.*[0-9A-Za-z])
    (?P<type>FS|SS|FF|SF)
    (?P<lag>[+-].*)?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

#: ``<ref>±lag`` for untyped tokens.  Only accepted when the body after
#: the sign is a lag this module can read, so the hex GUID
#: "A3F2-9C11-4E7B" stays one reference.
_UNTYPED_RE = re.compile(r"^(?P<ref>.+)(?P<lag>[+-][^+-]+)$")


#: An elapsed-unit lag: "3ed", "2ew".  The leading "e" marks calendar
#: time; the remainder is an ordinary duration unit.
_ELAPSED_RE = re.compile(r"^(?P<value>[\d.]+)e(?P<unit>[a-z]+)$", re.IGNORECASE)

#: A percentage lag: "50%".
_PERCENT_RE = re.compile(r"^(?P<value>[\d.]+)%$")


def parse_links(text) -> list[Link]:
    """Parse a predecessor/successor cell into links, dropping bad tokens.

    Args:
        text: Raw cell value.  ``None``, blanks and non-strings are
            handled and yield an empty list.

    Returns:
        The links in written order.  Duplicates are preserved; callers
        that care deduplicate on ``(ref, type)``.
    """
    return parse_links_with_rejects(text)[0]


def parse_links_with_rejects(text) -> tuple[list[Link], list[str]]:
    """Parse a cell, also returning the tokens that were not understood.

    The rejects are for the details page: a schedule whose dependencies
    silently fail to draw should say so rather than render an
    arrow-free chart.

    Args:
        text: Raw cell value.

    Returns:
        ``(links, rejected)``.  A token appears in *rejected* when no
        reference could be read from it (no link is produced) **or** when
        its lag was unparseable (the link is still produced, with zero
        lag).  Never raises: one bad cell should cost one field, not the
        whole row.
    """
    if text is None:
        return [], []
    if not isinstance(text, str):
        # A spreadsheet cell typed as a number: a lone source_id.
        text = str(text)

    links: list[Link] = []
    rejected: list[str] = []

    for raw_token in _SEPARATOR_RE.split(text):
        token = _WHITESPACE_RE.sub("", raw_token)
        if not token:
            continue

        ref, link_type, lag_text = _split_token(token)

        if not _is_reference(ref):
            rejected.append(raw_token.strip())
            continue

        lag_days = 0.0
        lag_percent: float | None = None
        lag_elapsed = False

        if lag_text is not None:
            lag_days, lag_percent, lag_elapsed, understood = _parse_lag(
                lag_text[0], lag_text[1:]
            )
            if not understood:
                rejected.append(raw_token.strip())

        links.append(
            Link(
                ref=ref,
                type=link_type,
                lag_days=lag_days,
                lag_percent=lag_percent,
                lag_elapsed=lag_elapsed,
                lag_text=lag_text,
            )
        )

    return links, rejected


def _split_token(token: str) -> tuple[str, str, str | None]:
    """Split one whitespace-free token into ``(ref, type, lag_text)``.

    A link type is read only where it is unambiguous (see :data:`_TYPED_RE`).
    Failing that, a trailing signed body is read as a lag only when it
    actually parses as one -- otherwise the token is all reference, which
    is what keeps hyphenated GUIDs intact.
    """
    typed = _TYPED_RE.match(token)
    if typed is not None:
        return typed.group("ref"), typed.group("type").upper(), typed.group("lag")

    untyped = _UNTYPED_RE.match(token)
    if untyped is not None:
        lag = untyped.group("lag")
        if _parse_lag(lag[0], lag[1:])[3]:
            return untyped.group("ref"), DEFAULT_LINK_TYPE, lag

    return token, DEFAULT_LINK_TYPE, None


def _is_reference(ref: str) -> bool:
    """True when *ref* can be a ``source_id``.

    Rejects the empty string, a bare link type ("FS" with nothing in
    front of it), anything opening with a sign, and anything carrying no
    alphanumeric at all.
    """
    if not ref or ref.upper() in LINK_TYPES:
        return False
    if ref[0] in "+-":
        return False
    return any(char.isalnum() for char in ref)


def _parse_lag(sign: str, lag: str) -> tuple[float, float | None, bool, bool]:
    """Resolve one lag body to ``(days, percent, elapsed, understood)``.

    *sign* is applied to whichever of days/percent the body produced.
    ``understood`` is False when the body is not a lag this module can
    read, in which case the caller keeps the link and reports the token.
    """
    negative = sign == "-"

    percent = _PERCENT_RE.match(lag)
    if percent is not None:
        value = float(percent.group("value"))
        return 0.0, -value if negative else value, False, True

    elapsed = _ELAPSED_RE.match(lag)
    if elapsed is not None:
        days = parse_duration(f"{elapsed.group('value')}{elapsed.group('unit')}")
        if days is None:
            return 0.0, None, True, False
        return (-days if negative else days), None, True, True

    days = parse_duration(lag)
    if days is None:
        return 0.0, None, False, False
    return (-days if negative else days), None, False, True
