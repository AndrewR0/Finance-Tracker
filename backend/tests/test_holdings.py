"""Investments step 1: setting up holdings from a provider's cost basis page."""

import datetime as dt

from app.holdings import divide_round, price_from_value, run_fifo, value_cents
from app.models import SHARE_UNITS, Trade, TradeKind

TODAY = "2026-11-26"


def create(client, name, type):
    response = client.post("/api/accounts", json={"name": name, "type": type})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def update_balance(client, account_id, balance_cents, date):
    response = client.post(f"/api/accounts/{account_id}/reconcile", json={"date": date, "balance_cents": balance_cents})
    assert response.status_code == 200, response.json()


def transfer(client, from_id, to_id, amount_cents, date):
    response = client.post("/api/transfers", json={
        "from_account_id": from_id, "to_account_id": to_id, "date": date, "amount_cents": amount_cents,
    })
    assert response.status_code == 201, response.json()


def holding(ticker="VTSAX", shares="100", cost=1000000, value=1200000, **extra):
    return {"ticker": ticker, "name": f"{ticker} fund", "kind": "fund", "shares": shares,
            "cost_basis_cents": cost, "market_value_cents": value, **extra}


def set_up(client, account_id, holdings, cash_cents=0, date=TODAY):
    return client.post(f"/api/accounts/{account_id}/holdings",
                       json={"date": date, "cash_cents": cash_cents, "holdings": holdings})


def accounts(client, **params):
    return {a["name"]: a for a in client.get("/api/accounts", params=params).json()}


def net_worth(client, date=TODAY):
    return client.get("/api/dashboard/summary", params={"start": date, "end": date}).json()["net_worth_cents"]


# ---- integer math ----

def test_value_and_price_round_trip_without_floats():
    shares = 3841207  # 0.03841207 BTC
    price = price_from_value(shares, 250000)  # worth $2,500.00
    assert value_cents(shares, price) == 250000
    assert value_cents(SHARE_UNITS, 123_456_700) == 12346  # 1 share at $123.4567 -> $123.46


def test_divide_round_rounds_halves_away_from_zero():
    assert (divide_round(5, 2), divide_round(-5, 2), divide_round(4, 3)) == (3, -3, 1)


# ---- FIFO ----

def trade(id, kind, shares, amount, day):
    return Trade(id=id, account_id=1, security_id=1, date=dt.date(2026, 1, day), kind=kind,
                 shares=shares * SHARE_UNITS, amount_cents=amount)


