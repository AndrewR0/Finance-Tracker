"""Database tables, written as SQLAlchemy models."""

import datetime as dt
import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AccountType(enum.StrEnum):
    """Matches the groups on the mockup's Accounts page."""

    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    BROKERAGE = "brokerage"
    CASH = "cash"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("uq_open_account_name", "name", unique=True,
              sqlite_where=text("closed_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[AccountType] = mapped_column(Enum(AccountType, native_enum=False, values_callable=lambda obj: [e.value for e in obj]))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column()


class CategoryKind(enum.StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class Category(Base):
    """A category, or a subcategory when parent_id is set. Only one level deep."""

    __tablename__ = "categories"
    __table_args__ = (
        # Top-level names are unique per kind ("Other" can be both income and expense).
        Index("uq_top_level_category_name", "kind", "name", unique=True,
              sqlite_where=text("parent_id IS NULL")),
        # Subcategory names are unique within their parent.
        UniqueConstraint("parent_id", "name", name="uq_subcategory_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[CategoryKind] = mapped_column(Enum(CategoryKind, native_enum=False, values_callable=lambda obj: [e.value for e in obj]))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    # Python-side links between rows. No new columns: both use parent_id.
    # remote_side tells SQLAlchemy which end is the parent, since both ends are this table.
    parent: Mapped["Category | None"] = relationship(back_populates="subcategories", remote_side=[id])
    subcategories: Mapped[list["Category"]] = relationship(back_populates="parent", order_by="Category.name")


class Payee(Base):
    """Who you paid or got paid by. Reused across transactions."""

    __tablename__ = "payees"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NOCASE: SQLite compares this column ignoring upper/lower case (ASCII letters),
    # so "Trader Joe's" and "trader joe's" are the same payee, for == and for unique.
    name: Mapped[str] = mapped_column(String(100, collation="NOCASE"), unique=True)


class Transaction(Base):
    """Money in (positive) or out (negative) of one account on one day."""

    __tablename__ = "transactions"
    __table_args__ = (
        # Most lookups are "this account, newest first" or "everything in a date range".
        Index("ix_transactions_account_date", "account_id", "date"),
        Index("ix_transactions_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    # dt.date, not date: inside this class, the name "date" means this column.
    date: Mapped[dt.date]
    amount_cents: Mapped[int]
    payee_id: Mapped[int | None] = mapped_column(ForeignKey("payees.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    payee: Mapped[Payee | None] = relationship()

    @property
    def payee_name(self) -> str | None:
        return self.payee.name if self.payee else None
