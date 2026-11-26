"""Investments step 3: buys, sells, dividends and contributions after setup. Made-up numbers only."""

import pytest

SETUP_DAY = "2026-10-01"


def create(client, name, type):
    response = client.post("/api/accounts", json={"name": name, "type": type})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def transfer(client, from_id, to_id, amount_cents, date):
    response = client.post("/api/transfers", json={
        "from_account_id": from_id, "to_account_id": to_id, "date": date, "amount_cents": amount_cents,
    })
    assert response.status_code == 201, response.json()


@pytest.fixture
def brokerage(client):
    """A brokerage set up with 10 shares of FUNDA (cost $1,000, worth $1,200) and no cash."""
    account = create(client, "Brokerage", "brokerage")
    response = client.post(f"/api/accounts/{account}/holdings", json={"date": SETUP_DAY, "holdings": [
        {"ticker": "FUNDA", "name": "Fund A", "kind": "fund", "price_source": "manual",
         "shares": "10", "cost_basis_cents": 100000, "market_value_cents": 120000},
    ]})
    assert response.status_code == 201, response.json()
    return account


def security_id(client, ticker):
    return next(h["security_id"] for a in client.get("/api/holdings").json() for h in a["holdings"] if h["ticker"] == ticker)


def trade(client, account, **body):
    return client.post(f"/api/accounts/{account}/trades", json=body)


def account_holdings(client, account):
    return next(a for a in client.get("/api/holdings").json() if a["account_id"] == account)


def test_transfer_then_buy_moves_cash_into_shares(client, brokerage):
    checking = create(client, "Checking", "checking")
    transfer(client, checking, brokerage, 50000, "2026-10-05")

    response = trade(client, brokerage, date="2026-10-05", kind="buy", security_id=security_id(client, "FUNDA"),
                     shares="4", amount_cents=50000)

    assert response.status_code == 201, response.json()
    body = account_holdings(client, brokerage)
    assert body["cash_cents"] == 0  # the transfer's cash went into shares
    funda = body["holdings"][0]
    assert funda["shares"] == 14 * 100_000_000
    assert funda["cost_basis_cents"] == 150000


def test_first_buy_of_a_new_security(client, brokerage):
    checking = create(client, "Checking", "checking")
    transfer(client, checking, brokerage, 20000, "2026-11-30")

    response = trade(client, brokerage, date="2026-11-30", kind="buy", shares="0.00333333", amount_cents=20000,
                     new_security={"ticker": "COINX", "name": "A coin", "kind": "crypto", "price_source": "manual"})

    assert response.status_code == 201, response.json()
    tickers = [h["ticker"] for h in account_holdings(client, brokerage)["holdings"]]
    assert "COINX" in tickers


def test_sell_realizes_a_fifo_gain_and_adds_cash(client, brokerage):
    fund = security_id(client, "FUNDA")
    trade(client, brokerage, date="2026-10-10", kind="buy", security_id=fund, shares="10", amount_cents=150000)

    response = trade(client, brokerage, date="2026-10-20", kind="sell", security_id=fund, shares="15", amount_cents=240000)

    assert response.status_code == 201, response.json()
    body = account_holdings(client, brokerage)
    # FIFO: all 10 opening shares ($1,000) + 5 of the bought ones ($750) were sold for $2,400.
    assert body["realized_cents"] == 240000 - 100000 - 75000
    assert body["holdings"][0]["shares"] == 5 * 100_000_000
    assert body["holdings"][0]["cost_basis_cents"] == 75000
    assert body["cash_cents"] == 240000 - 150000  # sell proceeds minus the buy


def test_selling_more_than_held_is_refused(client, brokerage):
    response = trade(client, brokerage, date="2026-10-20", kind="sell", security_id=security_id(client, "FUNDA"),
                     shares="11", amount_cents=130000)

    assert response.status_code == 422
    assert "more shares" in response.json()["detail"]
    assert account_holdings(client, brokerage)["holdings"][0]["shares"] == 10 * 100_000_000  # nothing saved


def test_a_sell_before_the_shares_were_bought_is_refused(client, brokerage):
    fund = security_id(client, "FUNDA")
    trade(client, brokerage, date="2026-10-30", kind="buy", security_id=fund, shares="5", amount_cents=60000)

    response = trade(client, brokerage, date="2026-10-15", kind="sell", security_id=fund, shares="12", amount_cents=150000)

    assert response.status_code == 422


