"""Investments step 4: you vs the same deposits in the S&P 500 (SPY). Made-up numbers only."""

import datetime as dt
from decimal import Decimal

import pytest

from app import prices
from app.benchmark import Day, Deposit, benchmark_values, weekly_dates
from app.main import app

D = dt.date


def day(d, close, dividend="0"):
    return Day(d, Decimal(close), Decimal(dividend))


# ---- the pretend SPY account ----

def test_deposits_buy_at_the_close_and_grow_with_the_price():
    days = [day(D(2026, 1, 2), "100"), day(D(2026, 1, 5), "110")]

    values = benchmark_values(days, [Deposit(1, D(2026, 1, 2), 100000)], [D(2026, 1, 2), D(2026, 1, 5)])

    assert values == {D(2026, 1, 2): 100000, D(2026, 1, 5): 110000}  # 10 shares, then +10%


def test_a_weekend_deposit_buys_at_the_next_trading_day():
    days = [day(D(2026, 1, 2), "100"), day(D(2026, 1, 5), "125")]  # Fri, Mon

    values = benchmark_values(days, [Deposit(1, D(2026, 1, 3), 100000)], [D(2026, 1, 3), D(2026, 1, 5)])

    assert values[D(2026, 1, 3)] == 100000  # waiting as cash over the weekend
    assert values[D(2026, 1, 5)] == 100000  # bought 8 shares at $125 on Monday


def test_dividends_are_reinvested():
    days = [day(D(2026, 1, 2), "100"), day(D(2026, 3, 20), "100", dividend="2")]

    values = benchmark_values(days, [Deposit(1, D(2026, 1, 2), 100000)], [D(2026, 3, 20)])

    assert values[D(2026, 3, 20)] == 102000  # 10 shares + 0.2 bought with the $20 dividend


def test_withdrawals_sell_pretend_shares():
    days = [day(D(2026, 1, 2), "100"), day(D(2026, 2, 2), "200")]
    deposits = [Deposit(1, D(2026, 1, 2), 100000), Deposit(1, D(2026, 2, 2), -100000)]

    values = benchmark_values(days, deposits, [D(2026, 2, 2)])

    assert values[D(2026, 2, 2)] == 100000  # $2,000 of SPY, minus the $1,000 taken out


def test_no_prices_yet_means_no_benchmark_value():
    assert benchmark_values([], [Deposit(1, D(2026, 1, 2), 100)], [D(2026, 1, 2)]) == {D(2026, 1, 2): None}


def test_weekly_dates_end_today():
    assert weekly_dates(D(2026, 1, 1), D(2026, 1, 20)) == [D(2026, 1, 1), D(2026, 1, 8), D(2026, 1, 15), D(2026, 1, 20)]


# ---- through the API ----

class FakeProvider:
    def __init__(self, days):
        self.days = days

    def closes(self, ticker, start, end):
        return {}

    def closes_and_dividends(self, ticker, start, end):
        return {d: (Decimal(c), Decimal(v)) for d, (c, v) in self.days.items() if start <= d <= end}


