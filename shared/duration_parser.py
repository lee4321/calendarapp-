"""
Parse human-written duration strings into decimal days.

Schedule exports write durations and work/effort as free text ("4hr",
"0.5d", "2w", "1d 4h", "-4h").  The ``events`` table keeps both: the raw
string in ``duration_text`` / ``effort_text`` and the parsed decimal-day
value in ``duration`` / ``effort``.  This module owns the parsing.

Conversion uses working-time, not wall-clock: a day is a workday, a week
is a work week.  The three constants below are the whole basis and are
the single place to change it.
"""

from __future__ import annotations

import re

#: Working hours in one day.
HOURS_PER_DAY: float = 8.0

#: Working days in one week.
DAYS_PER_WEEK: float = 5.0

#: Working days in one month.
DAYS_PER_MONTH: float = 20.0

#: Unit suffix -> multiplier in days.  Order matters only for the regex
#: alternation, which is built longest-first so "mo" wins over "m".
_UNIT_DAYS: dict[str, float] = {
    "minute": 1.0 / (HOURS_PER_DAY * 60.0),
    "minutes": 1.0 / (HOURS_PER_DAY * 60.0),
    "mins": 1.0 / (HOURS_PER_DAY * 60.0),
    "min": 1.0 / (HOURS_PER_DAY * 60.0),
    "m": 1.0 / (HOURS_PER_DAY * 60.0),
    "hour": 1.0 / HOURS_PER_DAY,
    "hours": 1.0 / HOURS_PER_DAY,
    "hrs": 1.0 / HOURS_PER_DAY,
    "hr": 1.0 / HOURS_PER_DAY,
    "h": 1.0 / HOURS_PER_DAY,
    "day": 1.0,
    "days": 1.0,
    "dy": 1.0,
    "d": 1.0,
    "week": DAYS_PER_WEEK,
    "weeks": DAYS_PER_WEEK,
    "wks": DAYS_PER_WEEK,
    "wk": DAYS_PER_WEEK,
    "w": DAYS_PER_WEEK,
    "month": DAYS_PER_MONTH,
    "months": DAYS_PER_MONTH,
    "mons": DAYS_PER_MONTH,
    "mon": DAYS_PER_MONTH,
    "mos": DAYS_PER_MONTH,
    "mo": DAYS_PER_MONTH,
}

# Longest-first so "mo"/"min" are preferred over the bare "m", and
# "hrs" over "hr" over "h".
_UNIT_ALTERNATION = "|".join(
    sorted((re.escape(u) for u in _UNIT_DAYS), key=len, reverse=True)
)

#: One "<number><unit>" term.  The unit is optional so a bare number
#: parses as days.  The trailing lookahead forbids a longer unit word
#: ("4hours" must consume "hours", not "h") while still allowing the
#: next term to follow immediately, as in "2w3d".
_TERM_RE = re.compile(
    rf"(?P<value>\d+(?:\.\d+)?|\.\d+)\s*(?P<unit>{_UNIT_ALTERNATION})?(?![A-Za-z])",
    re.IGNORECASE,
)

#: Characters stripped before parsing: schedule tools emit "4h?" for
#: estimated durations and "4 h" with stray spacing.  Commas surviving
#: normalize_decimal_separators() are not inside a number, so they are noise.
_NOISE_RE = re.compile(r"[?\s,]+")

#: A comma that groups thousands: preceded by a digit and followed by
#: exactly three more ("1,200" and "1,234,567", but not "1,5" or "1,50").
_THOUSANDS_COMMA_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

_DIGIT_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
_DIGIT_DOT_RE = re.compile(r"(?<=\d)\.(?=\d)")


def normalize_decimal_separators(text: str) -> str:
    """Resolve ',' and '.' down to a single decimal point.

    Locales disagree about which character separates decimals, so the
    rule is positional rather than assumed:

    * When both appear, the *later* one is the decimal separator and the
      earlier groups thousands -- "1,234.5" and "1.234,5" both mean
      1234.5.
    * A lone comma groups thousands only when exactly three digits
      follow it ("1,200" -> 1200); otherwise it is a decimal comma
      ("1,5" -> 1.5).

    The one genuine ambiguity, a decimal comma with three places
    ("1,500" meaning one and a half), resolves as thousands.  That is the
    conventional reading, and three-decimal-place durations do not occur
    in practice.
    """
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")

    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:
            # European: dots group, the comma carries the decimal.
            return _DIGIT_COMMA_RE.sub(".", _DIGIT_DOT_RE.sub("", text))
        # Anglo: commas group, the dot already carries the decimal.
        return _DIGIT_COMMA_RE.sub("", text)

    text = _THOUSANDS_COMMA_RE.sub("", text)
    return _DIGIT_COMMA_RE.sub(".", text)


def parse_duration(text) -> float | None:
    """Convert a duration string to decimal days.

    Accepts a single term ("4hr", "0.5d"), a compound of terms
    ("1d 4h", "2w3d"), a bare number (taken as days), and an optional
    leading sign so the variance fields ("-4h") parse too.

    ``m`` means *minutes*, not months -- months require ``mo`` or longer.
    This follows the schedule exports the importer reads, where minutes
    are common and months are always spelled out.

    Args:
        text: Raw source value.  Numbers, ``None`` and blanks are handled.

    Returns:
        Decimal days, or ``None`` when nothing parseable is present.
        Never raises -- an unparseable cell should cost one field, not
        the whole row.
    """
    if text is None:
        return None

    # Already numeric (a spreadsheet cell typed as a number) -> days.
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)

    raw = str(text).strip()
    if not raw:
        return None

    negative = raw.startswith("-")
    if raw[0] in "+-":
        raw = raw[1:]

    # Separators are resolved before noise is stripped -- otherwise the
    # comma in "1,5" would be discarded and the value read as 15.
    cleaned = _NOISE_RE.sub("", normalize_decimal_separators(raw))
    if not cleaned:
        return None

    total = 0.0
    matched_span = 0
    for match in _TERM_RE.finditer(cleaned):
        unit = (match.group("unit") or "d").lower()
        total += float(match.group("value")) * _UNIT_DAYS[unit]
        matched_span += len(match.group(0))

    # Require the whole string to be accounted for; "4hr of prep" and
    # "n/a" should both fail rather than silently yielding 0.5 days.
    if matched_span != len(cleaned):
        return None

    return -total if negative else total