def test_reinvested_dividend_adds_shares_but_not_income(client, brokerage):
    response = trade(client, brokerage, date="2026-10-31", kind="dividend", security_id=security_id(client, "FUNDA"),
                     amount_cents=1200, reinvested_shares="0.1")

    assert response.status_code == 201, response.json()
    assert [t["kind"] for t in response.json()] == ["dividend", "buy"]
    body = account_holdings(client, brokerage)
    assert body["dividends_cents"] == 1200
    assert body["cash_cents"] == 0  # paid in, then spent on the new shares
    assert body["holdings"][0]["shares"] == 10_10_000_000
    summary = client.get("/api/dashboard/summary", params={"start": "2026-10-01", "end": "2026-10-31"}).json()
    assert summary["income_cents"] == 0


def test_cash_dividend_stays_as_cash(client, brokerage):
    trade(client, brokerage, date="2026-10-31", kind="dividend", security_id=security_id(client, "FUNDA"), amount_cents=1200)

    assert account_holdings(client, brokerage)["cash_cents"] == 1200


def test_401k_contribution_adds_shares_without_using_cash(client):
    k401 = create(client, "401k", "retirement")
    client.post(f"/api/accounts/{k401}/holdings", json={"date": SETUP_DAY, "holdings": [
        {"ticker": "TRUST1", "name": "A trust", "kind": "fund", "price_source": "manual",
         "shares": "100", "cost_basis_cents": 1000000, "market_value_cents": 1000000},
    ]})

    response = trade(client, k401, date="2026-10-31", kind="contribution", security_id=security_id(client, "TRUST1"),
                     shares="5", amount_cents=55000)

    assert response.status_code == 201, response.json()
    body = account_holdings(client, k401)
    assert body["cash_cents"] == 0
    assert body["cost_basis_cents"] == 1055000
    # A manual-price fund learns a price from the contribution: $550 / 5 shares = $110.
    assert body["holdings"][0]["price"] == 110_000_000
    assert body["value_cents"] == 105 * 11000


def test_delete_a_trade(client, brokerage):
    added = trade(client, brokerage, date="2026-10-10", kind="buy", security_id=security_id(client, "FUNDA"),
                  shares="1", amount_cents=12000).json()

    assert client.delete(f"/api/trades/{added[0]['id']}").status_code == 204
    assert account_holdings(client, brokerage)["holdings"][0]["shares"] == 10 * 100_000_000


def test_deleting_a_buy_a_later_sell_needs_is_refused(client, brokerage):
    fund = security_id(client, "FUNDA")
    buy = trade(client, brokerage, date="2026-10-10", kind="buy", security_id=fund, shares="5", amount_cents=60000).json()
    trade(client, brokerage, date="2026-10-20", kind="sell", security_id=fund, shares="12", amount_cents=150000)

    response = client.delete(f"/api/trades/{buy[0]['id']}")

    assert response.status_code == 422


def test_opening_lots_cant_be_deleted_one_by_one(client, brokerage):
    opening = client.get(f"/api/accounts/{brokerage}/trades").json()[0]

    assert opening["kind"] == "opening"
    assert client.delete(f"/api/trades/{opening['id']}").status_code == 409


def test_trades_list_newest_first(client, brokerage):
    fund = security_id(client, "FUNDA")
    trade(client, brokerage, date="2026-10-10", kind="buy", security_id=fund, shares="1", amount_cents=12000)
    trade(client, brokerage, date="2026-10-20", kind="buy", security_id=fund, shares="1", amount_cents=12500)

    dates = [t["date"] for t in client.get(f"/api/accounts/{brokerage}/trades").json()]

    assert dates == ["2026-10-20", "2026-10-10", SETUP_DAY]


def test_undo_setup_is_refused_once_there_are_trades(client, brokerage):
    trade(client, brokerage, date="2026-10-10", kind="buy", security_id=security_id(client, "FUNDA"), shares="1", amount_cents=12000)

    assert account_holdings(client, brokerage)["can_undo"] is False
    assert client.delete(f"/api/accounts/{brokerage}/holdings").status_code == 409


@pytest.mark.parametrize("body", [
    {"kind": "buy", "amount_cents": 100},  # no shares
    {"kind": "dividend", "shares": "1", "amount_cents": 100},  # a dividend has no shares
    {"kind": "buy", "shares": "1", "amount_cents": 100, "reinvested_shares": "1"},
    {"kind": "opening", "shares": "1", "amount_cents": 100},
    {"kind": "buy", "shares": "1", "amount_cents": 0},
])
def test_bad_trades_are_refused(client, brokerage, body):
    response = trade(client, brokerage, date="2026-10-10", security_id=security_id(client, "FUNDA"), **body)

    assert response.status_code == 422
