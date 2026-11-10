"""Recurring spending: find payees you pay on a steady schedule, and predict the next charge.

Nothing here is stored. Series are derived from your transactions every time, the same way
holdings will be derived from trades. The only stored piece is your "ignore this one" choice
(RecurringSeries), applied by the router.

detect_series() is a pure function (charges in, series out) so it's easy to test.
"""

import calendar
import datetime as dt
import enum
from dataclasses import dataclass
from statistics import median

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryKind, Payee, Transaction
from app.reports import is_cash_flow


class Cadence(enum.StrEnum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass(frozen=True)
class Rule:
    cadence: Cadence
    shortest: int  # days between charges that still count as this cadence
    longest: int
    per_year: int  # charges in a year, to turn one charge into a monthly cost
    min_charges: int  # how many charges before we believe it's a pattern


# Bands are wide enough for "the 1st, but it posted on the 3rd" and short/long months.
RULES = [
    Rule(Cadence.WEEKLY, 5, 9, 52, 4),
    Rule(Cadence.BIWEEKLY, 12, 16, 26, 3),
    Rule(Cadence.MONTHLY, 26, 35, 12, 3),
    Rule(Cadence.QUARTERLY, 84, 98, 4, 3),
    Rule(Cadence.YEARLY, 350, 380, 1, 2),
]

RECENT = 7  # judge a payee on its last 7 charges, so an old, different habit doesn't count
STEADY_SHARE = 2 / 3  # at least this share of gaps (and of amounts) must fit the pattern
AMOUNT_RANGE = 0.4  # "steady" amount: within 40% of the typical one (utility bills move around)
SAME_AMOUNT = 0.05  # within 5%: shown as a fixed amount, otherwise "about"


@dataclass(frozen=True)
class Charge:
    """One payment, as a POSITIVE number of cents."""

    date: dt.date
    amount_cents: int
    payee_id: int
    payee_name: str
    category_id: int | None
    account_id: int


@dataclass(frozen=True)
class Series:
    payee_id: int
    payee_name: str
    # Set when only this payee's charges of exactly this amount repeat: rent by Zelle,
    # among all your other Zelle payments. None when everything to the payee repeats.
    # (payee_id, matched_amount_cents) names a series, for ignoring it.
    matched_amount_cents: int | None
    category_id: int | None  # from the latest charge
    account_id: int  # from the latest charge
    cadence: Cadence
    amount_cents: int  # the typical charge (median of recent ones)
    amount_varies: bool  # True for bills like gas or water: amount_cents is an estimate
    monthly_cents: int  # what it costs per month on average
    charges: int  # how many charges the pattern is based on
    last_date: dt.date
    next_date: dt.date  # can be a few days in the past: due, not posted yet


def add_months(day: dt.date, months: int) -> dt.date:
    """Same day of the month, `months` later. Jan 31 + 1 month = Feb 28 (or 29)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def next_charge(last: dt.date, cadence: Cadence) -> dt.date:
    match cadence:
        case Cadence.WEEKLY:
            return last + dt.timedelta(days=7)
        case Cadence.BIWEEKLY:
            return last + dt.timedelta(days=14)
        case Cadence.MONTHLY:
            return add_months(last, 1)
        case Cadence.QUARTERLY:
            return add_months(last, 3)
        case Cadence.YEARLY:
            return add_months(last, 12)


def share(flags: list[bool]) -> float:
    return sum(flags) / len(flags)


def detect_series(charges: list[Charge], today: dt.date) -> list[Series]:
    """Every payee that looks recurring, soonest next charge first."""
    by_payee: dict[int, list[Charge]] = {}
    for charge in sorted(charges, key=lambda c: c.date):
        by_payee.setdefault(charge.payee_id, []).append(charge)

    found = []
    for group in by_payee.values():
        if whole := series_of(group, today):
            found.append(whole)
            continue
        # Second try: the payee as a whole is irregular, but one exact amount may repeat.
        by_amount: dict[int, list[Charge]] = {}
        for charge in group:
            by_amount.setdefault(charge.amount_cents, []).append(charge)
        found += [s for amount, same in by_amount.items() if (s := series_of(same, today, amount))]
    return sorted(found, key=lambda s: (s.next_date, s.payee_name.lower()))


def series_of(charges: list[Charge], today: dt.date, matched_amount: int | None = None) -> Series | None:
    """One payee's charges (oldest first) -> its Series, or None if they aren't a pattern."""
    # Two payments to one payee on one day (rent paid in two parts) count as one charge.
    days: dict[dt.date, int] = {}
    for c in charges:
        days[c.date] = days.get(c.date, 0) + c.amount_cents
    recent = sorted(days.items())[-RECENT:]
    if len(recent) < 2:
        return None

    dates = [d for d, _ in recent]
    amounts = [a for _, a in recent]
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]

    # The typical gap picks the cadence. Then most gaps (not just the median) must fit it,
    # which rules out "twice in one week, then nothing for two months".
    rule = next((r for r in RULES if r.shortest <= median(gaps) <= r.longest), None)
    if rule is None or len(recent) < rule.min_charges:
        return None
    if share([rule.shortest <= g <= rule.longest for g in gaps]) < STEADY_SHARE:
        return None

    # Steady amounts too: a weekly grocery run is regular, but it isn't a bill.
    typical = round(median(amounts))
    if share([abs(a - typical) <= typical * AMOUNT_RANGE for a in amounts]) < STEADY_SHARE:
        return None

    # A missed charge, well past when it was due, means it stopped (a cancelled subscription).
    last = dates[-1]
    upcoming = next_charge(last, rule.cadence)
    if today > upcoming + dt.timedelta(days=rule.longest - rule.shortest):
        return None

    latest = charges[-1]
    return Series(
        payee_id=latest.payee_id,
        payee_name=latest.payee_name,
        matched_amount_cents=matched_amount,
        category_id=latest.category_id,
        account_id=latest.account_id,
        cadence=rule.cadence,
        amount_cents=typical,
        amount_varies=any(abs(a - typical) > typical * SAME_AMOUNT for a in amounts),
        monthly_cents=round(typical * rule.per_year / 12),
        charges=len(recent),
        last_date=last,
        next_date=upcoming,
    )


def upcoming(series: list[Series], start: dt.date, end: dt.date) -> list[tuple[dt.date, Series]]:
    """Every expected charge from start to end (inclusive), soonest first.

    A weekly series can land more than once. A charge that was due before `start` but
    hasn't posted yet shows on `start`, so a late bill doesn't vanish from the list.
    """
    found = []
    for s in series:
        day = s.next_date
        if day < start:
            found.append((start, s))
            day = next_charge(day, s.cadence)
        while day <= end:
            found.append((day, s))
            day = next_charge(day, s.cadence)
    return sorted(found, key=lambda item: (item[0], item[1].payee_name.lower()))


def load_charges(db: Session) -> list[Charge]:
    """Spending with a payee: money out, not a transfer or adjustment, not an income category."""
    rows = db.execute(
        select(
            Transaction.date,
            Transaction.amount_cents,
            Transaction.payee_id,
            Payee.name,
            Transaction.category_id,
            Transaction.account_id,
        )
        .join(Payee, Transaction.payee_id == Payee.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            is_cash_flow(),
            Transaction.amount_cents < 0,
            or_(Category.kind == CategoryKind.EXPENSE, Category.kind.is_(None)),
        )
    )
    return [Charge(day, -cents, payee_id, name, category_id, account_id)
            for day, cents, payee_id, name, category_id, account_id in rows]
