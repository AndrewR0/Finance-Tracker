"""Budgets for one month: what applies, what was spent, and suggestions. Derived, never stored
beyond the budget amounts themselves.

Spending uses the dashboard's rules (app/reports.py): refunds lower it; transfers, balance
adjustments and "counts as saving" categories don't count. A parent category's budget covers
all of its subcategories; a subcategory can have its own budget as well (shown under the parent).
"""

import calendar
import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Category, CategoryKind
from app.reports import roll_up, spending_per_category

SUGGESTION_MONTHS = 6


def first_of_month(day: dt.date) -> dt.date:
    return day.replace(day=1)


def last_of_month(month: dt.date) -> dt.date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def add_months(month: dt.date, n: int) -> dt.date:
    index = month.year * 12 + month.month - 1 + n
    return dt.date(index // 12, index % 12 + 1, 1)


def budgets_for(db: Session, month: dt.date) -> dict[int, int]:
    """{category_id: amount_cents} in effect for `month` (the newest row on or before it)."""
    rows = db.scalars(select(Budget).where(Budget.start_month <= month).order_by(Budget.start_month)).all()
    current: dict[int, int] = {}
    for row in rows:  # oldest first, so the newest row for each category wins
        current[row.category_id] = row.amount_cents
    return {category_id: cents for category_id, cents in current.items() if cents > 0}


@dataclass
class Row:
    category_id: int
    name: str
    parent_id: int | None
    budget_cents: int | None  # None: no budget this month
    spent_cents: int  # a parent's includes its subcategories
    suggested_cents: int  # average monthly spending over the previous SUGGESTION_MONTHS months


@dataclass
class MonthBudgets:
    month: dt.date
    days_in_month: int
    days_elapsed: int  # for the pace marker: all of a past month, today's day for this month, 0 ahead
    rows: list[Row]  # every expense category that can have a budget, parents before their subcategories
    budgeted_cents: int  # total of the budgets this month
    spent_budgeted_cents: int  # spending those budgets cover
    unbudgeted_cents: int  # spending no budget covers
    total_spent_cents: int


def month_budgets(db: Session, month: dt.date, today: dt.date) -> MonthBudgets:
    start, end = month, last_of_month(month)
    days = end.day
    if end < today:
        elapsed = days
    elif start > today:
        elapsed = 0
    else:
        elapsed = today.day

    categories = db.scalars(
        select(Category).where(Category.kind == CategoryKind.EXPENSE, Category.counts_as_saving.is_(False))
        .order_by(Category.name)
    ).all()
    parent_of = {c.id: c.parent_id for c in categories}
    flat = spending_per_category(db, start, end)  # straight from transactions (None = uncategorized)
    rolled = roll_up(flat, parent_of)
    history_start = add_months(month, -SUGGESTION_MONTHS)
    history = spending_per_category(db, history_start, start - dt.timedelta(days=1))
    history_rolled = roll_up(history, parent_of)
    budgets = budgets_for(db, month)

    rows: list[Row] = []
    tops = [c for c in categories if c.parent_id is None]
    subs_of = {c.id: [s for s in categories if s.parent_id == c.id] for c in tops}

    def row(c: Category, spent: dict, past: dict) -> Row:
        return Row(c.id, c.name, c.parent_id, budgets.get(c.id), spent.get(c.id, 0),
                   max(0, round(past.get(c.id, 0) / SUGGESTION_MONTHS)))

    for top in tops:
        rows.append(row(top, rolled, history_rolled))
        rows.extend(row(sub, flat, history) for sub in subs_of[top.id])

    # What the budgets cover: a budgeted parent covers its whole family; otherwise each budgeted
    # subcategory covers itself. Spending is counted once even if a parent and a child both have one.
    covered_spent = 0
    for top in tops:
        if top.id in budgets:
            covered_spent += rolled.get(top.id, 0)
        else:
            covered_spent += sum(flat.get(s.id, 0) for s in subs_of[top.id] if s.id in budgets)
    total = sum(v for v in flat.values())
    return MonthBudgets(
        month=month,
        days_in_month=days,
        days_elapsed=elapsed,
        rows=rows,
        budgeted_cents=sum(cents for cid, cents in budgets.items() if cid in parent_of
                           and (parent_of[cid] is None or parent_of[cid] not in budgets)),
        spent_budgeted_cents=covered_spent,
        unbudgeted_cents=total - covered_spent,
        total_spent_cents=total,
    )
