"""Dashboard numbers: income, spending, saved, net worth.

The rules for what counts as income or spending live in income_cents() and
spending_cents(), so every report (summary, cash flow, by category) agrees.
"""

import datetime as dt

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.balances import get_balances
from app.models import Category, CategoryKind, Transaction


def income_cents():
    """SQL expression: how much this transaction adds to income (0 if none).

    Only valid in a query that LEFT OUTER JOINs Category, so Category.kind is
    NULL for uncategorized transactions. Transfers are filtered out by the caller.
    """
    return case(
        (Category.kind == CategoryKind.INCOME, Transaction.amount_cents),
        (Category.kind.is_(None) & (Transaction.amount_cents > 0), Transaction.amount_cents),
        else_=0,
    )


def spending_cents():
    """SQL expression: how much this transaction adds to spending, as a POSITIVE number (0 if none)."""
    return case(
        (Category.kind == CategoryKind.EXPENSE, -Transaction.amount_cents),
        (Category.kind.is_(None) & (Transaction.amount_cents < 0), -Transaction.amount_cents),
        else_=0,
    )


def income_and_spending(db: Session, start: dt.date, end: dt.date) -> tuple[int, int]:
    """Total (income_cents, spending_cents) for transactions from start to end, inclusive."""
    query = (
        select(
            # SUM of no rows is NULL in SQL, not 0. COALESCE swaps NULL for 0.
            func.coalesce(func.sum(income_cents()), 0),
            func.coalesce(func.sum(spending_cents()), 0),
        )
        .select_from(Transaction)
        # OUTER join: keep uncategorized transactions (their Category columns are NULL).
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.transfer_id.is_(None),  # transfers are neither income nor spending
            Transaction.date >= start,
            Transaction.date <= end,
        )
    )
    income, spending = db.execute(query).one()
    return income, spending


def last_n_months(end: dt.date, n: int) -> list[str]:
    """The n months up to and including end's month, oldest first, as "YYYY-MM".

    last_n_months(date(2026, 10, 31), 3) -> ["2026-08", "2026-09", "2026-10"]
    """
    year = end.year
    month = end.month
    months = []
    for _ in range(n):
        months.append(f"{year}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year -1, 12

    return months[::-1]


def cash_flow(db: Session, end: dt.date, months: int) -> list[dict]:
    """Income, spending and saved for each of the `months` months ending at end's month.

    Every month is present, oldest first, even with no transactions (all zeros).
    """
    labels = last_n_months(end, months)
    start = dt.date.fromisoformat(labels[0] + "-01")  # first day of the oldest month

    # SQLite stores dates as "2026-10-22" text; strftime cuts that down to "2026-10".
    month = func.strftime("%Y-%m", Transaction.date)
    query = (
        select(month, func.sum(income_cents()), func.sum(spending_cents()))
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.transfer_id.is_(None),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(month)
    )
    # {"2026-10": (income, spending)}, only for months that have transactions.
    totals = {label: (income, spending) for label, income, spending in db.execute(query)}

    rows = []
    for label in labels:
        income, spending = totals.get(label, (0, 0))  # a quiet month is zeros, not missing
        rows.append({"month": label, "income_cents": income, "spending_cents": spending,
                     "saved_cents": income - spending})
    return rows


def net_worth(db: Session, as_of: dt.date) -> int:
    """Everything you have minus everything you owe, at the end of as_of."""
    return sum(get_balances(db, as_of).values())
