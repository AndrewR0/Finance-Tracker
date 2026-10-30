"""Transfer endpoints: /api/transfers (money moving between your own accounts)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.checks import check_category_kind, get_category, get_open_account
from app.db import get_db
from app.models import Transaction, Transfer
from app.schemas import TransferCreate, TransferRead, TransferUpdate

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


def get_transfer(db: Session, transfer_id: int) -> Transfer:
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} does not exist.")
    return transfer


@router.get("/{transfer_id}", response_model=TransferRead)
def read_transfer(transfer_id: int, db: DbSession):
    """Both legs of one transfer (the edit panel needs the from and to accounts)."""
    return get_transfer(db, transfer_id)


@router.patch("/{transfer_id}", response_model=TransferRead)
def update_transfer(transfer_id: int, payload: TransferUpdate, db: DbSession):
    transfer = get_transfer(db, transfer_id)
    changes = payload.model_dump(exclude_unset=True)  # only what the client sent
    if changes.get("category_id") is not None:
        check_category_kind(get_category(db, changes["category_id"]), transfer=True)

    from_leg = transfer.from_leg
    to_leg = transfer.to_leg

    if "date" in changes:
        from_leg.date = changes["date"]
        to_leg.date = changes["date"]
    if "amount_cents" in changes:
        from_leg.amount_cents = -changes["amount_cents"]
        to_leg.amount_cents = changes["amount_cents"]
    if "description" in changes:
        transfer.description = changes["description"] or None
    if "category_id" in changes:
        from_leg.category_id = changes["category_id"]
        to_leg.category_id = changes["category_id"]
    
    db.commit()
    return transfer


@router.delete("/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(transfer_id: int, db: DbSession):
    # The legs relationship has cascade="all, delete-orphan", so both legs go too.
    db.delete(get_transfer(db, transfer_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
