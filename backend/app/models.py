"""Database tables, written as SQLAlchemy models."""

import enum
from datetime import datetime

from sqlalchemy import Index, Enum, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

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
