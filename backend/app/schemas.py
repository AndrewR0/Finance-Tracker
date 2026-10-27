"""API shapes: what clients send in and what they get back.

These are separate from the database models on purpose. The client never
chooses an id or created_at, so those fields only appear on the "Read" shape.
"""

import datetime as dt
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

from app.models import AccountType, CategoryKind

# Trims surrounding spaces, then requires 1-100 characters.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class AccountCreate(BaseModel):
    name: Name
    type: AccountType


class AccountRead(BaseModel):
    # Lets Pydantic read attributes off a SQLAlchemy object (account.name, ...).
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: AccountType
    created_at: datetime
    closed_at: datetime | None


class AccountWithBalance(AccountRead):
    # Calculated from transactions when the response is built, not a column.
    balance_cents: int


class CategoryCreate(BaseModel):
    name: Name
    kind: CategoryKind
    parent_id: int | None = None  # leave out for a top-level category


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    parent_id: int | None


class CategoryTree(CategoryRead):
    """A top-level category with its subcategories nested inside."""

    subcategories: list[CategoryRead]


Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class TransactionCreate(BaseModel):
    account_id: int
    date: dt.date  # "2026-10-22"
    # Integer cents, negative = money out. StrictInt rejects 84.12 and "8412",
    # so a dollar amount can't sneak in by accident.
    amount_cents: StrictInt
    payee: Name | None = None  # a name; the server finds or creates the Payee
    category_id: int | None = None  # None = uncategorized
    notes: Notes | None = None


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    date: dt.date
    amount_cents: int
    payee_id: int | None
    payee_name: str | None
    category_id: int | None
    notes: str | None
    transfer_id: int | None
    transfer_description: str | None
    created_at: datetime


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    date: dt.date
    # Always positive here: the server makes the "from" leg negative and the "to" leg positive.
    amount_cents: Annotated[StrictInt, Field(gt=0)]
    description: Notes | None = None
    category_id: int | None = None  # must be a transfer-kind category


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str | None
    created_at: datetime
    from_leg: TransactionRead
    to_leg: TransactionRead
