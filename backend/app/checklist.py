"""The month-end checklist. Derived from your data every time, never stored: an item is done
when the data shows it's done (a price dated this month, a reconcile this month, and so on).

Items:
- reconcile: every open checking, savings, cash and credit card account, once a month.
- update_price: every held security with typed-in prices, once a month.
- contribution: 401k-style accounts (Retirement accounts with holdings that never receive
  transfers, so payroll money is the only way in), once a month.
- invest_cash: an investment account with holdings and uninvested cash sitting in it, like
  Strike's weekly transfers before the month's buy. Only listed while there's cash to invest.
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.balances import get_cash
from app.holdings import get_positions
from app.models import Account, AccountType, PriceSource, Trade, TradeKind, Transaction

RECONCILED_TYPES = (AccountType.CHECKING, AccountType.SAVINGS, AccountType.CASH, AccountType.CREDIT_CARD)
INVESTMENT_TYPES = (AccountType.BROKERAGE, AccountType.RETIREMENT)
# Less uninvested cash than this isn't worth a reminder (leftover cents after a buy).
CASH_THRESHOLD_CENTS = 1000


@dataclass
class Item:
    key: str  # stable id, like "reconcile:5"
    kind: str  # reconcile | update_price | contribution | invest_cash
    title: str
    detail: str
    done: bool
    link: str  # where in the app to do it


def month_start(today: dt.date) -> dt.date:
    return today.replace(day=1)


def checklist(db: Session, today: dt.date) -> list[Item]:
    start = month_start(today)
    accounts = db.scalars(select(Account).where(Account.closed_at.is_(None)).order_by(Account.name)).all()
    items: list[Item] = []

    for account in accounts:
        if account.type in RECONCILED_TYPES:
            done = account.reconciled_on is not None and account.reconciled_on >= start
            last = f"last reconciled {account.reconciled_on:%b} {account.reconciled_on.day}" if account.reconciled_on else "never reconciled"
            items.append(Item(f"reconcile:{account.id}", "reconcile", f"Reconcile {account.name}",
                              "Done for this month" if done else f"Match it to your statement ({last})", done, "/accounts"))

    positions = [p for p in get_positions(db, today) if p.shares > 0]
    held_accounts = {p.account_id for p in positions}
    names = {a.id: a.name for a in accounts}

    seen: set[int] = set()
    for p in positions:
        security = p.security
        if security.price_source != PriceSource.MANUAL or security.id in seen:
            continue
        seen.add(security.id)
        done = p.price_date is not None and p.price_date >= start
        when = f"last price {p.price_date:%b} {p.price_date.day}" if p.price_date else "no price yet"
        items.append(Item(f"price:{security.id}", "update_price", f"Update {security.ticker}'s price",
                          "Done for this month" if done else f"{security.name}, in {names.get(p.account_id, 'an account')} ({when})",
                          done, "/investments"))

    with_transfers = set(db.scalars(select(Transaction.account_id).where(Transaction.transfer_id.is_not(None)).distinct()))
    contributed = set(db.scalars(select(Trade.account_id).where(
        Trade.kind == TradeKind.CONTRIBUTION, Trade.date >= start, Trade.date <= today).distinct()))
    for account in accounts:
        if account.type == AccountType.RETIREMENT and account.id in held_accounts and account.id not in with_transfers:
            done = account.id in contributed
            items.append(Item(f"contribution:{account.id}", "contribution", f"Record {account.name}'s contributions",
                              "Done for this month" if done else "Add this month's payroll contribution per fund, from your statement",
                              done, "/investments"))

    cash = get_cash(db, today)
    for account in accounts:
        if account.type in INVESTMENT_TYPES and account.id in held_accounts and cash.get(account.id, 0) >= CASH_THRESHOLD_CENTS:
            dollars = cash[account.id]
            items.append(Item(f"invest:{account.id}", "invest_cash", f"Record the buy in {account.name}",
                              f"${dollars // 100:,}.{dollars % 100:02d} is sitting as cash. Add the Buy, or leave it if it's meant to be cash.",
                              False, "/investments"))

    return items
