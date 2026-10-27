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


def net_worth(db: Session, as_of: dt.date) -> int:
    """Everything you have minus everything you owe, at the end of as_of."""
    return sum(get_balances(db, as_of).values())
