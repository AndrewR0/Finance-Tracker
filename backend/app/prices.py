"""Market prices: where they come from (a PriceProvider) and keeping the Price table fresh.

PriceProvider is the "swappable" part of the plan: the app only ever asks for closing prices
by ticker and date. Today that's yfinance; tests use a fake; another source could replace it
without touching anything else.
"""

import datetime as dt
import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PRICE_UNITS, Price, PriceSource, Security, Trade

log = logging.getLogger(__name__)

QUOTE_STEP = Decimal("0.0001")
# The first market price for a security must be within this of the value you entered at
# setup. Further off almost always means the ticker names a different fund (a 401k trust
# vs the public fund, another share class), and using it would quietly change your balance.
MAX_SETUP_DIFFERENCE = Decimal("0.05")


class PriceProvider(Protocol):
    def closes(self, ticker: str, start: dt.date, end: dt.date) -> dict[dt.date, Decimal]:
        """Closing price (dollars per share) for each trading day from start to end, inclusive.

        Returns {} when there's nothing (a weekend, or a ticker it doesn't know).
        Raises on network or source errors.
        """
        ...


class YFinanceProvider:
    """Closing prices from Yahoo Finance through the yfinance library.

    yfinance is unofficial (it reads Yahoo's website data), so it can break or be rate-limited.
    That's fine here: prices are cached in the Price table, and the app keeps using the last
    one it has.
    """

    def closes(self, ticker: str, start: dt.date, end: dt.date) -> dict[dt.date, Decimal]:
        import yfinance  # imported here so tests and the rest of the app never load it

        # auto_adjust=False: the actual closing price, which is what your shares are worth.
        # (The S&P comparison in step 4 will want dividend-adjusted prices instead.)
        history = yfinance.Ticker(ticker).history(start=start, end=end + dt.timedelta(days=1), auto_adjust=False)
        # The library hands back floats with noise in the last digits (118.68000030517578).
        # Prices are quoted to at most 4 decimals, so rounding there gives back the real quote.
        # `close == close` skips NaN (a day with no close), since NaN never equals itself.
        return {stamp.date(): Decimal(repr(float(close))).quantize(QUOTE_STEP, rounding=ROUND_HALF_UP)
                for stamp, close in history["Close"].items() if close == close}


def to_price_units(dollars: Decimal) -> int:
    """Decimal dollars -> whole millionths of a dollar, rounding half up."""
    return int((dollars * PRICE_UNITS).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class RefreshResult:
    refreshed_at: dt.datetime | None = None
    updated: int = 0  # price rows added or changed
    failed: dict[str, str] = field(default_factory=dict)  # ticker -> what went wrong


# The latest refresh, kept in memory for the Investments page. Lost on restart, which is fine:
# a refresh runs at startup.
last_refresh = RefreshResult()


def refresh_prices(db: Session, provider: PriceProvider, today: dt.date) -> RefreshResult:
    """Fetch closing prices for every held security with a public ticker, up to today.

    Each security is fetched from a few days before its newest automatic price (or a week before
    its first trade, the first time). A market price replaces a typed-in price for the same day.
    """
    global last_refresh
    result = RefreshResult(refreshed_at=dt.datetime.now())

    first_trade = dict(db.execute(select(Trade.security_id, func.min(Trade.date)).group_by(Trade.security_id)).all())
    newest_auto = dict(db.execute(
        select(Price.security_id, func.max(Price.date)).where(Price.source == PriceSource.YFINANCE).group_by(Price.security_id)
    ).all())
    securities = db.scalars(select(Security).where(Security.price_source == PriceSource.YFINANCE,
                                                   Security.id.in_(first_trade))).all()

    for security in securities:
        newest = newest_auto.get(security.id)
        if newest is None:
            # A week before the first trade, so a holding set up on a holiday or weekend still
            # has a market price from the last trading day before it.
            start = first_trade[security.id] - dt.timedelta(days=7)
        else:
            # A few days back: a close can be corrected the next day, and long weekends happen.
            start = newest - dt.timedelta(days=4)
        try:
            closes = provider.closes(security.ticker, start, today)
        except Exception as error:  # network trouble, Yahoo changes: report it and move on
            log.warning("price refresh failed for %s: %s", security.ticker, error)
            result.failed[security.ticker] = str(error)[:200] or type(error).__name__
            continue
        if not closes:
            result.failed[security.ticker] = "No prices found. Is the ticker right? (Yahoo uses BTC-USD for bitcoin.)"
            continue
        if newest is None and (problem := setup_mismatch(db, security, first_trade[security.id], closes)):
            result.failed[security.ticker] = problem
            continue
        existing = {p.date: p for p in db.scalars(select(Price).where(Price.security_id == security.id,
                                                                       Price.date.in_(closes)))}
        for day, dollars in closes.items():
            if day > today:
                continue
            price = to_price_units(dollars)
            row = existing.get(day)
            if row is None:
                db.add(Price(security_id=security.id, date=day, price=price, source=PriceSource.YFINANCE))
                result.updated += 1
            elif row.price != price or row.source != PriceSource.YFINANCE:
                row.price, row.source = price, PriceSource.YFINANCE
                result.updated += 1
    db.commit()
    last_refresh = result
    return result


def setup_mismatch(db: Session, security: Security, setup_day: dt.date, closes: dict[dt.date, Decimal]) -> str | None:
    """Compare the market close nearest the setup day with the price you entered then.

    Returns a message when they're too far apart, or None when they agree (or can't be compared).
    """
    entered = db.scalar(select(Price.price).where(Price.security_id == security.id, Price.date == setup_day,
                                                  Price.source == PriceSource.MANUAL))
    on_or_before = [day for day in closes if day <= setup_day]
    if not entered or not on_or_before:
        return None
    day = max(on_or_before)
    market = closes[day]
    yours = Decimal(entered) / PRICE_UNITS
    difference = abs(market - yours) / yours
    if difference <= MAX_SETUP_DIFFERENCE:
        return None
    return (f"Yahoo's price for {security.ticker} (${market:,.2f} on {day:%b} {day.day}) is {difference:.0%} off the "
            f"value you entered (${yours:,.2f} a share), so it wasn't used. The ticker may name a different "
            "fund: switch it to manual prices, or undo the setup and fix the ticker.")


def get_price_provider() -> PriceProvider:
    """FastAPI dependency, so tests can swap in a fake provider."""
    return YFinanceProvider()
