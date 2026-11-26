"""Holdings, derived from trades. Never stored.

FIFO (first in, first out): a sell uses up the oldest lot first. A lot is what's left of one
opening lot, buy or contribution: how many shares, and what they cost.

Units (see app/models.py): shares in 1/SHARE_UNITS of a share, prices in 1/PRICE_UNITS of a
dollar, money in cents. Everything is integer math; rounding happens once, in value_cents().
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PRICE_UNITS, SHARE_UNITS, Price, Security, Trade, TradeKind

# Marks the balance adjustment a holdings setup adds (see app/routers/investments.py).
SETUP_NOTE = "Holdings set up"

# shares (units) x price (units) / CENTS_DIVISOR = cents
CENTS_DIVISOR = SHARE_UNITS * PRICE_UNITS // 100


def divide_round(numerator: int, denominator: int) -> int:
    """Integer division, rounding halves away from zero: divide_round(5, 2) == 3, (-5, 2) == -3."""
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    numerator, denominator = abs(numerator), abs(denominator)
    return sign * ((numerator * 2 + denominator) // (denominator * 2))


def value_cents(shares: int, price: int) -> int:
    """What `shares` are worth at `price`, in cents."""
    return divide_round(shares * price, CENTS_DIVISOR)


def price_from_value(shares: int, cents: int) -> int:
    """The price that makes `shares` worth `cents`: price_from_value(SHARE_UNITS, 12345) == 123.45 dollars."""
    return divide_round(cents * CENTS_DIVISOR, shares)


@dataclass
class Lot:
    trade_id: int
    account_id: int
    security_id: int
    date: dt.date
    shares: int
    cost_cents: int


@dataclass
class Position:
    """One security in one account: its open lots added up."""

    account_id: int
    security: Security
    shares: int
    cost_cents: int
    realized_cents: int  # gains locked in by sells (proceeds - cost of the shares sold)
    dividends_cents: int  # cash it paid out
    price: int | None  # latest price on or before the as_of day; None if there isn't one yet
    price_date: dt.date | None

    @property
    def value_cents(self) -> int:
        """Market value. With no price yet, the cost basis stands in for it."""
        return self.cost_cents if self.price is None else value_cents(self.shares, self.price)


# Trades that add a lot. Opening and contribution lots don't touch the account's cash.
ADDS_LOT = (TradeKind.OPENING, TradeKind.BUY, TradeKind.CONTRIBUTION)


@dataclass
class Fifo:
    """What running trades through FIFO gives. Keys are (account_id, security_id)."""

    lots: list[Lot]
    realized: dict[tuple[int, int], int]
    dividends: dict[tuple[int, int], int]
    oversold: list[int]  # ids of sells for more shares than were held at the time


def run_fifo(trades: list[Trade]) -> Fifo:
    """Run trades, oldest first (same day: in the order they were entered), through FIFO."""
    lots: dict[tuple[int, int], list[Lot]] = defaultdict(list)
    realized: dict[tuple[int, int], int] = defaultdict(int)
    dividends: dict[tuple[int, int], int] = defaultdict(int)
    oversold: list[int] = []
    for trade in sorted(trades, key=lambda t: (t.date, t.id)):
        key = (trade.account_id, trade.security_id)
        if trade.kind in ADDS_LOT:
            lots[key].append(Lot(trade.id, trade.account_id, trade.security_id, trade.date, trade.shares, trade.amount_cents))
            continue
        if trade.kind == TradeKind.DIVIDEND:
            dividends[key] += trade.amount_cents
            continue
        # A sell: take shares from the oldest lots first.
        to_sell = trade.shares
        cost_sold = 0
        queue = lots[key]
        while to_sell > 0 and queue:
            lot = queue[0]
            taken = min(to_sell, lot.shares)
            # The cost of part of a lot is its share of the lot's cost.
            cost = lot.cost_cents if taken == lot.shares else divide_round(lot.cost_cents * taken, lot.shares)
            lot.shares -= taken
            lot.cost_cents -= cost
            cost_sold += cost
            to_sell -= taken
            if lot.shares == 0:
                queue.pop(0)
        if to_sell > 0:
            oversold.append(trade.id)
        realized[key] += trade.amount_cents - cost_sold
    return Fifo([lot for queue in lots.values() for lot in queue], dict(realized), dict(dividends), oversold)


def latest_prices(db: Session, as_of: dt.date | None = None) -> dict[int, tuple[int, dt.date]]:
    """{security_id: (price, date)}: each security's newest price on or before as_of."""
    newest = select(Price.security_id, func.max(Price.date).label("date")).group_by(Price.security_id)
    if as_of is not None:
        newest = newest.where(Price.date <= as_of)
    newest = newest.subquery()
    rows = db.execute(
        select(Price.security_id, Price.price, Price.date).join(
            newest, (Price.security_id == newest.c.security_id) & (Price.date == newest.c.date)
        )
    )
    return {security_id: (price, date) for security_id, price, date in rows}


def get_trades(db: Session, as_of: dt.date | None = None, account_id: int | None = None) -> list[Trade]:
    query = select(Trade)
    if as_of is not None:
        query = query.where(Trade.date <= as_of)
    if account_id is not None:
        query = query.where(Trade.account_id == account_id)
    return list(db.scalars(query))


def get_positions(db: Session, as_of: dt.date | None = None) -> list[Position]:
    """Every security held in every account at the end of as_of (None = today), with its price."""
    trades = get_trades(db, as_of)
    if not trades:
        return []
    fifo = run_fifo(trades)
    prices = latest_prices(db, as_of)
    securities = {t.security_id: t.security for t in trades}

    totals: dict[tuple[int, int], list[int]] = {}
    for lot in fifo.lots:
        shares_cost = totals.setdefault((lot.account_id, lot.security_id), [0, 0])
        shares_cost[0] += lot.shares
        shares_cost[1] += lot.cost_cents
    for key in [*fifo.realized, *fifo.dividends]:  # sold out: still listed, for its realized gain
        totals.setdefault(key, [0, 0])

    positions = []
    for (account_id, security_id), (shares, cost) in totals.items():
        price, price_date = prices.get(security_id, (None, None))
        key = (account_id, security_id)
        positions.append(Position(account_id, securities[security_id], shares, cost,
                                  fifo.realized.get(key, 0), fifo.dividends.get(key, 0), price, price_date))
    return sorted(positions, key=lambda p: (p.account_id, -p.value_cents, p.security.ticker))


def holdings_values(db: Session, as_of: dt.date | None = None) -> dict[int, int]:
    """{account_id: market value of its holdings} for accounts that hold anything."""
    result: dict[int, int] = defaultdict(int)
    for position in get_positions(db, as_of):
        result[position.account_id] += position.value_cents
    return dict(result)


def cash_from_trades(db: Session, as_of: dt.date | None = None) -> dict[int, int]:
    """{account_id: cash change from trades}. Buys spend cash; sells and dividends bring it in.

    Opening and contribution lots don't touch cash (see TradeKind).
    """
    result: dict[int, int] = defaultdict(int)
    for trade in get_trades(db, as_of):
        if trade.kind == TradeKind.BUY:
            result[trade.account_id] -= trade.amount_cents
        elif trade.kind in (TradeKind.SELL, TradeKind.DIVIDEND):
            result[trade.account_id] += trade.amount_cents
    return dict(result)
