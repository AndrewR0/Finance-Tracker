"""Recurring spending endpoints: /api/recurring"""

import datetime as dt
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import Today
from app.db import get_db
from app.models import Payee, RecurringSeries
from app.recurring import Series, detect_series, load_charges, upcoming
from app.schemas import RecurringIgnore, RecurringRead, UpcomingCharge

router = APIRouter(prefix="/api/recurring", tags=["recurring"])

DbSession = Annotated[Session, Depends(get_db)]

SeriesKey = tuple[int, int | None]  # (payee_id, matched_amount_cents)


def key_of(s: Series) -> SeriesKey:
    return (s.payee_id, s.matched_amount_cents)


def ignored_keys(db: Session) -> set[SeriesKey]:
    rows = db.execute(
        select(RecurringSeries.payee_id, RecurringSeries.matched_amount_cents).where(RecurringSeries.ignored)
    )
    return {(payee_id, amount) for payee_id, amount in rows}


@router.get("", response_model=list[RecurringRead])
def list_recurring(db: DbSession, today: Today):
    """Every detected series, soonest next charge first. Ignored ones are included, marked."""
    ignored = ignored_keys(db)
    return [
        RecurringRead(**asdict(s), ignored=key_of(s) in ignored)
        for s in detect_series(load_charges(db), today)
    ]


@router.get("/upcoming", response_model=list[UpcomingCharge])
def upcoming_charges(db: DbSession, today: Today, days: Annotated[int, Query(ge=1, le=366)] = 14):
    """Expected charges from today through the next `days` days, leaving out ignored series."""
    ignored = ignored_keys(db)
    series = [s for s in detect_series(load_charges(db), today) if key_of(s) not in ignored]
    return [
        UpcomingCharge(
            date=day,
            payee_id=s.payee_id,
            payee_name=s.payee_name,
            category_id=s.category_id,
            cadence=s.cadence,
            amount_cents=s.amount_cents,
            amount_varies=s.amount_varies,
        )
        for day, s in upcoming(series, today, today + dt.timedelta(days=days - 1))
    ]


@router.put("/ignored", status_code=status.HTTP_204_NO_CONTENT)
def set_ignored(body: RecurringIgnore, db: DbSession):
    """Hide a series ({"ignored": true}) or bring it back ({"ignored": false})."""
    if db.get(Payee, body.payee_id) is None:
        raise HTTPException(status_code=404, detail="Payee not found")

    # Look up first: the unique constraint can't catch a duplicate NULL amount (see the model).
    row = db.scalar(
        select(RecurringSeries).where(
            RecurringSeries.payee_id == body.payee_id,
            # Plain == never matches NULL in SQL. IS NOT DISTINCT FROM treats NULL like a value.
            RecurringSeries.matched_amount_cents.is_not_distinct_from(body.matched_amount_cents),
        )
    )
    if row is None:
        row = RecurringSeries(payee_id=body.payee_id, matched_amount_cents=body.matched_amount_cents)
        db.add(row)
    row.ignored = body.ignored
    db.commit()
