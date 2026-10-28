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


def spending_per_category(db: Session, start: dt.date, end: dt.date) -> dict[int | None, int]:
    """{category_id: spending_cents} straight from the transactions, not rolled up.

    None is the key for uncategorized spending. Categories with no rows are missing.
    """
    query = (
        select(Transaction.category_id, func.sum(spending_cents()))
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.transfer_id.is_(None),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(Transaction.category_id)
    )
    return {category_id: total for category_id, total in db.execute(query)}


def roll_up(totals: dict[int | None, int], parent_of: dict[int, int | None]) -> dict[int | None, int]:
    """Add each subcategory's total into its top-level category.

    totals:    {category_id: cents}, flat, as from spending_per_category().
               The None key (uncategorized) may be present.
    parent_of: {category_id: parent_id}; parent_id is None for top-level categories.
    Returns:   {top_level_category_id: cents}, plus the None key if it was in totals.

    roll_up({1: 500, 5: 300, 6: 200, None: 40}, {1: None, 5: 1, 6: 1})
        -> {1: 1000, None: 40}
    """
    # TODO(human): combine the flat totals into one total per top-level category.
    #   For each (category_id, cents) in totals:
    #     - which top-level category does it belong to? A subcategory -> its parent.
    #       A top-level category -> itself. None (uncategorized) -> None.
    #     - add cents to that top-level category's running total.
    #   Edge cases (each has a test):
    #     - Food has direct transactions AND subcategory transactions: both count.
    #     - Only a subcategory has spending: the parent still appears in the result.
    #     - None isn't a key in parent_of. Looking it up there would fail.
    #   Hint: a plain dict with result[key] = result.get(key, 0) + cents works.
    #     (collections.defaultdict(int) is the shortcut, if you want to look it up.)
    result = {}
    for category_id, cents in totals.items():
        parent = parent_of.get(category_id)
        top = category_id if parent is None else parent
        result[top] = result.get(top, 0) + cents
    return result


def spending_by_category(
    db: Session,
    start: dt.date,
    end: dt.date,
    compare: tuple[dt.date, dt.date] | None = None,
) -> list[dict]:
    """Spending per top-level expense category, with subcategories nested, biggest first.

    compare: an optional (start, end) to fill in previous_cents for each row.
    """
    categories = db.scalars(select(Category)).all()
    parent_of = {c.id: c.parent_id for c in categories}

    now = spending_per_category(db, start, end)
    before = spending_per_category(db, *compare) if compare else None
    now_rolled = roll_up(now, parent_of)
    before_rolled = roll_up(before, parent_of) if before is not None else None

    def row(category_id: int | None, name: str, flat_now: dict, flat_before: dict | None) -> dict:
        return {
            "category_id": category_id,
            "name": name,
            "spending_cents": flat_now.get(category_id, 0),
            "previous_cents": None if flat_before is None else flat_before.get(category_id, 0),
        }

    def has_spending(r: dict) -> bool:
        return r["spending_cents"] != 0 or (r["previous_cents"] or 0) != 0

    rows = []
    for top in (c for c in categories if c.parent_id is None and c.kind == CategoryKind.EXPENSE):
        parent_row = row(top.id, top.name, now_rolled, before_rolled)
        subs = [row(s.id, s.name, now, before) for s in top.subcategories]
        parent_row["subcategories"] = sorted(
            (s for s in subs if has_spending(s)), key=lambda s: (-s["spending_cents"], s["name"])
        )
        rows.append(parent_row)

    uncategorized = row(None, "Uncategorized", now_rolled, before_rolled)
    uncategorized["subcategories"] = []
    rows.append(uncategorized)

    return sorted((r for r in rows if has_spending(r)), key=lambda r: (-r["spending_cents"], r["name"]))


def net_worth(db: Session, as_of: dt.date) -> int:
    """Everything you have minus everything you owe, at the end of as_of."""
    return sum(get_balances(db, as_of).values())
