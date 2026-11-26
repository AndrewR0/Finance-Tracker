"""API shapes: what clients send in and what they get back.

These are separate from the database models on purpose. The client never
chooses an id or created_at, so those fields only appear on the "Read" shape.
"""

import datetime as dt
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints

from app.goals import GoalStatus
from app.models import AccountType, CategoryKind, PriceSource, SecurityKind, TradeKind
from app.periods import PeriodKind
from app.recurring import Cadence

# Trims surrounding spaces, then requires 1-100 characters.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class AccountCreate(BaseModel):
    name: Name
    type: AccountType
    # Leave out for the default: retirement accounts are left out of net worth, the rest count.
    in_net_worth: bool | None = None


class AccountUpdate(BaseModel):
    """PATCH body: send the fields you want to change (name, type, or both).

    Same rules as TransactionUpdate: a field can be left out, but not sent as null,
    because an account always has a name and a type.
    """

    model_config = ConfigDict(extra="forbid")  # a typo like {"nmae": ...} fails loudly

    name: Name = None
    type: AccountType = None
    in_net_worth: bool = None


class AccountRead(BaseModel):
    # Lets Pydantic read attributes off a SQLAlchemy object (account.name, ...).
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: AccountType
    created_at: datetime
    closed_at: datetime | None
    in_net_worth: bool  # False: the balance is left out of net worth (401k, Roth IRA)


class InvestmentRead(BaseModel):
    """Where a Brokerage or Retirement account's balance came from; the parts add up to it."""

    starting_cents: int  # the opening balance snapshot (before the first transfer)
    contributed_cents: int  # transfers in minus transfers out
    gain_cents: int  # later balance updates (market moves), dividends, fees
    # Once the account has holdings (Investments), these come from its lots instead.
    cost_basis_cents: int | None  # what the shares still held cost
    unrealized_gain_cents: int | None  # their market value minus that cost


class AccountWithBalance(AccountRead):
    # Calculated from transactions when the response is built, not a column.
    balance_cents: int
    investment: InvestmentRead | None  # only for Brokerage and Retirement accounts


class ReconcileRequest(BaseModel):
    """What your bank or card statement says the balance was at the end of `date`."""

    date: dt.date
    # Negative for money owed, like a credit card: owing $250.00 is -25000.
    balance_cents: StrictInt


class CategoryCreate(BaseModel):
    name: Name
    kind: CategoryKind
    parent_id: int | None = None  # leave out for a top-level category


class CategoryUpdate(BaseModel):
    """PATCH body: a new name, and/or a new parent.

    parent_id: an id moves it under that category; null makes it top-level.
    Leave a field out to keep it. The kind can't change: transactions and
    transfers were checked against it when they were saved.
    """

    model_config = ConfigDict(extra="forbid")

    name: Name = None
    parent_id: int | None = None
    # Top-level expense categories only; their subcategories follow along.
    counts_as_saving: bool = None


class CategoryDeleted(BaseModel):
    moved_transactions: int  # how many transactions now point at move_to (or are uncategorized)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: CategoryKind
    parent_id: int | None
    counts_as_saving: bool  # moved, not spent: counts toward Saved instead of Spending


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
    is_adjustment: bool  # a reconcile entry: not income or spending
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


class Change(BaseModel):
    """This period vs the compare period, for one number."""

    previous_cents: int
    change_cents: int  # now - previous
    change_percent: float | None  # None when previous is 0 (nothing to compare with)


class DashboardSummary(BaseModel):
    start: dt.date
    end: dt.date
    net_worth_cents: int  # balances of accounts that count in net worth, at the end of `end`
    net_worth_change_cents: int  # since the end of the day before `start`
    income_cents: int
    spending_cents: int  # positive number; refunds reduce it
    saved_cents: int  # income - spending; negative if you spent more than you earned
    # The part of saved_cents that was invested: transfers into Brokerage or Retirement accounts,
    # plus expenses in "counts as saving" categories.
    moved_to_savings_cents: int
    # These three are None unless compare_start and compare_end were given.
    income_change: Change | None
    spending_change: Change | None
    saved_change: Change | None


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


class PacePoint(BaseModel):
    label: str  # "1".."31" (day of the month) or "Jan".."Dec"
    current_cents: int | None  # spending so far; None for days that haven't happened yet
    previous_cents: int | None  # None past the end of a shorter previous period


