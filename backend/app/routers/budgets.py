"""Budget endpoints: /api/budgets"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.budgets import first_of_month, month_budgets
from app.clock import Today
from app.db import get_db
from app.models import Budget, Category, CategoryKind
from app.schemas import BudgetSet, MonthBudgetsRead

router = APIRouter(prefix="/api/budgets", tags=["budgets"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=MonthBudgetsRead)
def get_month_budgets(db: DbSession, today: Today, month: dt.date | None = None):
    """Budgets vs spending for ?month=2026-11-01 (any day in it works; defaults to this month)."""
    return month_budgets(db, first_of_month(month or today), today)


@router.put("/{category_id}", response_model=MonthBudgetsRead)
def set_budget(category_id: int, payload: BudgetSet, db: DbSession, today: Today):
    """Set (or remove, with null) a category's budget from that month on. Earlier months keep theirs."""
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail=f"Category {category_id} does not exist.")
    if category.kind != CategoryKind.EXPENSE or category.counts_as_saving:
        raise HTTPException(status_code=422, detail=f"{category.name} isn't a spending category, so it can't have a budget.")
    month = first_of_month(payload.month)
    amount = payload.amount_cents or 0
    row = db.scalar(select(Budget).where(Budget.category_id == category.id, Budget.start_month == month))
    if row is None:
        db.add(Budget(category_id=category.id, start_month=month, amount_cents=amount))
    else:
        row.amount_cents = amount
    db.commit()
    return month_budgets(db, month, today)
