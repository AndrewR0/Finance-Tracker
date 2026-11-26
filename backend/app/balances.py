"""Account balances, derived from transactions. Never stored.

This lives outside the routers so other features (the dashboard's net worth,
reconciling) can reuse it without going through HTTP.
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.holdings import cash_from_trades, holdings_values
from app.models import Transaction


def get_balances(db: Session, as_of: dt.date | None = None) -> dict[int, int]:
    """Return {account_id: balance_cents} for every account that has transactions.

    as_of: count only transactions on or before this date. None means all of them.
    Accounts with no transactions are simply missing from the dict; callers treat
    missing as 0.
    """
    query = (
        select(Transaction.account_id, func.sum(Transaction.amount_cents))
        .group_by(Transaction.account_id)
    )
    if as_of is not None:
        query = query.where(Transaction.date <= as_of)

    rows = db.execute(query)
    return {account_id: total for account_id, total in rows}


# Balance updates this many days from an account's first entry still count as its opening
# balance: setting an account up often takes a correction or two.
SETUP_DAYS = 7


@dataclass
class InvestmentBreakdown:
    """Where an investment account's balance came from. The three parts add up to the balance.

    starting_cents:    balance adjustments in the account's first week (SETUP_DAYS), before any
                       transfer: its opening snapshot, plus corrections made while setting it up.
                       The app can't tell deposits from gains in it, so it counts as money you
                       put in.
    contributed_cents: transfers in minus transfers out: your contribution basis.
    gain_cents:        everything else: later balance updates (market moves), dividends, fees.
                       For a snapshot-only account (a 401k), payroll contributions land here
                       too, since they never show up as transfers.
    """

    starting_cents: int = 0
    contributed_cents: int = 0
    gain_cents: int = 0


def get_investment_breakdowns(
    db: Session, account_ids: list[int], as_of: dt.date | None = None
) -> dict[int, InvestmentBreakdown]:
    """{account_id: InvestmentBreakdown} for the given accounts (every one gets an entry)."""
    result = {account_id: InvestmentBreakdown() for account_id in account_ids}
    if not account_ids:
        return result
    query = (
        select(Transaction.account_id, Transaction.date, Transaction.amount_cents, Transaction.is_adjustment,
               Transaction.transfer_id)
        .where(Transaction.account_id.in_(account_ids))
        .order_by(Transaction.date, Transaction.id)  # oldest first, so the first row is the first day
    )
    if as_of is not None:
        query = query.where(Transaction.date <= as_of)

    first_day: dict[int, dt.date] = {}
    had_transfer: set[int] = set()
    for account_id, date, cents, is_adjustment, transfer_id in db.execute(query):
        parts = result[account_id]
        first_day.setdefault(account_id, date)
        in_setup = (date - first_day[account_id]).days < SETUP_DAYS and account_id not in had_transfer
        if transfer_id is not None:
            parts.contributed_cents += cents
            had_transfer.add(account_id)
        elif is_adjustment and in_setup:
            parts.starting_cents += cents
        else:
            parts.gain_cents += cents
    return result


def get_cash(db: Session, as_of: dt.date | None = None) -> dict[int, int]:
    """{account_id: cash}: transactions, minus money spent on buys, plus money from sells.

    For an account without trades this is just get_balances().
    """
    result = dict(get_balances(db, as_of))
    for account_id, cents in cash_from_trades(db, as_of).items():
        result[account_id] = result.get(account_id, 0) + cents
    return result


def get_account_values(db: Session, as_of: dt.date | None = None) -> dict[int, int]:
    """{account_id: what it's worth}: cash plus the market value of its holdings.

    This is "the balance" everywhere the app shows or adds one up (net worth, Accounts, goals).
    """
    result = get_cash(db, as_of)
    for account_id, cents in holdings_values(db, as_of).items():
        result[account_id] = result.get(account_id, 0) + cents
    return result