class SpendingPace(BaseModel):
    kind: PeriodKind
    start: dt.date
    end: dt.date
    compare_start: dt.date
    compare_end: dt.date
    spent_cents: int  # this period so far
    previous_same_point_cents: int  # previous period, up to the same point
    previous_total_cents: int  # the whole previous period
    projected_cents: int  # where this period ends up at the current daily average
    points: list[PacePoint]


class SubcategorySpending(BaseModel):
    category_id: int | None  # None = Uncategorized
    name: str
    # For a "counts as saving" category (only listed with include_saving), the amount moved to savings.
    spending_cents: int
    previous_cents: int | None  # None when no compare period was asked for
    counts_as_saving: bool


class CategorySpending(SubcategorySpending):
    """A top-level category; its spending includes all of its subcategories."""

    subcategories: list[SubcategorySpending]


class ReconcileResult(BaseModel):
    previous_balance_cents: int  # what the app had for that date before reconciling
    balance_cents: int  # what it has now (the statement balance)
    adjustment: TransactionRead | None  # None when it already matched


# ---- CSV import ----
# The browser reads the CSV file and turns each line into an ImportRow. The server
# never sees the file itself, only clean rows, so it doesn't care where the file came from:
# a bank's export, or your own spreadsheet saved as CSV.

class ImportRow(BaseModel):
    date: dt.date
    amount_cents: StrictInt  # negative = money out, like everywhere else
    payee: Name | None = None
    notes: Notes | None = None


MAX_IMPORT_ROWS = 50_000  # decades of hand-kept rows; more is probably the wrong file


class ImportPreviewItem(ImportRow):
    account_id: int | None = None  # None: going into a new account, so nothing can be a duplicate


class ImportPreviewRequest(BaseModel):
    rows: Annotated[list[ImportPreviewItem], Field(max_length=MAX_IMPORT_ROWS)]


class ImportPreviewRow(ImportPreviewItem):
    duplicate: bool  # looks like a transaction that's already in this account
    suggested_category_id: int | None  # the category last used with this payee


# A reference to an account or category in an import: an int is the id of one that exists,
# a str is the key of one in new_accounts / new_categories, created by this same import.
# The browser can't know a new row's id before the database makes it, so it uses its own
# temporary keys ("account:Amex"), and the server swaps them for real ids.
Ref = StrictInt | Annotated[str, StringConstraints(min_length=1, max_length=250)]


class NewAccount(BaseModel):
    key: str
    name: Name
    type: AccountType


class NewCategory(BaseModel):
    key: str
    name: Name
    kind: CategoryKind
    parent: Ref | None = None  # an existing top-level category, another new one, or None


class ImportCommitRow(ImportRow):
    account: Ref
    category: Ref | None = None  # None = uncategorized


class ImportCommitRequest(BaseModel):
    new_accounts: list[NewAccount] = []
    new_categories: list[NewCategory] = []
    rows: Annotated[list[ImportCommitRow], Field(min_length=1, max_length=MAX_IMPORT_ROWS)]


class ImportResult(BaseModel):
    created: int  # transactions
    created_accounts: int
    created_categories: int


# ---- recurring ----

class RecurringRead(BaseModel):
    payee_id: int
    payee_name: str
    matched_amount_cents: int | None  # set when only this exact amount repeats (rent by Zelle)
    category_id: int | None
    account_id: int
    cadence: Cadence
    amount_cents: int  # the typical charge, as a POSITIVE number
    amount_varies: bool  # True: amount_cents is an estimate (a gas or water bill)
    monthly_cents: int  # average cost per month
    charges: int  # how many charges the pattern is based on
    last_date: dt.date
    next_date: dt.date  # may be a few days past: due, not posted yet
    ignored: bool


class UpcomingCharge(BaseModel):
    date: dt.date
    payee_id: int
    payee_name: str
    category_id: int | None
    cadence: Cadence
    amount_cents: int
    amount_varies: bool


class RecurringIgnore(BaseModel):
    payee_id: int
    matched_amount_cents: int | None = None
    ignored: bool


# ---- goals ----

class GoalCreate(BaseModel):
    name: Name
    account_id: int  # the account whose balance funds it
    target_cents: Annotated[StrictInt, Field(gt=0)]
    target_date: dt.date | None = None  # optional "by when"


class GoalUpdate(BaseModel):
    """PATCH body. Same rules as TransactionUpdate. archived: true when you bought it."""

    model_config = ConfigDict(extra="forbid")

    name: Name = None
    account_id: int = None
    target_cents: Annotated[StrictInt, Field(gt=0)] = None
    target_date: dt.date | None = None
    archived: bool = None


