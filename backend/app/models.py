"""Database tables, written as SQLAlchemy models."""

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
