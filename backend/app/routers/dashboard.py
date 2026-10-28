"""Dashboard endpoints: /api/dashboard"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.reports import cash_flow, income_and_spending, net_worth
from app.schemas import CashFlowMonth, DashboardSummary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/summary", response_model=DashboardSummary)
def summary(db: DbSession, start: dt.date, end: dt.date):
    """The four top cards: ?start=2026-10-01&end=2026-10-31 (inclusive)."""
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end.")

    income, spending = income_and_spending(db, start, end)
    return DashboardSummary(
        start=start,
        end=end,
        net_worth_cents=net_worth(db, as_of=end),
        income_cents=income,
        spending_cents=spending,
        saved_cents=income - spending,
    )


@router.get("/cash-flow", response_model=list[CashFlowMonth])
def cash_flow_by_month(
    db: DbSession,
    end: dt.date | None = None,
    months: Annotated[int, Query(ge=1, le=120)] = 12,
):
    """Income vs spending per month, oldest first: ?end=2026-10-31&months=12. end defaults to today."""
    return cash_flow(db, end or dt.date.today(), months)
