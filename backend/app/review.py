"""Year in Review: one year's story, derived from data the app already has. Nothing is stored.

Every number reuses an existing rule, so it agrees with the rest of the app:
income/spending/saved (app/reports.py), invested (transfers into investment accounts),
net worth (accounts in net worth), investment values (cash + holdings), budgets (app/budgets.py)
and the S&P 500 (SPY closes + dividends, app/benchmark.py).
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balances import get_account_values
from app.benchmark import benchmark_days
from app.budgets import month_budgets
from app.models import Account, AccountType, Category, CategoryKind, Payee, Transaction
from app.reports import (
    cash_flow,
    income_and_spending,
    is_cash_flow,
    moved_to_savings,
    net_worth,
    roll_up,
    spending_cents,
    spending_per_category,
)

TOP_CATEGORIES = 8
TOP_PAYEES = 5


@dataclass
class Totals:
    income_cents: int
    spending_cents: int
    saved_cents: int
    invested_cents: int


@dataclass
class TopItem:
    id: int | None
    name: str
    cents: int
    previous_cents: int  # the same thing the year before
    count: int = 0  # transactions (payees only)


@dataclass
class Review:
    year: int
    start: dt.date
    end: dt.date  # Dec 31, or today for the current year
    partial: bool  # the year isn't over yet
    totals: Totals
    previous: Totals | None  # the year before, over the same stretch of days; None before your data starts
    months: list[dict]  # {month, income_cents, spending_cents, saved_cents}, Jan to the end month
    top_categories: list[TopItem]
    top_payees: list[TopItem]
    transactions: int
    net_worth_start_cents: int  # end of the day before the year began
    net_worth_end_cents: int
    investments_start_cents: int  # all Brokerage and Retirement accounts
    investments_end_cents: int
    sp500_return_bp: int | None  # SPY with dividends reinvested, over the year so far; None without prices
    budget_months_on_track: int  # (category, month) pairs at or under budget
    budget_months_total: int
    years: list[int] = field(default_factory=list)  # every year you have data for


def totals(db: Session, start: dt.date, end: dt.date) -> Totals:
    income, spending = income_and_spending(db, start, end)
    return Totals(income, spending, income - spending, moved_to_savings(db, start, end))


def top_categories(db: Session, start: dt.date, end: dt.date, before: tuple[dt.date, dt.date]) -> list[TopItem]:
    categories = db.scalars(select(Category).where(Category.kind == CategoryKind.EXPENSE)).all()
    parent_of = {c.id: c.parent_id for c in categories}
    names = {c.id: c.name for c in categories}
    now = roll_up(spending_per_category(db, start, end), parent_of)
    then = roll_up(spending_per_category(db, *before), parent_of)
    items = [TopItem(cid, names.get(cid, "Uncategorized") if cid is not None else "Uncategorized", cents, then.get(cid, 0))
             for cid, cents in now.items() if cents > 0]
    return sorted(items, key=lambda i: -i.cents)[:TOP_CATEGORIES]


def top_payees(db: Session, start: dt.date, end: dt.date, before: tuple[dt.date, dt.date]) -> list[TopItem]:
    def spending_by_payee(a: dt.date, b: dt.date) -> dict[int, tuple[str, int, int]]:
        rows = db.execute(
            select(Payee.id, Payee.name, func.sum(spending_cents()), func.count(Transaction.id))
            .select_from(Transaction)
            .join(Payee, Transaction.payee_id == Payee.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(is_cash_flow(), Transaction.date >= a, Transaction.date <= b)
            .group_by(Payee.id, Payee.name)
        )
        return {pid: (name, cents or 0, count) for pid, name, cents, count in rows}

    now = spending_by_payee(start, end)
    then = spending_by_payee(*before)
    items = [TopItem(pid, name, cents, then.get(pid, ("", 0, 0))[1], count)
             for pid, (name, cents, count) in now.items() if cents > 0]
    return sorted(items, key=lambda i: -i.cents)[:TOP_PAYEES]


def investment_value(db: Session, as_of: dt.date) -> int:
    ids = set(db.scalars(select(Account.id).where(Account.type.in_((AccountType.BROKERAGE, AccountType.RETIREMENT)))))
    return sum(cents for account_id, cents in get_account_values(db, as_of).items() if account_id in ids)


def sp500_return_bp(db: Session, start: dt.date, end: dt.date) -> int | None:
    """SPY total return from the last close before `start` to the last close on or before `end`."""
    days = benchmark_days(db)
    before = [d for d in days if d.date < start]
    during = [d for d in days if start <= d.date <= end]
    if not before or not during:
        return None
    shares = Decimal(1)
    for day in during:
        if day.dividend:
            shares += shares * day.dividend / day.close
    growth = shares * during[-1].close / before[-1].close - 1
    return int((growth * 10000).to_integral_value())


def budget_track_record(db: Session, start: dt.date, end: dt.date, today: dt.date) -> tuple[int, int]:
    """How many (budgeted category, finished month) pairs ended at or under budget. Months still
    in progress don't count yet."""
    on_track = total = 0
    month = start
    while month <= end:
        next_month = dt.date(month.year + (month.month == 12), month.month % 12 + 1, 1)
        if next_month - dt.timedelta(days=1) < today:  # the month is over
            view = month_budgets(db, month, today)
            for row in view.rows:
                if row.budget_cents is not None:
                    total += 1
                    on_track += row.spent_cents <= row.budget_cents
        month = next_month
    return on_track, total


def year_in_review(db: Session, year: int, today: dt.date) -> Review:
    start = dt.date(year, 1, 1)
    end = min(dt.date(year, 12, 31), today)
    partial = end < dt.date(year, 12, 31)
    # The year before, over the same days, so a year in progress compares like with like.
    previous_start = dt.date(year - 1, 1, 1)
    previous_end = end.replace(year=year - 1) if not (end.month == 2 and end.day == 29) else dt.date(year - 1, 2, 28)
    first_date = db.scalar(select(func.min(Transaction.date)))
    has_previous = first_date is not None and first_date <= previous_end

    months_count = end.month
    months = cash_flow(db, end, months_count)
    count = db.scalar(select(func.count(Transaction.id)).where(
        is_cash_flow(), Transaction.date >= start, Transaction.date <= end))
    on_track, budget_total = budget_track_record(db, start, end, today)
    first_year = first_date.year if first_date else today.year

    return Review(
        year=year,
        start=start,
        end=end,
        partial=partial,
        totals=totals(db, start, end),
        previous=totals(db, previous_start, previous_end) if has_previous else None,
        months=months,
        top_categories=top_categories(db, start, end, (previous_start, previous_end)),
        top_payees=top_payees(db, start, end, (previous_start, previous_end)),
        transactions=count,
        net_worth_start_cents=net_worth(db, start - dt.timedelta(days=1)),
        net_worth_end_cents=net_worth(db, end),
        investments_start_cents=investment_value(db, start - dt.timedelta(days=1)),
        investments_end_cents=investment_value(db, end),
        sp500_return_bp=sp500_return_bp(db, start, end),
        budget_months_on_track=on_track,
        budget_months_total=budget_total,
        years=list(range(first_year, today.year + 1)),
    )
