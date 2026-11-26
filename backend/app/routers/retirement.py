"""Retirement estimator: /api/retirement

The server supplies the facts (your last 12 months, your balances) and stores your settings.
The projection itself runs in the browser (frontend/src/lib/retirement.ts), so changing a
number updates the chart instantly without a round trip.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balances import get_account_values
from app.clock import Today
from app.db import get_db
from app.models import Account, AccountType, RetirementSettings, Trade, TradeKind
from app.reports import income_and_spending, moved_to_savings
from app.schemas import RetirementAccount, RetirementInputs, RetirementSettingsIn, RetirementSettingsRead

router = APIRouter(prefix="/api/retirement", tags=["retirement"])

DbSession = Annotated[Session, Depends(get_db)]

SETTINGS_ID = 1  # the one and only row


def get_settings(db: Session) -> RetirementSettings:
    """The settings row, created with the defaults the first time it's asked for."""
    settings = db.get(RetirementSettings, SETTINGS_ID)
    if settings is None:
        settings = RetirementSettings(id=SETTINGS_ID)
        db.add(settings)
        db.flush()
    return settings


@router.get("", response_model=RetirementInputs)
def retirement_inputs(db: DbSession, today: Today):
    settings = get_settings(db)
    db.commit()
    start = today - dt.timedelta(days=364)  # 365 days, today included
    _, spending = income_and_spending(db, start, today)
    k401 = db.scalar(
        select(func.coalesce(func.sum(Trade.amount_cents), 0)).where(
            Trade.kind == TradeKind.CONTRIBUTION, Trade.date >= start, Trade.date <= today)
    )
    accounts = db.scalars(
        select(Account).where(Account.type.in_((AccountType.BROKERAGE, AccountType.RETIREMENT)),
                              Account.closed_at.is_(None)).order_by(Account.name)
    ).all()
    values = get_account_values(db)
    rows = [RetirementAccount(account_id=a.id, name=a.name, type=a.type, in_net_worth=a.in_net_worth,
                              value_cents=values.get(a.id, 0)) for a in accounts]
    return RetirementInputs(
        settings=RetirementSettingsRead.model_validate(settings),
        period_start=start,
        period_end=today,
        spending_12m_cents=spending,
        invested_12m_cents=moved_to_savings(db, start, today),
        k401_12m_cents=k401,
        balance_cents=sum(r.value_cents for r in rows),
        accounts=rows,
    )


@router.put("/settings", response_model=RetirementSettingsRead)
def save_settings(payload: RetirementSettingsIn, db: DbSession):
    """Replace all settings. Send null for an override to go back to what your data says."""
    settings = get_settings(db)
    for field, value in payload.model_dump().items():
        setattr(settings, field, value)
    db.commit()
    return settings
