"""Dashboard endpoints: /api/dashboard"""

import datetime as dt
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import Today
from app.db import get_db
from app.models import Transaction
from app.periods import Period, PeriodKind, bounds, resolve_period
from app.reports import (
    cash_flow,
    change,
    income_and_spending,
    net_worth,
    spending_by_category,
    spending_pace,
)
from app.schemas import CashFlowMonth, CategorySpending, DashboardSummary, PeriodRead, SpendingPace

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/period", response_model=PeriodRead)
def period(db: DbSession, today: Today, kind: PeriodKind, date: dt.date | None = None):
    """Date ranges for ?kind=month&date=2026-10-23 (date defaults to today).

    The ‹ and › buttons send previous_date / next_date back as ?date=.
    """
    if kind == PeriodKind.ALL:
        first_day = db.scalar(select(func.min(Transaction.date)))
        p = resolve_period(kind, today, today, first_day)
        return PeriodRead(**vars(p), previous_date=None, next_date=None)

    p = resolve_or_422(kind, date or today, today)
    _, last = bounds(kind, p.start)
    day_after = last + dt.timedelta(days=1)
    return PeriodRead(
        **vars(p),
        previous_date=p.compare_start,  # the previous period starts where the compare range starts
        next_date=day_after if day_after <= today else None,
    )


@router.get("/spending-pace", response_model=SpendingPace)
def spending_pace_report(db: DbSession, today: Today, kind: PeriodKind, date: dt.date | None = None):
    """Running spending this period vs last: ?kind=month or ?kind=year (date defaults to today)."""
    if kind == PeriodKind.ALL:
        raise HTTPException(status_code=422, detail="All time has no earlier period to compare. Pick month or year.")
    return spending_pace(db, resolve_or_422(kind, date or today, today))


def resolve_or_422(kind: PeriodKind, anchor: dt.date, today: dt.date) -> Period:
    """resolve_period, but a bad period becomes a 422 response instead of a crash."""
    try:
        return resolve_period(kind, anchor, today)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@dataclass(frozen=True)
class Ranges:
    start: dt.date
    end: dt.date
    compare: tuple[dt.date, dt.date] | None


def date_ranges(
    start: dt.date,
    end: dt.date,
    compare_start: dt.date | None = None,
    compare_end: dt.date | None = None,
) -> Ranges:
    """Shared query parameters: ?start&end, plus an optional compare_start&compare_end.

    Endpoints ask for `ranges: DateRanges`. FastAPI reads these four parameters from the URL,
    runs the checks below, and hands the endpoint a Ranges, or answers 422 before it runs.
    """
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end.")
    if (compare_start is None) != (compare_end is None):
        raise HTTPException(status_code=422, detail="Give both compare_start and compare_end, or neither.")
    if compare_start is not None and compare_start > compare_end:
        raise HTTPException(status_code=422, detail="compare_start must be on or before compare_end.")
    compare = (compare_start, compare_end) if compare_start is not None else None
    return Ranges(start, end, compare)


DateRanges = Annotated[Ranges, Depends(date_ranges)]


@router.get("/summary", response_model=DashboardSummary)
def summary(db: DbSession, ranges: DateRanges):
    """The four top cards: ?start=2026-10-01&end=2026-10-31 (inclusive).

    Add compare_start and compare_end to fill in the *_change fields.
    """
    income, spending = income_and_spending(db, ranges.start, ranges.end)
    worth = net_worth(db, as_of=ranges.end)
    worth_before = net_worth(db, as_of=ranges.start - dt.timedelta(days=1))

    changes = {"income_change": None, "spending_change": None, "saved_change": None}
    if ranges.compare:
        income_then, spending_then = income_and_spending(db, *ranges.compare)
        changes = {
            "income_change": change(income, income_then),
            "spending_change": change(spending, spending_then),
            "saved_change": change(income - spending, income_then - spending_then),
        }

    return DashboardSummary(
        start=ranges.start,
        end=ranges.end,
        net_worth_cents=worth,
        net_worth_change_cents=worth - worth_before,
        income_cents=income,
        spending_cents=spending,
        saved_cents=income - spending,
        **changes,
    )


@router.get("/cash-flow", response_model=list[CashFlowMonth])
def cash_flow_by_month(
    db: DbSession,
    end: dt.date | None = None,
    months: Annotated[int, Query(ge=1, le=120)] = 12,
):
    """Income vs spending per month, oldest first: ?end=2026-10-31&months=12. end defaults to today."""
    return cash_flow(db, end or dt.date.today(), months)


@router.get("/spending-by-category", response_model=list[CategorySpending])
def spending_by_category_report(db: DbSession, ranges: DateRanges):
    """Spending per category, biggest first. Add compare_start and compare_end to get previous_cents."""
    return spending_by_category(db, ranges.start, ranges.end, ranges.compare)