class GoalRead(BaseModel):
    id: int
    name: str
    account_id: int
    target_cents: int
    target_date: dt.date | None
    position: int  # fill order among goals on the same account
    archived_at: datetime | None
    created_at: datetime
    # Worked out from the account's balance, not stored. Archived goals show 0 saved.
    saved_cents: int
    status: GoalStatus
    eta: dt.date | None  # funded around this date at the account's current pace
    needed_per_month_cents: int | None  # to reach the target by target_date
    account_pace_cents: int  # how much the account grew per month, on average, lately


class GoalOrder(BaseModel):
    """Every goal id, in the order they should fill."""

    ids: Annotated[list[int], Field(min_length=1)]


# ---- Investments ----

Ticker = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20)]
# Sent as a string ("0.03841207") so no float rounding happens on the way in.
Shares = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=8)]


class HoldingInput(BaseModel):
    """One holding, copied from your provider's cost basis page."""

    ticker: Ticker
    name: Name
    kind: SecurityKind
    price_source: PriceSource = PriceSource.YFINANCE  # manual: no public ticker (some 401k funds)
    shares: Shares
    cost_basis_cents: Annotated[StrictInt, Field(ge=0)]
    market_value_cents: Annotated[StrictInt, Field(ge=0)]  # today's value; sets the first price


class HoldingsSetup(BaseModel):
    """Start tracking an account's holdings: one opening lot per holding, all on `date`."""

    date: dt.date
    cash_cents: StrictInt = 0  # uninvested cash in the account (a settlement fund counts as a holding)
    holdings: Annotated[list[HoldingInput], Field(min_length=1)]


class HoldingRead(BaseModel):
    security_id: int
    ticker: str
    name: str
    kind: SecurityKind
    price_source: PriceSource
    shares: int  # units of 1/100,000,000 of a share
    cost_basis_cents: int
    price: int | None  # units of 1/1,000,000 of a dollar; None until there's a price
    price_date: dt.date | None
    value_cents: int
    gain_cents: int  # unrealized: value - cost basis
    realized_cents: int  # locked in by sells
    dividends_cents: int  # cash it paid out


class AccountHoldings(BaseModel):
    account_id: int
    account_name: str
    in_net_worth: bool
    cash_cents: int
    value_cents: int  # cash + holdings
    cost_basis_cents: int
    gain_cents: int  # unrealized, all holdings
    realized_cents: int  # from sells, including holdings since sold out
    dividends_cents: int
    can_undo: bool  # only opening lots so far, so the setup can be undone
    holdings: list[HoldingRead]


class PriceInput(BaseModel):
    date: dt.date
    price: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]  # dollars per share, as a string


class PriceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    security_id: int
    date: dt.date
    price: int  # units of 1/1,000,000 of a dollar
    source: PriceSource


class PriceStatus(BaseModel):
    """How fresh automatic prices are, for the Investments page."""

    refreshed_at: datetime | None  # the latest refresh since the app started; None if none yet
    updated: int  # prices that refresh added or changed
    failed: dict[str, str]  # ticker -> what went wrong
    prices_as_of: dt.date | None  # newest automatic price


class SecurityUpdate(BaseModel):
    """PATCH body: switch a security between automatic and typed-in prices."""

    model_config = ConfigDict(extra="forbid")

    price_source: PriceSource


class NewSecurity(BaseModel):
    """A security the account hasn't held before."""

    ticker: Ticker
    name: Name
    kind: SecurityKind
    price_source: PriceSource = PriceSource.YFINANCE


class TradeCreate(BaseModel):
    """One buy, sell, dividend or contribution. Give security_id, or new_security for a first buy."""

    date: dt.date
    kind: TradeKind
    security_id: int | None = None
    new_security: NewSecurity | None = None
    shares: Shares | None = None  # every kind but dividend
    # buy / contribution: what it cost, fees included. sell: what you got, after fees.
    # dividend: the cash paid.
    amount_cents: Annotated[StrictInt, Field(gt=0)]
    # Dividend only: shares bought right away with it (a reinvested dividend). The app adds
    # the matching buy for the same amount.
    reinvested_shares: Shares | None = None


class TradeRead(BaseModel):
    id: int
    date: dt.date
    kind: TradeKind
    security_id: int
    ticker: str
    shares: int  # units of 1/100,000,000 of a share; 0 for a dividend
    amount_cents: int
