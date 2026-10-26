"""Transaction endpoints: /api/transactions (income and expenses; transfers come later)."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Account, Category, CategoryKind, Payee, Transaction
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
        # Many-to-one (each transaction has at most one payee): a JOIN fetches it in the same query.
        .options(joinedload(Transaction.payee))
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
    account = db.get(Account, payload.account_id)
    if account is None:
        raise HTTPException(status_code=422, detail=f"Account {payload.account_id} does not exist.")
    if account.closed_at is not None:
        raise HTTPException(status_code=422, detail=f"{account.name} is closed, so it can't get new transactions.")

    if payload.category_id is None:
        return
    category = db.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(status_code=422, detail=f"Category {payload.category_id} does not exist.")
    if category.kind == CategoryKind.TRANSFER:
        raise HTTPException(status_code=422, detail="Use the transfer endpoint for transfers between accounts.")


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
