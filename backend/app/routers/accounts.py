"""Account endpoints: /api/accounts"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.balances import get_balances
from app.clock import Today
from app.db import get_db
from app.models import Account, Transaction
from app.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    AccountWithBalance,
    ReconcileRequest,
    ReconcileResult,
)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# "Give me a database session" as a reusable type. FastAPI calls get_db() for us.
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AccountWithBalance])
def list_accounts(db: DbSession, as_of: dt.date | None = None):
    """Every account with its balance. ?as_of=2026-10-31 gives balances at the end of that day."""
    # Open accounts first (closed_at IS NULL sorts first), then alphabetical.
    query = select(Account).order_by(Account.closed_at.is_not(None), Account.name)
    accounts = db.scalars(query).all()
    balances = get_balances(db, as_of)
    return [
        AccountWithBalance(
            **AccountRead.model_validate(account).model_dump(),
            balance_cents=balances.get(account.id, 0),  # no transactions yet = 0
        )
        for account in accounts
    ]


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: DbSession):
    account = Account(name=payload.name, type=payload.type)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"An open account named '{payload.name}' already exists.")
    return account


@router.patch("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, payload: AccountUpdate, db: DbSession):
    """Change an account's name and/or type. Transactions point at the account by id,
    so they follow automatically, and balances don't change: they're sums of transactions."""
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} does not exist.")

    for field, value in payload.model_dump(exclude_unset=True).items():  # only what was sent
        setattr(account, field, value)
    try:
        # The partial unique index (open accounts only) decides what's a duplicate. Asking the
        # database, instead of checking first in Python, can't be fooled by two requests at once.
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"An open account named '{payload.name}' already exists.")
    return account


def dollars(cents: int) -> str:
    """-25000 -> "-$250.00", for error messages. Integer math, so no float rounding."""
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"


def get_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} does not exist.")
    return account


@router.post("/{account_id}/reconcile", response_model=ReconcileResult)
def reconcile_account(account_id: int, payload: ReconcileRequest, db: DbSession):
    """Make the balance at the end of `date` match a statement, by adding an adjustment entry.

    History is never rewritten: the difference becomes one new transaction on that date,
    marked is_adjustment so it doesn't count as income or spending.
    """
    account = get_account(db, account_id)
    if account.closed_at is not None:
        raise HTTPException(status_code=409, detail=f"{account.name} is closed. Reopen it to reconcile.")

    previous = get_balances(db, payload.date).get(account.id, 0)
    difference = payload.balance_cents - previous
    if difference == 0:
        return ReconcileResult(previous_balance_cents=previous, balance_cents=previous, adjustment=None)

    adjustment = Transaction(
        account_id=account.id,
        date=payload.date,
        amount_cents=difference,
        notes="Balance adjustment",
        is_adjustment=True,
    )
    db.add(adjustment)
    db.commit()
    return ReconcileResult(previous_balance_cents=previous, balance_cents=payload.balance_cents, adjustment=adjustment)


@router.post("/{account_id}/close", response_model=AccountRead)
def close_account(account_id: int, db: DbSession, today: Today):
    """Close an account you no longer use. Its history stays, and it still counts in past reports.

    The balance must be zero first: a closed account with money in it would quietly keep
    counting toward net worth while being hidden from the lists.
    """
    account = get_account(db, account_id)
    if account.closed_at is not None:
        return account  # already closed: closing again changes nothing
    balance = get_balances(db).get(account.id, 0)
    if balance != 0:
        raise HTTPException(
            status_code=409,
            detail=f"{account.name} still has a balance of {dollars(balance)}. "
                   "Move the money out with a transfer, or reconcile it to 0, before closing.",
        )
    account.closed_at = dt.datetime.combine(today, dt.time())
    db.commit()
    return account


@router.post("/{account_id}/reopen", response_model=AccountRead)
def reopen_account(account_id: int, db: DbSession):
    account = get_account(db, account_id)
    account.closed_at = None
    try:
        db.commit()
    except IntegrityError:
        # The partial unique index: an open account already uses this name.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"An open account named '{account.name}' already exists. Rename one of them first.",
        )
    return account
