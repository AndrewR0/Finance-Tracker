"""Transaction endpoints: /api/transactions (income and expenses; transfers live in transfers.py)."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.checks import check_category_kind, get_category, get_open_account
from app.db import get_db
from app.models import Payee, Transaction
from app.schemas import TransactionCreate, TransactionRead

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    db: DbSession,
    account_id: int | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
):
    """Newest first. Optional filters: ?account_id=1&start=2026-10-01&end=2026-10-31 (inclusive)."""
    query = (
        select(Transaction)
        # Many-to-one (each transaction has at most one payee and one transfer):
        # a JOIN fetches them in the same query, so there's no N+1.
        .options(joinedload(Transaction.payee), joinedload(Transaction.transfer))
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    if start is not None:
        query = query.where(Transaction.date >= start)
    if end is not None:
        query = query.where(Transaction.date <= end)
    return db.scalars(query).all()


def check_references(db: Session, payload: TransactionCreate) -> None:
    """Raise HTTPException(422) if the account or category can't be used."""
    get_open_account(db, payload.account_id)
    if payload.category_id is not None:
        check_category_kind(get_category(db, payload.category_id), transfer=False)


def get_or_create_payee(db: Session, name: str) -> Payee:
    """Return the Payee with this name, creating it if it's new."""
    query = select(Payee).where(Payee.name == name)
    
    payee = db.scalars(query).first()
    if payee is not None:
        return payee

    payee = Payee(name=name)
    db.add(payee)
    return payee


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, db: DbSession):
    check_references(db, payload)

    transaction = Transaction(
        account_id=payload.account_id,
        date=payload.date,
        amount_cents=payload.amount_cents,
        payee=get_or_create_payee(db, payload.payee) if payload.payee else None,
        category_id=payload.category_id,
        notes=payload.notes or None,  # treat "" as no notes
    )
    db.add(transaction)
    db.commit()
    return transaction
