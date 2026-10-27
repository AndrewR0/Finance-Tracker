"""Transaction endpoints: /api/transactions (income and expenses; transfers live in transfers.py)."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.checks import check_category_kind, get_category, get_open_account
from app.db import get_db
from app.models import Payee, Transaction
from app.schemas import TransactionCreate, TransactionRead, TransactionUpdate

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


def get_editable_transaction(db: Session, transaction_id: int) -> Transaction:
    """Load a transaction that can be edited here: 404 if missing, 409 if it's a transfer leg."""
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} does not exist.")
    if transaction.transfer_id is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This is part of transfer {transaction.transfer_id}. "
                   f"Change it with /api/transfers/{transaction.transfer_id} so both sides stay in sync.",
        )
    return transaction


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(transaction_id: int, payload: TransactionUpdate, db: DbSession):
    transaction = get_editable_transaction(db, transaction_id)
    # Only the fields the client actually sent. {"category_id": null} is in here
    # (meaning "clear it"); a field that wasn't sent is not.
    changes = payload.model_dump(exclude_unset=True)

    if "account_id" in changes:
        get_open_account(db, changes["account_id"])
    if changes.get("category_id") is not None:
        check_category_kind(get_category(db, changes["category_id"]), transfer=False)
    if "payee" in changes:
        name = changes.pop("payee")  # a name, not a column: turn it into a Payee
        transaction.payee = get_or_create_payee(db, name) if name else None
    if "notes" in changes:
        changes["notes"] = changes["notes"] or None

    for field, value in changes.items():
        setattr(transaction, field, value)
    db.commit()
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, db: DbSession):
    transaction = get_editable_transaction(db, transaction_id)
    db.delete(transaction)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
