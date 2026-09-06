"""
Shared label format for government holidays in detail listings.

Every view that lists holidays alongside their dates — the text-mini details
block, the mini details page, the compactplan roster — prefixes the holiday
name with its ISO 3166-1 alpha-2 country code::

    07/15 UA - Ukrainian Statehood Day

A calendar can carry several countries at once (``--country US,CA,UA``), and
without the code a reader cannot tell whose holiday a row describes — worse,
countries share holiday *names*, so 1 January lists "New Year's Day" twice
with nothing to distinguish the rows.

Company special days come from the ``specialdays`` table rather than a
government holiday calendar and carry no country code, so they are never
prefixed.
"""

from __future__ import annotations


def format_holiday_label(name: str | None, country: str | None) -> str:
    """Return *name* prefixed with its two-letter *country* code.

    Args:
        name: The holiday's display name.
        country: ISO 3166-1 alpha-2 code, or several joined by ", " when one
            row stands for the same-named holiday in more than one country.
            Falsy values (a special day, an unattributed row) yield the bare
            name, so callers need no conditional of their own.

    Returns:
        ``"UA - Ukrainian Statehood Day"``, or the bare name when there is no
        country code to add.
    """
    name = (name or "").strip()
    code = (country or "").strip()
    if not code or not name:
        return name
    return f"{code} - {name}"
