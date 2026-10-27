"""Transfer endpoints: /api/transfers (money moving between your own accounts)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.checks import check_category_kind, get_category, get_open_account
from app.db import get_db
from app.models import Transaction, Transfer
from app.schemas import TransferCreate, TransferRead

router = APIRouter(prefix="/api/transfers", tags=["transfers"])

DbSession = Annotated[Session, Depends(get_db)]


def check_transfer(db: Session, payload: TransferCreate) -> None:
    """Raise HTTPException(422) if this transfer can't happen."""
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(status_code=422, detail="A transfer needs two different accounts.")
    get_open_account(db, payload.from_account_id)
    get_open_account(db, payload.to_account_id)
    if payload.category_id is not None:
        check_category_kind(get_category(db, payload.category_id), transfer=True)


@router.post("", response_model=TransferRead, status_code=status.HTTP_201_CREATED)
def create_transfer(payload: TransferCreate, db: DbSession):
    check_transfer(db, payload)

    shared = dict(date=payload.date, category_id=payload.category_id)

    from_leg = Transaction(
        account_id=payload.from_account_id,
        amount_cents=-payload.amount_cents,
        **shared
    )
    to_leg = Transaction(
        account_id=payload.to_account_id,
        amount_cents=payload.amount_cents,
        **shared
    )

    transfer = Transfer(
        description=payload.description or None,
        legs=[from_leg, to_leg]
    )
    db.add(transfer)
    db.commit()
    return transfer
