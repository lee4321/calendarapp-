"""How each visible day is treated as a holiday, weekend or ordinary day, for every view.

:func:`resolve_day_styles` combines three things the views used to work out
separately: which non-working classes a day belongs to
(:func:`shared.day_classifier.classify_day`), the country flags carried by the
holiday rows themselves (:func:`shared.holiday_band.compute_holiday_band_days`),
and the theme's ``holidays`` block (fill colour and opacity, static icon).

A day in several classes takes its fill and static icon from the highest class
that sets one: federal holiday, then company holiday, then weekend.  A federal
holiday's country flags are separate from the static icon and win over it where
a view can draw only one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from config.theme_schema import DayClass, Holidays
from shared.day_classifier import classify_day
from shared.holiday_band import HolidayMark, compute_holiday_band_days

if TYPE_CHECKING:
    from config.config import CalendarConfig
    from shared.db_access import CalendarDB

#: Class name to the ``Holidays`` field that styles it, highest priority first.
PRIORITY: tuple[tuple[str, str], ...] = (
    ("federal_holiday", "federal"),
    ("company_holiday", "company"),
    ("weekend", "weekend"),
)


@dataclass(frozen=True)
class DayStyle:
    """What a view draws for one day."""

    classes: frozenset[str] = frozenset()
    fill: str | None = None
    fill_opacity: float = 1.0
    #: Static icon from the theme.
    icon: str | None = None
    #: Country flags of the holidays on this day.
    flags: tuple[HolidayMark, ...] = ()

    @property
    def is_nonworkday(self) -> bool:
        return bool(self.classes)

    @property
    def best_icon(self) -> str | None:
        """The first country flag if there is one, else the static icon."""
        return self.flags[0].icon if self.flags else self.icon


def style_for(classes: frozenset[str], holidays: Holidays) -> tuple[str | None, float, str | None]:
    """``(fill, opacity, icon)`` for a set of classes, from the highest class that sets each."""
    fill = opacity = icon = None
    for cls, field_name in PRIORITY:
        if cls not in classes:
            continue
        spec: DayClass = getattr(holidays, field_name)
        if fill is None and spec.color:
            fill, opacity = spec.color, spec.opacity
        if icon is None and spec.icon:
            icon = spec.icon
    return fill, 1.0 if opacity is None else opacity, icon


def resolve_day_styles(
    days: list[date],
    db: CalendarDB | None,
    config: CalendarConfig,
    holidays: Holidays,
    *,
    nonworkdays_only: bool = True,
) -> dict[date, DayStyle]:
    """A :class:`DayStyle` for every day in *days*.

    *nonworkdays_only* limits the country flags to holidays that close the
    office; pass ``False`` to flag observances as well.
    """
    flags = compute_holiday_band_days(days, db, config, nonworkdays_only=nonworkdays_only)
    out: dict[date, DayStyle] = {}
    for day in days:
        classes = classify_day(day, db, config)
        fill, opacity, icon = style_for(classes, holidays)
        out[day] = DayStyle(classes, fill, opacity, icon, tuple(flags.get(day, ())))
    return out
