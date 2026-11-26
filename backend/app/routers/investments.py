"""Investments endpoints: holdings per account, setting them up, and manual prices."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import benchmark, prices
from app.balances import get_cash
from app.clock import Today
from app.db import get_db
from app.holdings import SETUP_NOTE, Position, get_positions, get_trades, price_from_value, run_fifo
from app.models import (
    PRICE_UNITS,
    SHARE_UNITS,
    Account,
    AccountType,
    Price,
    PriceSource,
    Security,
    Trade,
    TradeKind,
    Transaction,
)
from app.schemas import (
    AccountHoldings,
    Comparison,
    HoldingRead,
    HoldingsSetup,
    PriceInput,
    PriceRead,
    PriceStatus,
    SecurityUpdate,
    TradeCreate,
    TradeRead,
)

router = APIRouter(prefix="/api", tags=["investments"])

DbSession = Annotated[Session, Depends(get_db)]

INVESTMENT_TYPES = (AccountType.BROKERAGE, AccountType.RETIREMENT)


def holding_read(position: Position) -> HoldingRead:
    security = position.security
    return HoldingRead(
        security_id=security.id,
        ticker=security.ticker,
        name=security.name,
        kind=security.kind,
        price_source=security.price_source,
        shares=position.shares,
        cost_basis_cents=position.cost_cents,
        price=position.price,
        price_date=position.price_date,
        value_cents=position.value_cents,
        gain_cents=position.value_cents - position.cost_cents,
        realized_cents=position.realized_cents,
        dividends_cents=position.dividends_cents,
    )


def account_holdings(db: Session, accounts: list[Account]) -> list[AccountHoldings]:
    """Holdings for the given accounts; accounts with no trades are left out."""
    positions = get_positions(db)
    cash = get_cash(db)
    trade_kinds: dict[int, set[TradeKind]] = {}
    for account_id, kind in db.execute(select(Trade.account_id, Trade.kind).distinct()):
        trade_kinds.setdefault(account_id, set()).add(kind)

    result = []
    for account in accounts:
        if account.id not in trade_kinds:
            continue
        mine = [p for p in positions if p.account_id == account.id]
        held = [holding_read(p) for p in mine if p.shares > 0]
        account_cash = cash.get(account.id, 0)
        holdings_value = sum(h.value_cents for h in held)
        cost = sum(h.cost_basis_cents for h in held)
        result.append(AccountHoldings(
            account_id=account.id,
            account_name=account.name,
            in_net_worth=account.in_net_worth,
            cash_cents=account_cash,
            value_cents=account_cash + holdings_value,
            cost_basis_cents=cost,
            gain_cents=holdings_value - cost,
            realized_cents=sum(p.realized_cents for p in mine),
            dividends_cents=sum(p.dividends_cents for p in mine),
            can_undo=trade_kinds[account.id] == {TradeKind.OPENING},
            holdings=held,
        ))
    return result


def get_investment_account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} does not exist.")
    if account.type not in INVESTMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"{account.name} isn't a Brokerage or Retirement account.")
    return account


@router.get("/holdings", response_model=list[AccountHoldings])
def list_holdings(db: DbSession):
    """Every investment account that has holdings, biggest holding first within each."""
    accounts = db.scalars(
        select(Account).where(Account.type.in_(INVESTMENT_TYPES)).order_by(Account.closed_at.is_not(None), Account.name)
    ).all()
    return account_holdings(db, list(accounts))


@router.post("/accounts/{account_id}/holdings", response_model=AccountHoldings, status_code=status.HTTP_201_CREATED)
def set_up_holdings(account_id: int, payload: HoldingsSetup, db: DbSession):
    """Start tracking an account's holdings from your provider's cost basis page.

    Each holding becomes an opening lot dated `date`, and its market value sets the first price.
    One balance adjustment then brings the account's cash to `cash_cents`, so the money that
    past balance updates already counted isn't counted again by the holdings. Nothing in
    the account's history is changed.
    """
    account = get_investment_account(db, account_id)
    if account.closed_at is not None:
        raise HTTPException(status_code=409, detail=f"{account.name} is closed. Reopen it first.")
    if db.scalar(select(Trade.id).where(Trade.account_id == account.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail=f"{account.name}'s holdings are already set up. Undo that first.")
    tickers = [h.ticker for h in payload.holdings]
    if len(set(tickers)) != len(tickers):
        raise HTTPException(status_code=422, detail="Each ticker can only be listed once.")

    for holding in payload.holdings:
        security = db.scalar(select(Security).where(Security.ticker == holding.ticker))
        if security is None:
            security = Security(ticker=holding.ticker, name=holding.name, kind=holding.kind,
                                price_source=holding.price_source)
            db.add(security)
            db.flush()  # gives it an id
        shares = int(holding.shares * SHARE_UNITS)  # exact: at most 8 decimal places
        db.add(Trade(account_id=account.id, security_id=security.id, date=payload.date, kind=TradeKind.OPENING,
                     shares=shares, amount_cents=holding.cost_basis_cents))
        set_price(db, security.id, payload.date, price_from_value(shares, holding.market_value_cents), PriceSource.MANUAL)

    # Before this setup, the account's cash was all of its value. Now cash is what you said.
    difference = payload.cash_cents - get_cash(db, payload.date).get(account.id, 0)
    if difference != 0:
        db.add(Transaction(account_id=account.id, date=payload.date, amount_cents=difference,
                           notes=SETUP_NOTE, is_adjustment=True))
    db.commit()
    return account_holdings(db, [account])[0]


@router.delete("/accounts/{account_id}/holdings", status_code=status.HTTP_204_NO_CONTENT)
def undo_holdings_setup(account_id: int, db: DbSession):
    """Remove the opening lots and the setup's balance adjustment, so you can set it up again."""
    account = get_investment_account(db, account_id)
    trades = db.scalars(select(Trade).where(Trade.account_id == account.id)).all()
    if not trades:
        raise HTTPException(status_code=404, detail=f"{account.name} has no holdings set up.")
    if any(t.kind != TradeKind.OPENING for t in trades):
        raise HTTPException(status_code=409, detail=f"{account.name} has buys or sells since its setup, so it can't be undone.")
    dates = {t.date for t in trades}
    db.execute(delete(Trade).where(Trade.account_id == account.id))
    db.execute(delete(Transaction).where(
        Transaction.account_id == account.id, Transaction.is_adjustment.is_(True),
        Transaction.notes == SETUP_NOTE, Transaction.date.in_(dates),
    ))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def set_price(db: Session, security_id: int, date, price: int, source: PriceSource) -> Price:
    """Save a price for that day, replacing one already there (a price is a fact, not history)."""
    row = db.scalar(select(Price).where(Price.security_id == security_id, Price.date == date))
    if row is None:
        row = Price(security_id=security_id, date=date, price=price, source=source)
        db.add(row)
    else:
        row.price, row.source = price, source
    return row


