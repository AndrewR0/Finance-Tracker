"""Database tables, written as SQLAlchemy models."""

import datetime as dt
import enum
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, UniqueConstraint, false, func, text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AccountType(enum.StrEnum):
    """Matches the groups on the mockup's Accounts page."""

    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    BROKERAGE = "brokerage"
    CASH = "cash"
    RETIREMENT = "retirement"  # 401k, Roth IRA: balance snapshots, left out of net worth by default


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
    # False keeps the balance out of net worth: money you can't reach yet (401k, Roth IRA).
    in_net_worth: Mapped[bool] = mapped_column(default=True, server_default=true())


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
    # Expense categories only. Money here is moved, not spent (Roth IRA, brokerage): it counts
    # toward Saved instead of Spending. Set on a top-level category; its subcategories copy it,
    # so reports can read it straight off each row without joining the parent.
    counts_as_saving: Mapped[bool] = mapped_column(default=False, server_default=false())

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
    # Set on both legs of a transfer; None for ordinary income and expenses.
    transfer_id: Mapped[int | None] = mapped_column(ForeignKey("transfers.id"), index=True)
    # A reconcile entry: it fixes a balance to match a statement. Like a transfer, it is
    # neither income nor spending. server_default fills in existing rows during the migration.
    is_adjustment: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    payee: Mapped[Payee | None] = relationship()
    transfer: Mapped["Transfer | None"] = relationship(back_populates="legs")

    @property
    def payee_name(self) -> str | None:
        return self.payee.name if self.payee else None

    @property
    def transfer_description(self) -> str | None:
        return self.transfer.description if self.transfer else None


class Transfer(Base):
    """Links the two legs of a move between accounts: money out of one, into the other.

    Date and amount live on the legs only, so there is one source of truth.
    """

    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # cascade: deleting a Transfer deletes its legs too, so half a transfer can't be left behind.
    legs: Mapped[list[Transaction]] = relationship(back_populates="transfer", cascade="all, delete-orphan")

    @property
    def from_leg(self) -> Transaction:
        """The leg where money leaves (negative amount)."""
        return next(leg for leg in self.legs if leg.amount_cents < 0)

    @property
    def to_leg(self) -> Transaction:
        """The leg where money arrives (positive amount)."""
        return next(leg for leg in self.legs if leg.amount_cents > 0)


class RecurringSeries(Base):
    """Your choice about one detected recurring series. Only "ignore it", for now.

    The series themselves are never stored: app/recurring.py derives them from transactions.
    A series is named by its payee, plus an amount when only that exact amount repeats
    (rent by Zelle, among other Zelle payments).
    """

    __tablename__ = "recurring_series"
    __table_args__ = (
        # SQLite treats NULLs as all different, so this alone doesn't stop two rows with a
        # NULL amount for one payee. The router looks a row up before adding one.
        UniqueConstraint("payee_id", "matched_amount_cents", name="uq_recurring_series"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    payee_id: Mapped[int] = mapped_column(ForeignKey("payees.id"))
    matched_amount_cents: Mapped[int | None]
    ignored: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Goal(Base):
    """Something you're saving up for, funded by the balance of one account.

    Progress is never stored: app/goals.py works it out from the account's balance.
    When several goals share an account, they fill in `position` order (lowest first).
    """

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    target_cents: Mapped[int]
    target_date: Mapped[dt.date | None]
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    # Set when you bought the thing (or gave up). An archived goal stops claiming money,
    # so the goals after it on the same account move up.
    archived_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---- Investments (feature 5) ----
#
# Holdings are never stored: app/holdings.py derives them from trades, FIFO.
# No floats: shares are whole units of 1/100,000,000 of a share (bitcoin's 8 decimals),
# prices are whole millionths of a dollar, money is cents.

SHARE_UNITS = 100_000_000  # units per share
PRICE_UNITS = 1_000_000  # price units per dollar


class SecurityKind(enum.StrEnum):
    FUND = "fund"
    STOCK = "stock"
    CRYPTO = "crypto"
    OTHER = "other"


class PriceSource(enum.StrEnum):
    YFINANCE = "yfinance"  # has a public ticker; prices fetched automatically (step 2)
    MANUAL = "manual"  # e.g. a 401k fund with no public ticker: you type the price in


class Security(Base):
    """Something you can own: a fund, a stock, bitcoin."""

    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NOCASE, like payee names: "vtsax" and "VTSAX" are the same security.
    ticker: Mapped[str] = mapped_column(String(20, collation="NOCASE"), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[SecurityKind] = mapped_column(Enum(SecurityKind, native_enum=False, values_callable=lambda obj: [e.value for e in obj]))
    price_source: Mapped[PriceSource] = mapped_column(Enum(PriceSource, native_enum=False, values_callable=lambda obj: [e.value for e in obj]))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TradeKind(enum.StrEnum):
    # A holding you already had when you started tracking it, at your provider's cost basis.
    # Unlike a buy, it doesn't use the account's cash: that money was already in the account.
    OPENING = "opening"
    BUY = "buy"  # paid from the account's cash
    SELL = "sell"  # proceeds go to the account's cash
    # Cash paid out by a holding. Gain inside the account, not income on the dashboard.
    # shares is 0; reinvesting it is a separate buy.
    DIVIDEND = "dividend"
    # Shares bought with money that never passed through the app, like 401k payroll
    # contributions. A lot, like a buy, but no cash leaves the account.
    CONTRIBUTION = "contribution"


class Trade(Base):
    """One opening lot, buy or sell. Both amounts are positive; kind says which way they go."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    date: Mapped[dt.date]
    kind: Mapped[TradeKind] = mapped_column(Enum(TradeKind, native_enum=False, values_callable=lambda obj: [e.value for e in obj]))
    shares: Mapped[int]  # units of 1/SHARE_UNITS of a share
    # Cost basis for opening, buy and contribution (fees included), proceeds for sell
    # (fees taken off), the cash paid for a dividend.
    amount_cents: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    security: Mapped[Security] = relationship()


class Price(Base):
    """One security's closing price on one day."""

    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("security_id", "date", name="uq_price_per_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"))
    date: Mapped[dt.date]
    price: Mapped[int]  # units of 1/PRICE_UNITS of a dollar
    source: Mapped[PriceSource] = mapped_column(Enum(PriceSource, native_enum=False, values_callable=lambda obj: [e.value for e in obj]))


class BenchmarkPrice(Base):
    """One day of a benchmark (SPY for the S&P 500): its close, and any dividend paid that day.

    Raw closes and dividend amounts, not Yahoo's "adjusted close": an adjusted series gets
    rescaled every time a dividend is paid, so stored values would stop agreeing with new
    ones. app/benchmark.py reinvests the dividends itself instead.
    """

    __tablename__ = "benchmark_prices"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_benchmark_price_per_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    date: Mapped[dt.date]
    close: Mapped[int]  # units of 1/PRICE_UNITS of a dollar
    dividend: Mapped[int] = mapped_column(default=0, server_default="0")  # per share, same units
