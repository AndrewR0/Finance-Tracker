"""Validation helpers shared by several routers.

Each one loads a row and raises HTTPException(422) with a readable message if
the row can't be used. On success it returns the row, so callers can use it.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Account, Category, CategoryKind


def get_open_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=422, detail=f"Account {account_id} does not exist.")
    if account.closed_at is not None:
        raise HTTPException(status_code=422, detail=f"{account.name} is closed, so it can't get new transactions.")
    return account


def get_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=422, detail=f"Category {category_id} does not exist.")
    return category


def check_category_kind(category: Category, *, transfer: bool) -> None:
    """Transfers need a transfer category; income and expenses need anything else."""
    if transfer and category.kind != CategoryKind.TRANSFER:
        raise HTTPException(status_code=422, detail=f"{category.name} is an {category.kind} category, not a transfer category.")
    if not transfer and category.kind == CategoryKind.TRANSFER:
        raise HTTPException(status_code=422, detail="Use the transfer endpoint for transfers between accounts.")
