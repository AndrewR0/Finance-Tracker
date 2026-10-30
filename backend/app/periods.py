"""Month / Year / All: turn "which period am I looking at?" into date ranges.

The dashboard says "Month, around Oct 23". This module turns that into
start=Oct 1, end=Oct 23, and a compare range of Sep 1-23 ("the same point
last month"). Pure functions only: no database, no clock. The router passes
today in, so tests can pick any day they like.
"""

import calendar
import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class PeriodKind(StrEnum):
    MONTH = "month"
    YEAR = "year"
    ALL = "all"


@dataclass(frozen=True)
class Period:
    kind: PeriodKind
    start: dt.date
    end: dt.date  # never after today
    compare_start: dt.date | None  # None for ALL: there's no earlier period
    compare_end: dt.date | None


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def bounds(kind: PeriodKind, anchor: dt.date) -> tuple[dt.date, dt.date]:
    """First and last day of the month or year that contains anchor."""
    if kind == PeriodKind.MONTH:
        return anchor.replace(day=1), anchor.replace(day=days_in_month(anchor.year, anchor.month))
    return dt.date(anchor.year, 1, 1), dt.date(anchor.year, 12, 31)


def one_period_back(day: dt.date, kind: PeriodKind) -> dt.date:
    """The same day, one month or one year earlier."""
    if kind == PeriodKind.MONTH:
        year, month = (day.year, day.month - 1) if day.month > 1 else (day.year - 1, 12)
    elif kind == PeriodKind.YEAR:
        year, month = day.year - 1, day.month
    else:
        raise ValueError(f"Can't step back one {kind} period.")
    return dt.date(year, month, min(day.day, days_in_month(year, month)))

def resolve_period(
    kind: PeriodKind,
    anchor: dt.date,
    today: dt.date,
    first_day: dt.date | None = None,
) -> Period:
    """The date ranges for the period that contains anchor.

    first_day: the earliest transaction date, only used for ALL (None = no transactions yet).
    Raises ValueError if the period starts after today.
    """
    if kind == PeriodKind.ALL:
        start = min(first_day, today) if first_day else today
        return Period(kind, start, today, None, None)

    start, last = bounds(kind, anchor)
    if start > today:
        raise ValueError("That period hasn't started yet.")

    end = min(last, today)
    compare_start = one_period_back(start, kind)
    if end == last:
        # A finished period is compared with the whole previous one: all of Sep vs all of Aug,
        # not Sep 1-30 vs Aug 1-30.
        _, compare_end = bounds(kind, compare_start)
    else:
        compare_end = one_period_back(end, kind)
    return Period(kind, start, end, compare_start, compare_end)
