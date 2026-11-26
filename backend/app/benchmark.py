"""You vs the S&P 500: what the same deposits, on the same days, would be worth in SPY.

Deposits are derived, never stored. For an investment account they are:
- transfers in (+) and out (-),
- its opening balance: balance updates in its first week, before any transfer
  (see app/balances.py for the same rule),
- 401k contributions (trades of kind "contribution": payroll money the app never saw),
- for an account whose history starts with its holdings setup, its value on that day.
Market moves (later balance updates), dividends and the setup's own adjustment are not deposits.

The pretend SPY account buys at the close of the first trading day on or after each deposit,
and reinvests every dividend at that day's close. Decimal math, rounded to cents at the end.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.balances import SETUP_DAYS, get_account_values
from app.holdings import SETUP_NOTE
from app.models import PRICE_UNITS, Account, AccountType, BenchmarkPrice, Trade, TradeKind, Transaction
from app.prices import BENCHMARK

INVESTMENT_TYPES = (AccountType.BROKERAGE, AccountType.RETIREMENT)


@dataclass(frozen=True)
class Deposit:
    account_id: int
    date: dt.date
    cents: int  # negative for money taken out


def investment_account_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Account.id).where(Account.type.in_(INVESTMENT_TYPES))))


def get_deposits(db: Session, account_ids: list[int]) -> list[Deposit]:
    """Every deposit into the given accounts, oldest first."""
    deposits: list[Deposit] = []
    rows = db.execute(
        select(Transaction.account_id, Transaction.date, Transaction.amount_cents, Transaction.transfer_id,
               Transaction.is_adjustment, Transaction.notes)
        .where(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.date, Transaction.id)
    ).all()
    trades = db.scalars(select(Trade).where(Trade.account_id.in_(account_ids))).all()

    first_day: dict[int, dt.date] = {}
    for account_id, date, *_ in rows:
        first_day.setdefault(account_id, date)
    for trade in trades:
        if trade.account_id not in first_day or trade.date < first_day[trade.account_id]:
            first_day[trade.account_id] = trade.date

    had_transfer: set[int] = set()
    for account_id, date, cents, transfer_id, is_adjustment, notes in rows:
        if transfer_id is not None:
            deposits.append(Deposit(account_id, date, cents))
            had_transfer.add(account_id)
        elif is_adjustment and notes != SETUP_NOTE and account_id not in had_transfer \
                and (date - first_day[account_id]).days < SETUP_DAYS:
            deposits.append(Deposit(account_id, date, cents))  # the opening balance

    for trade in trades:
        if trade.kind == TradeKind.CONTRIBUTION:
            deposits.append(Deposit(trade.account_id, trade.date, trade.amount_cents))

    # An account first seen at its holdings setup: what it held that day is its first deposit.
    setup_day: dict[int, dt.date] = {}
    for trade in trades:
        if trade.kind == TradeKind.OPENING:
            setup_day[trade.account_id] = trade.date
    for account_id, day in setup_day.items():
        if not any(d.account_id == account_id and d.date <= day for d in deposits):
            value = get_account_values(db, day).get(account_id, 0)
            if value:
                deposits.append(Deposit(account_id, day, value))

    return sorted(deposits, key=lambda d: d.date)


def first_deposit_date(db: Session) -> dt.date | None:
    deposits = get_deposits(db, investment_account_ids(db))
    return deposits[0].date if deposits else None


@dataclass(frozen=True)
class Day:
    date: dt.date
    close: Decimal  # dollars
    dividend: Decimal  # dollars per share paid that day


def benchmark_days(db: Session) -> list[Day]:
    rows = db.scalars(select(BenchmarkPrice).where(BenchmarkPrice.symbol == BENCHMARK).order_by(BenchmarkPrice.date))
    return [Day(r.date, Decimal(r.close) / PRICE_UNITS, Decimal(r.dividend) / PRICE_UNITS) for r in rows]


def to_cents(dollars: Decimal) -> int:
    return int((dollars * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def benchmark_values(days: list[Day], deposits: list[Deposit], dates: list[dt.date]) -> dict[dt.date, int | None]:
    """{date: value in cents of the pretend SPY account at the end of that date}, for each of `dates`.

    None for a date before the first benchmark price. Deposits on a non-trading day buy at
    the next trading day's close; until then they count at face value (as uninvested cash).
    """
    pending = sorted(deposits, key=lambda d: d.date)
    targets = sorted(dates)
    result: dict[dt.date, int | None] = {}
    shares = Decimal(0)
    cash = Decimal(0)  # deposited, waiting for the next trading day
    last_close: Decimal | None = None
    i = j = 0

    def settle_until(day: dt.date) -> None:
        nonlocal i, cash
        while i < len(pending) and pending[i].date <= day:
            cash += Decimal(pending[i].cents) / 100
            i += 1

    for day in days:
        # Report every target date that ends before this trading day.
        while j < len(targets) and targets[j] < day.date:
            settle_until(targets[j])
            result[targets[j]] = None if last_close is None else to_cents(shares * last_close + cash)
            j += 1
        if day.dividend and shares:
            shares += shares * day.dividend / day.close  # reinvested at the close
        settle_until(day.date)
        if cash:
            shares += cash / day.close
            cash = Decimal(0)
        last_close = day.close
    while j < len(targets):
        settle_until(targets[j])
        result[targets[j]] = None if last_close is None else to_cents(shares * last_close + cash)
        j += 1
    return result


@dataclass
class Point:
    date: dt.date
    put_in_cents: int
    benchmark_cents: int | None
    value_cents: int | None  # yours; None before the app tracked market value for these accounts


@dataclass
class Comparison:
    start: dt.date | None
    put_in_cents: int
    value_cents: int
    benchmark_cents: int | None
    benchmark_as_of: dt.date | None
    tracked_since: dt.date | None
    points: list[Point]


def weekly_dates(start: dt.date, end: dt.date) -> list[dt.date]:
    dates = []
    day = start
    while day < end:
        dates.append(day)
        day += dt.timedelta(days=7)
    dates.append(end)
    return dates


def compare(db: Session, account_ids: list[int], today: dt.date) -> Comparison:
    deposits = get_deposits(db, account_ids)
    values_now = get_account_values(db)
    value_now = sum(values_now.get(a, 0) for a in account_ids)
    if not deposits:
        return Comparison(None, 0, value_now, None, None, None, [])

    days = benchmark_days(db)
    start = deposits[0].date
    dates = weekly_dates(start, today)
    benchmark = benchmark_values(days, deposits, dates)

    # Your value is known from when every included account with holdings was set up.
    first_trade: dict[int, dt.date] = {}
    for account_id, date in db.execute(select(Trade.account_id, Trade.date).where(Trade.account_id.in_(account_ids))):
        if account_id not in first_trade or date < first_trade[account_id]:
            first_trade[account_id] = date
    tracked_since = max(first_trade.values()) if first_trade else None

    points = []
    running = 0
    k = 0
    for date in dates:
        while k < len(deposits) and deposits[k].date <= date:
            running += deposits[k].cents
            k += 1
        yours = None
        if tracked_since is not None and date >= tracked_since:
            values = values_now if date == today else get_account_values(db, date)
            yours = sum(values.get(a, 0) for a in account_ids)
        points.append(Point(date, running, benchmark[date], yours))

    return Comparison(
        start=start,
        put_in_cents=running,
        value_cents=value_now,
        benchmark_cents=benchmark[today],
        benchmark_as_of=days[-1].date if days else None,
        tracked_since=tracked_since,
        points=points,
    )