@router.post("/securities/{security_id}/prices", response_model=PriceRead)
def add_price(security_id: int, payload: PriceInput, db: DbSession):
    """Type in a price, for a security with no automatic prices (or to correct one)."""
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=404, detail=f"Security {security_id} does not exist.")
    row = set_price(db, security_id, payload.date, int(payload.price * PRICE_UNITS), PriceSource.MANUAL)
    db.commit()
    return row


Provider = Annotated[prices.PriceProvider, Depends(prices.get_price_provider)]


def price_status(db: Session) -> PriceStatus:
    latest = prices.last_refresh
    return PriceStatus(
        refreshed_at=latest.refreshed_at,
        updated=latest.updated,
        failed=latest.failed,
        prices_as_of=db.scalar(select(func.max(Price.date)).where(Price.source == PriceSource.YFINANCE)),
    )


@router.get("/prices/status", response_model=PriceStatus)
def get_price_status(db: DbSession):
    return price_status(db)


@router.post("/prices/refresh", response_model=PriceStatus)
def refresh_prices_now(db: DbSession, provider: Provider, today: Today):
    """Fetch the latest closing prices now (the app also does this by itself every few hours)."""
    prices.refresh_prices(db, provider, today)
    return price_status(db)


@router.patch("/securities/{security_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def update_security(security_id: int, payload: SecurityUpdate, db: DbSession):
    """Switch between automatic and typed-in prices, e.g. a 401k trust Yahoo doesn't know."""
    security = db.get(Security, security_id)
    if security is None:
        raise HTTPException(status_code=404, detail=f"Security {security_id} does not exist.")
    security.price_source = payload.price_source
    prices.last_refresh.failed.pop(security.ticker, None)  # its warning no longer applies
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- Trades going forward ----

def trade_read(trade: Trade) -> TradeRead:
    return TradeRead(id=trade.id, date=trade.date, kind=trade.kind, security_id=trade.security_id,
                     ticker=trade.security.ticker, shares=trade.shares, amount_cents=trade.amount_cents)


@router.get("/accounts/{account_id}/trades", response_model=list[TradeRead])
def list_trades(account_id: int, db: DbSession):
    """An account's trades, newest first."""
    account = get_investment_account(db, account_id)
    trades = get_trades(db, account_id=account.id)
    return [trade_read(t) for t in sorted(trades, key=lambda t: (t.date, t.id), reverse=True)]


def check_not_oversold(db: Session, account: Account) -> None:
    """Raise 422 (after the caller's changes are flushed) if any sell is for more shares than were held."""
    db.flush()
    fifo = run_fifo(get_trades(db, account_id=account.id))
    if fifo.oversold:
        sell = db.get(Trade, fifo.oversold[0])
        raise HTTPException(
            status_code=422,
            detail=f"That leaves the {sell.security.ticker} sell on {sell.date} selling more shares than "
                   f"{account.name} held then.",
        )


def resolve_security(db: Session, payload: TradeCreate) -> Security:
    if (payload.security_id is None) == (payload.new_security is None):
        raise HTTPException(status_code=422, detail="Give either security_id or new_security.")
    if payload.security_id is not None:
        security = db.get(Security, payload.security_id)
        if security is None:
            raise HTTPException(status_code=404, detail=f"Security {payload.security_id} does not exist.")
        return security
    new = payload.new_security
    existing = db.scalar(select(Security).where(Security.ticker == new.ticker))
    if existing is not None:
        return existing  # already known (maybe held in another account): reuse it
    security = Security(ticker=new.ticker, name=new.name, kind=new.kind, price_source=new.price_source)
    db.add(security)
    db.flush()
    return security


@router.post("/accounts/{account_id}/trades", response_model=list[TradeRead], status_code=status.HTTP_201_CREATED)
def add_trade(account_id: int, payload: TradeCreate, db: DbSession):
    """Record a buy, sell, dividend or contribution. Returns what was added (a reinvested
    dividend adds two trades: the dividend and the buy it paid for)."""
    account = get_investment_account(db, account_id)
    if account.closed_at is not None:
        raise HTTPException(status_code=409, detail=f"{account.name} is closed. Reopen it first.")
    if payload.kind == TradeKind.OPENING:
        raise HTTPException(status_code=422, detail="Opening lots come from setting up holdings.")
    if payload.kind == TradeKind.DIVIDEND:
        if payload.shares is not None:
            raise HTTPException(status_code=422, detail="A dividend has no shares; use reinvested_shares if it bought some.")
    else:
        if payload.shares is None:
            raise HTTPException(status_code=422, detail=f"A {payload.kind} needs shares.")
        if payload.reinvested_shares is not None:
            raise HTTPException(status_code=422, detail="reinvested_shares is only for dividends.")
    security = resolve_security(db, payload)

    def add(kind: TradeKind, shares, amount: int) -> Trade:
        units = 0 if shares is None else int(shares * SHARE_UNITS)
        trade = Trade(account_id=account.id, security_id=security.id, date=payload.date, kind=kind,
                      shares=units, amount_cents=amount)
        db.add(trade)
        # A security with typed-in prices learns one from the trade, if it has none that day.
        if units and security.price_source == PriceSource.MANUAL:
            if db.scalar(select(Price.id).where(Price.security_id == security.id, Price.date == payload.date)) is None:
                set_price(db, security.id, payload.date, price_from_value(units, amount), PriceSource.MANUAL)
        return trade

    added = [add(payload.kind, payload.shares, payload.amount_cents)]
    if payload.reinvested_shares is not None:
        added.append(add(TradeKind.BUY, payload.reinvested_shares, payload.amount_cents))
    check_not_oversold(db, account)
    db.commit()
    return [trade_read(t) for t in added]


@router.delete("/trades/{trade_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_trade(trade_id: int, db: DbSession):
    """Delete a trade entered by mistake (re-add it to change it). Opening lots: undo the setup."""
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} does not exist.")
    if trade.kind == TradeKind.OPENING:
        raise HTTPException(status_code=409, detail="That's an opening lot. Undo the account's setup to change it.")
    account = db.get(Account, trade.account_id)
    db.delete(trade)
    check_not_oversold(db, account)  # deleting a buy can leave a later sell short
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/investments/comparison", response_model=Comparison)
def compare_with_sp500(db: DbSession, today: Today, account_id: int | None = None):
    """Your investments vs the same deposits put into the S&P 500 on the same days.

    ?account_id=7 for one account; leave it out for every Brokerage and Retirement account.
    """
    if account_id is None:
        account_ids = benchmark.investment_account_ids(db)
    else:
        account_ids = [get_investment_account(db, account_id).id]
    return benchmark.compare(db, account_ids, today)
