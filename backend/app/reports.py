"""Dashboard numbers: income, spending, saved, net worth.

The rules for what counts as income or spending live in income_cents() and
spending_cents(), so every report (summary, cash flow, by category) agrees.
"""

import calendar
import datetime as dt
from itertools import accumulate

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.balances import get_balances
from app.models import Category, CategoryKind, Transaction
from app.periods import Period, PeriodKind, bounds


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


# strftime format for one bucket: a day for a Month view, a month for a Year view.
BUCKET_FORMAT = {PeriodKind.MONTH: "%Y-%m-%d", PeriodKind.YEAR: "%Y-%m"}


def bucket_keys(kind: PeriodKind, start: dt.date, end: dt.date) -> list[str]:
    """Every bucket from start to end, in order, formatted like BUCKET_FORMAT.

    MONTH, Oct 1 to Oct 3 -> ["2026-10-01", "2026-10-02", "2026-10-03"]
    YEAR,  Jan 1 to Mar 9 -> ["2026-01", "2026-02", "2026-03"]
    """
    if kind == PeriodKind.MONTH:
        return [(start + dt.timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    return [f"{start.year}-{m:02d}" for m in range(start.month, end.month + 1)]


def spending_per_bucket(db: Session, kind: PeriodKind, start: dt.date, end: dt.date) -> dict[str, int]:
    """{bucket: spending_cents} for buckets that have transactions. Quiet buckets are missing."""
    bucket = func.strftime(BUCKET_FORMAT[kind], Transaction.date)
    query = (
        select(bucket, func.sum(spending_cents()))
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.transfer_id.is_(None),
            Transaction.date >= start,
            Transaction.date <= end,
        )
        .group_by(bucket)
    )
    return {key: total for key, total in db.execute(query)}


def running_totals(per_bucket: dict[str, int], keys: list[str]) -> list[int]:
    """Spending so far at the end of each bucket in keys: one number per key, same order.

    per_bucket: {bucket: cents spent IN that bucket}; buckets with no spending are missing.
    keys:       every bucket, in order (from bucket_keys).
    """
    return list(accumulate(per_bucket.get(key, 0) for key in keys))

def spending_pace(db: Session, period: Period) -> dict:
    """This period's running spending vs the whole previous period, for the pace chart.

    period must be MONTH or YEAR (ALL has nothing to compare with).
    """
    kind = period.kind
    _, last = bounds(kind, period.start)
    previous_start, previous_last = bounds(kind, period.compare_start)

    now = running_totals(spending_per_bucket(db, kind, period.start, period.end),
                         bucket_keys(kind, period.start, period.end))
    # The previous line is drawn in full, even past "the same point", so you can see where it ended up.
    before = running_totals(spending_per_bucket(db, kind, previous_start, previous_last),
                            bucket_keys(kind, previous_start, previous_last))

    # One x-axis point per day (or month). Oct has 31 days and Sep 30, so pad the shorter line with None.
    length = max(len(bucket_keys(kind, period.start, last)), len(before))
    points = [
        {
            "label": str(i + 1) if kind == PeriodKind.MONTH else calendar.month_abbr[i + 1],
            "current_cents": now[i] if i < len(now) else None,  # None = hasn't happened yet
            "previous_cents": before[i] if i < len(before) else None,
        }
        for i in range(length)
    ]

    spent = now[-1]
    # "On pace for": if every remaining day looks like the average day so far.
    elapsed_days = (period.end - period.start).days + 1
    total_days = (last - period.start).days + 1
    return {
        "kind": kind,
        "start": period.start,
        "end": period.end,
        "compare_start": period.compare_start,
        "compare_end": period.compare_end,
        "spent_cents": spent,
        # Exactly the compare range, so it matches /summary for the same dates.
        "previous_same_point_cents": income_and_spending(db, period.compare_start, period.compare_end)[1],
        "previous_total_cents": before[-1],
        "projected_cents": round(spent * total_days / elapsed_days),
        "points": points,
    }


def percent_change(now: int, before: int) -> float | None:
    """How much now differs from before, as a percent of before, rounded to 1 decimal place."""
    if before == 0:
        return None
    return round((now - before) / abs(before) * 100, 1)


def change(now: int, before: int) -> dict:
    """One "vs previous period" badge: previous value, difference, and percent."""
    return {"previous_cents": before, "change_cents": now - before, "change_percent": percent_change(now, before)}


def net_worth(db: Session, as_of: dt.date) -> int:
    """Everything you have minus everything you owe, at the end of as_of."""
    return sum(get_balances(db, as_of).values())
