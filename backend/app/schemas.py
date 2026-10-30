"""API shapes: what clients send in and what they get back.

These are separate from the database models on purpose. The client never
chooses an id or created_at, so those fields only appear on the "Read" shape.
"""

import datetime as dt
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

from app.models import AccountType, CategoryKind
from app.periods import PeriodKind

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


class TransactionUpdate(BaseModel):
    """PATCH body: send only the fields you want to change.

    Fields typed without "| None" (account_id, date, amount_cents) can be left out,
    but sending them as null is rejected, since a transaction can't lack them.
    Fields with "| None" can be sent as null to clear them.
    """

    # Reject unknown fields, so a typo like "amount" fails loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")

    account_id: int = None
    date: dt.date = None
    amount_cents: StrictInt = None
    payee: Name | None = None
    category_id: int | None = None
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


class TransferUpdate(BaseModel):
    """PATCH body for a transfer. Same rules as TransactionUpdate."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date = None
    amount_cents: Annotated[StrictInt, Field(gt=0)] = None
    description: Notes | None = None
    category_id: int | None = None


class TransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str | None
    created_at: datetime
    from_leg: TransactionRead
    to_leg: TransactionRead


class DashboardSummary(BaseModel):
    start: dt.date
    end: dt.date
    net_worth_cents: int  # all account balances at the end of `end`
    income_cents: int
    spending_cents: int  # positive number; refunds reduce it
    saved_cents: int  # income - spending; negative if you spent more than you earned


class CashFlowMonth(BaseModel):
    month: str  # "2026-10"
    income_cents: int
    spending_cents: int
    saved_cents: int


class PeriodRead(BaseModel):
    """The date ranges for one Month / Year / All view. Pass them to the other dashboard endpoints."""

    kind: PeriodKind
    start: dt.date
    end: dt.date  # never after today
    compare_start: dt.date | None  # None for "all"
    compare_end: dt.date | None
    previous_date: dt.date | None  # use as ?date= for the ‹ button; None for "all"
    next_date: dt.date | None  # for the › button; None if the next period hasn't started


class SubcategorySpending(BaseModel):
    category_id: int | None  # None = Uncategorized
    name: str
    spending_cents: int
    previous_cents: int | None  # None when no compare period was asked for


class CategorySpending(SubcategorySpending):
    """A top-level category; its spending includes all of its subcategories."""

    subcategories: list[SubcategorySpending]
