"""CSV import endpoints: /api/import

Two steps, so nothing is saved until you've looked at it:
1. POST /api/import/preview  marks likely duplicates and suggests categories.
2. POST /api/import          creates any new accounts and categories, then the rows. All or nothing.

The same two endpoints serve a bank's statement (every row in one account) and your own
spreadsheet (each row names its account and category).
"""

import datetime as dt
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.checks import check_category_kind, get_category, get_open_account
from app.db import get_db
from app.importing import DUPLICATE_WINDOW_DAYS, Money, find_duplicates
from app.models import Account, Category, Payee, Transaction
from app.routers.categories import check_parent, duplicate_name
from app.schemas import (
    ImportCommitRequest,
    ImportPreviewRequest,
    ImportPreviewRow,
    ImportResult,
    NewAccount,
    NewCategory,
    Ref,
)

router = APIRouter(prefix="/api/import", tags=["import"])

DbSession = Annotated[Session, Depends(get_db)]


def last_category_by_payee(db: Session) -> dict[str, int]:
    """{lowercased payee name: the category its newest categorized transaction used}."""
    query = (
        select(Transaction)
        .options(joinedload(Transaction.payee))
        .where(
            Transaction.payee_id.is_not(None),
            Transaction.category_id.is_not(None),
            Transaction.transfer_id.is_(None),
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    result: dict[str, int] = {}
    for tx in db.scalars(query):
        result.setdefault(tx.payee.name.lower(), tx.category_id)  # newest first, so the first one wins
    return result


def duplicates_in_account(db: Session, account_id: int, rows: list[Money]) -> list[bool]:
    """find_duplicates for rows going into one existing account."""
    get_open_account(db, account_id)
    # Only transactions near the file's dates can match, so load just those.
    window = dt.timedelta(days=DUPLICATE_WINDOW_DAYS)
    saved = db.scalars(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.date >= min(r.date for r in rows) - window,
            Transaction.date <= max(r.date for r in rows) + window,
        )
    )
    return find_duplicates([Money(tx.date, tx.amount_cents) for tx in saved], rows)


@router.post("/preview", response_model=list[ImportPreviewRow])
def preview_import(payload: ImportPreviewRequest, db: DbSession):
    """Saves nothing. Returns the rows in the same order, each marked duplicate or not."""
    # Group row positions by account: each account's rows are compared with its own history.
    positions: dict[int, list[int]] = defaultdict(list)
    for i, row in enumerate(payload.rows):
        if row.account_id is not None:
            positions[row.account_id].append(i)

    duplicate = [False] * len(payload.rows)  # rows for new accounts stay False
    for account_id, indexes in positions.items():
        found = duplicates_in_account(db, account_id, [Money(payload.rows[i].date, payload.rows[i].amount_cents) for i in indexes])
        for i, is_duplicate in zip(indexes, found, strict=True):
            duplicate[i] = is_duplicate

    categories = last_category_by_payee(db)
    return [
        ImportPreviewRow(
            **row.model_dump(),
            duplicate=duplicate[i],
            suggested_category_id=categories.get(row.payee.lower()) if row.payee else None,
        )
        for i, row in enumerate(payload.rows)
    ]


def flush_or_409(db: Session, error: HTTPException) -> None:
    """Send pending inserts to the database now (to get ids), turning a unique-name clash into `error`."""
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise error


def create_accounts(db: Session, new: list[NewAccount]) -> dict[str, int]:
    """Create the import's new accounts. Returns {key: new id}."""
    ids: dict[str, int] = {}
    for item in new:
        if item.key in ids:
            raise HTTPException(status_code=422, detail=f"Two new accounts use the key '{item.key}'.")
        account = Account(name=item.name, type=item.type)
        db.add(account)
        flush_or_409(db, HTTPException(status_code=409, detail=f"An open account named '{item.name}' already exists."))
        ids[item.key] = account.id
    return ids


def create_categories(db: Session, new: list[NewCategory]) -> dict[str, int]:
    """Create the import's new categories. Returns {key: new id}.

    A new subcategory can sit under a new top-level category (parent is that one's key),
    so top-level and existing-parent ones are created first.
    """
    ids: dict[str, int] = {}
    for item in sorted(new, key=lambda c: isinstance(c.parent, str)):  # False (no new parent) sorts first
        if item.key in ids:
            raise HTTPException(status_code=422, detail=f"Two new categories use the key '{item.key}'.")
        parent_id = None if item.parent is None else resolve(item.parent, ids, "category")
        check_parent(db, parent_id, item.kind)
        category = Category(name=item.name, kind=item.kind, parent_id=parent_id)
        db.add(category)
        flush_or_409(db, duplicate_name(item.name, parent_id, item.kind))
        ids[item.key] = category.id
    return ids


def resolve(ref: Ref, new_ids: dict[str, int], what: str) -> int:
    """An id stays an id; a key becomes the id of the row this import just created."""
    if isinstance(ref, int):
        return ref
    if ref not in new_ids:
        raise HTTPException(status_code=422, detail=f"No new {what} has the key '{ref}'.")
    return new_ids[ref]


@router.post("", response_model=ImportResult, status_code=201)
def commit_import(payload: ImportCommitRequest, db: DbSession):
    """Create the new accounts and categories, then every row. If anything is invalid, nothing is saved."""
    account_ids = create_accounts(db, payload.new_accounts)
    category_ids = create_categories(db, payload.new_categories)

    # Check each account and category once, not once per row.
    checked_accounts: set[int] = set()
    checked_categories: set[int] = set()
    # Load every payee once ({lowercased name: Payee}) instead of a query per row.
    payees = {p.name.lower(): p for p in db.scalars(select(Payee))}

    for row in payload.rows:
        account_id = resolve(row.account, account_ids, "account")
        if account_id not in checked_accounts:
            get_open_account(db, account_id)
            checked_accounts.add(account_id)

        category_id = None if row.category is None else resolve(row.category, category_ids, "category")
        if category_id is not None and category_id not in checked_categories:
            check_category_kind(get_category(db, category_id), transfer=False)
            checked_categories.add(category_id)

        payee = None
        if row.payee:
            payee = payees.get(row.payee.lower())
            if payee is None:
                payee = payees[row.payee.lower()] = Payee(name=row.payee)
                db.add(payee)

        db.add(Transaction(
            account_id=account_id,
            date=row.date,
            amount_cents=row.amount_cents,
            payee=payee,
            category_id=category_id,
            notes=row.notes or None,
        ))
    # One commit for everything: the database transaction makes the import all or nothing.
    # (A 422 above ends the request before this, and the session is closed without committing.)
    db.commit()
    return ImportResult(
        created=len(payload.rows),
        created_accounts=len(account_ids),
        created_categories=len(category_ids),
    )
