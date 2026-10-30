"""Account endpoints: /api/accounts"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.balances import get_balances
from app.db import get_db
from app.models import Account
from app.schemas import AccountCreate, AccountRead, AccountUpdate, AccountWithBalance

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