def test_a_sell_uses_the_oldest_lot_first():
    fifo = run_fifo([
        trade(1, TradeKind.OPENING, 10, 100000, 1),  # $100/share
        trade(2, TradeKind.BUY, 10, 150000, 2),  # $150/share
        trade(3, TradeKind.SELL, 15, 240000, 3),  # $160/share: all of lot 1 + half of lot 2
    ])

    assert [(lot.trade_id, lot.shares // SHARE_UNITS, lot.cost_cents) for lot in fifo.lots] == [(2, 5, 75000)]
    assert fifo.realized == {(1, 1): 240000 - 100000 - 75000}
    assert fifo.oversold == []


def test_selling_more_than_held_is_flagged():
    fifo = run_fifo([trade(1, TradeKind.BUY, 10, 100000, 1), trade(2, TradeKind.SELL, 11, 120000, 2)])

    assert fifo.oversold == [2]


# ---- setting up an account ----

def test_setup_keeps_the_account_value_and_net_worth_the_same(client):
    brokerage = create(client, "Vanguard Brokerage", "brokerage")
    update_balance(client, brokerage, 5000000, "2026-11-20")  # what past balance updates said
    before = net_worth(client)

    response = set_up(client, brokerage, [
        holding("VTSAX", "300.5", cost=3500000, value=4900000),
        holding("VMFXX", "1000", cost=100000, value=100000),  # settlement fund at $1
    ])

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["value_cents"] == 5000000
    assert body["cost_basis_cents"] == 3600000
    assert body["gain_cents"] == 1400000
    assert body["cash_cents"] == 0
    assert [h["ticker"] for h in body["holdings"]] == ["VTSAX", "VMFXX"]  # biggest first
    assert net_worth(client) == before
    assert accounts(client)["Vanguard Brokerage"]["balance_cents"] == 5000000


def test_accounts_page_switches_to_cost_basis_from_lots(client):
    roth = create(client, "Roth IRA", "retirement")
    set_up(client, roth, [holding("VTI", "50", cost=1800000, value=2000000)])

    investment = accounts(client)["Roth IRA"]["investment"]

    assert investment["cost_basis_cents"] == 1800000
    assert investment["unrealized_gain_cents"] == 200000


def test_contributions_from_transfers_are_kept_beside_the_lots(client):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    transfer(client, checking, roth, 1500000, "2025-06-30")  # what you can withdraw anytime
    set_up(client, roth, [holding("VTI", "50", cost=1700000, value=2000000)])

    assert accounts(client)["Roth IRA"]["investment"]["contributed_cents"] == 1500000


def test_uninvested_cash_is_kept(client):
    strike = create(client, "Strike", "brokerage")
    update_balance(client, strike, 360000, "2026-11-20")

    body = set_up(client, strike, [holding("BTC-USD", "0.03841207", cost=400000, value=250000)], cash_cents=110000).json()

    assert body["cash_cents"] == 110000
    assert body["value_cents"] == 360000
    assert body["holdings"][0]["shares"] == 3841207


def test_a_market_value_of_zero_is_a_price_of_zero(client):
    k401 = create(client, "401k", "retirement")

    body = set_up(client, k401, [holding("TGT2055", "10", cost=100000, value=0, price_source="manual")]).json()

    assert body["holdings"][0]["price"] == 0
    assert body["holdings"][0]["value_cents"] == 0


def test_manual_price_updates_the_value(client):
    k401 = create(client, "401k", "retirement")
    body = set_up(client, k401, [holding("TGT2055", "10", cost=100000, value=120000, price_source="manual")]).json()
    security_id = body["holdings"][0]["security_id"]

    response = client.post(f"/api/securities/{security_id}/prices", json={"date": "2026-11-30", "price": "130.5"})

    assert response.status_code == 200, response.json()
    assert response.json()["price"] == 130_500_000
    assert accounts(client)["401k"]["balance_cents"] == 130500
    assert accounts(client, as_of=TODAY)["401k"]["balance_cents"] == 120000  # the older price still applies then


def test_setup_twice_is_refused(client):
    roth = create(client, "Roth IRA", "retirement")
    set_up(client, roth, [holding()])

    assert set_up(client, roth, [holding()]).status_code == 409


def test_only_investment_accounts(client):
    checking = create(client, "Checking", "checking")

    assert set_up(client, checking, [holding()]).status_code == 422


def test_each_ticker_once(client):
    roth = create(client, "Roth IRA", "retirement")

    assert set_up(client, roth, [holding("VTI"), holding("vti")]).status_code == 422


def test_more_than_8_decimal_places_is_refused(client):
    roth = create(client, "Roth IRA", "retirement")

    assert set_up(client, roth, [holding(shares="0.123456789")]).status_code == 422


def test_undo_restores_the_account_as_it_was(client):
    roth = create(client, "Roth IRA", "retirement")
    update_balance(client, roth, 2000000, "2026-11-20")
    set_up(client, roth, [holding("VTI", "50", cost=1800000, value=1900000)])  # a typo in the value

    assert client.delete(f"/api/accounts/{roth}/holdings").status_code == 204

    assert accounts(client)["Roth IRA"]["balance_cents"] == 2000000
    assert client.get("/api/holdings").json() == []
    assert set_up(client, roth, [holding("VTI", "50", cost=1800000, value=2000000)]).status_code == 201


def test_list_holdings_shows_only_accounts_with_holdings(client):
    roth = create(client, "Roth IRA", "retirement")
    create(client, "Strike", "brokerage")
    set_up(client, roth, [holding()])

    rows = client.get("/api/holdings").json()

    assert [r["account_name"] for r in rows] == ["Roth IRA"]
    assert rows[0]["can_undo"] is True