@pytest.fixture
def spy(today):  # today is Oct 23, 2026 in tests
    fake = FakeProvider({
        D(2026, 1, 2): ("100", "0"),
        D(2026, 6, 1): ("120", "0"),
        D(2026, 10, 1): ("150", "0"),
        D(2026, 10, 23): ("150", "0"),
    })
    app.dependency_overrides[prices.get_price_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(prices.get_price_provider, None)


def create(client, name, type):
    return client.post("/api/accounts", json={"name": name, "type": type}).json()["id"]


def transfer(client, from_id, to_id, cents, date):
    response = client.post("/api/transfers", json={"from_account_id": from_id, "to_account_id": to_id,
                                                   "date": date, "amount_cents": cents})
    assert response.status_code == 201, response.json()


def compare(client, **params):
    response = client.get("/api/investments/comparison", params=params)
    assert response.status_code == 200, response.json()
    return response.json()


def test_same_transfers_into_spy(client, spy):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    transfer(client, checking, roth, 100000, "2026-01-02")  # 10 pretend shares at $100
    transfer(client, checking, roth, 120000, "2026-06-01")  # 10 more at $120
    client.post("/api/accounts/%d/reconcile" % roth, json={"date": "2026-10-01", "balance_cents": 250000})
    client.post("/api/prices/refresh")

    body = compare(client, account_id=roth)

    assert body["start"] == "2026-01-02"
    assert body["put_in_cents"] == 220000
    assert body["benchmark_cents"] == 300000  # 20 shares x $150
    assert body["value_cents"] == 250000  # yours: behind the S&P
    assert body["points"][-1]["date"] == "2026-10-23"
    assert body["points"][-1]["value_cents"] is None  # no holdings set up, so no value history


def test_opening_balance_and_setup_count_as_deposits(client, spy):
    brokerage = create(client, "Brokerage", "brokerage")
    client.post(f"/api/accounts/{brokerage}/reconcile", json={"date": "2026-06-01", "balance_cents": 120000})
    client.post(f"/api/accounts/{brokerage}/holdings", json={"date": "2026-10-01", "holdings": [
        {"ticker": "FUNDA", "name": "Fund A", "kind": "fund", "price_source": "manual",
         "shares": "10", "cost_basis_cents": 120000, "market_value_cents": 140000},
    ]})
    client.post("/api/prices/refresh")

    body = compare(client, account_id=brokerage)

    # Only the opening balance is a deposit: the setup's adjustment just moves the value into holdings.
    assert body["put_in_cents"] == 120000
    assert body["benchmark_cents"] == 150000  # 10 pretend shares at $120 -> $150
    assert body["value_cents"] == 140000
    assert body["tracked_since"] == "2026-10-01"
    assert body["points"][-1]["value_cents"] == 140000


def test_an_account_first_seen_at_setup_deposits_its_value_that_day(client, spy):
    k401 = create(client, "401k", "retirement")
    client.post(f"/api/accounts/{k401}/holdings", json={"date": "2026-10-01", "holdings": [
        {"ticker": "TRUST1", "name": "A trust", "kind": "fund", "price_source": "manual",
         "shares": "100", "cost_basis_cents": 1000000, "market_value_cents": 1500000},
    ]})
    client.post(f"/api/accounts/{k401}/trades", json={"date": "2026-10-23", "kind": "contribution",
                                                      "security_id": 1, "shares": "1", "amount_cents": 15000})
    client.post("/api/prices/refresh")

    body = compare(client, account_id=k401)

    assert body["start"] == "2026-10-01"
    assert body["put_in_cents"] == 1515000  # its value at setup + the payroll contribution


def test_all_accounts_together(client, spy):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    strike = create(client, "Strike", "brokerage")
    transfer(client, checking, roth, 100000, "2026-01-02")
    transfer(client, checking, strike, 30000, "2026-10-01")
    client.post("/api/prices/refresh")

    body = compare(client)

    assert body["put_in_cents"] == 130000
    assert body["benchmark_cents"] == 150000 + 30000


def test_no_deposits_yet(client, spy):
    create(client, "Roth IRA", "retirement")

    body = compare(client)

    assert body["start"] is None and body["points"] == []


def test_only_investment_accounts(client):
    checking = create(client, "Checking", "checking")

    assert client.get("/api/investments/comparison", params={"account_id": checking}).status_code == 422


def test_benchmark_refresh_fetches_only_whats_missing(client, spy):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    transfer(client, checking, roth, 100000, "2026-06-01")
    asked = []
    original = spy.closes_and_dividends
    spy.closes_and_dividends = lambda t, s, e: asked.append((s, e)) or original(t, s, e)

    client.post("/api/prices/refresh")
    client.post("/api/prices/refresh")
    transfer(client, checking, roth, 100000, "2026-01-02")  # an older deposit turns up
    client.post("/api/prices/refresh")

    assert asked[0] == (D(2026, 5, 25), D(2026, 10, 23))  # first time: a week before the first deposit
    assert asked[1] == (D(2026, 10, 19), D(2026, 10, 23))  # then just the last few days
    assert asked[2] == (D(2025, 12, 26), D(2026, 6, 1))  # the older range...

