"""Investments step 2: automatic prices, through a fake PriceProvider (no network in tests)."""

import datetime as dt
from decimal import Decimal

import pytest

from app import prices
from app.main import app
from app.prices import to_price_units


class FakeProvider:
    """Answers from a dict; records what it was asked for."""

    def __init__(self, closes: dict[str, dict[dt.date, str]], broken: set[str] = frozenset()):
        self.data = closes
        self.broken = broken
        self.asked: list[tuple[str, dt.date, dt.date]] = []

    def closes(self, ticker, start, end):
        self.asked.append((ticker, start, end))
        if ticker in self.broken:
            raise ConnectionError("Yahoo is down")
        return {day: Decimal(price) for day, price in self.data.get(ticker, {}).items() if start <= day <= end}

    def closes_and_dividends(self, ticker, start, end):
        return {}  # no benchmark data in these tests (tests/test_benchmark.py covers it)


@pytest.fixture
def provider(today):
    fake = FakeProvider({
        "VTI": {dt.date(2026, 10, 21): "350.10", dt.date(2026, 10, 22): "352.4567"},
        "BTC-USD": {dt.date(2026, 10, 22): "61000", dt.date(2026, 10, 23): "62000.5"},
    })
    app.dependency_overrides[prices.get_price_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(prices.get_price_provider, None)


def set_up(client, name, type, holdings):
    account = client.post("/api/accounts", json={"name": name, "type": type}).json()["id"]
    response = client.post(f"/api/accounts/{account}/holdings", json={"date": "2026-10-22", "holdings": holdings})
    assert response.status_code == 201, response.json()
    return account


def holding(ticker, shares, cost, value, **extra):
    return {"ticker": ticker, "name": ticker, "kind": "fund", "shares": shares,
            "cost_basis_cents": cost, "market_value_cents": value, **extra}


def refresh(client):
    response = client.post("/api/prices/refresh")
    assert response.status_code == 200, response.json()
    return response.json()


def holdings(client):
    return {h["ticker"]: h for a in client.get("/api/holdings").json() for h in a["holdings"]}


def test_to_price_units_is_exact():
    assert to_price_units(Decimal("352.4567")) == 352_456_700
    assert to_price_units(Decimal("658.869995")) == 658_869_995
    assert to_price_units(Decimal("0.1234565")) == 123_457  # half rounds up


def test_refresh_updates_values_from_market_prices(client, provider):
    set_up(client, "Roth IRA", "retirement", [holding("VTI", "10", 300000, 350000)])
    set_up(client, "Strike", "brokerage", [holding("BTC-USD", "0.5", 2500000, 3000000, kind="crypto")])

    status = refresh(client)

    assert status["failed"] == {}
    assert status["prices_as_of"] == "2026-10-23"
    held = holdings(client)
    # The market close on the setup day replaces the typed-in price: 10 x $352.4567.
    assert held["VTI"]["price"] == 352_456_700 and held["VTI"]["value_cents"] == 352457
    assert held["BTC-USD"]["price_date"] == "2026-10-23"  # crypto trades every day
    assert held["BTC-USD"]["value_cents"] == 3100025  # 0.5 x $62,000.50


def test_manual_price_securities_are_never_fetched(client, provider):
    set_up(client, "401k", "retirement", [holding("TRUST1", "3", 30000, 37800, price_source="manual")])

    refresh(client)

    assert provider.asked == []
    assert holdings(client)["TRUST1"]["price"] == 126_000_000  # still the typed-in one


def test_one_broken_ticker_doesnt_stop_the_others(client, today):
    fake = FakeProvider({"VTI": {dt.date(2026, 10, 22): "352"}}, broken={"VXUS"})
    app.dependency_overrides[prices.get_price_provider] = lambda: fake
    set_up(client, "Roth IRA", "retirement", [holding("VTI", "10", 300000, 350000), holding("VXUS", "10", 70000, 78000)])

    status = refresh(client)
    app.dependency_overrides.pop(prices.get_price_provider)

    assert "VXUS" in status["failed"] and "Yahoo is down" in status["failed"]["VXUS"]
    held = holdings(client)
    assert held["VTI"]["price"] == 352_000_000
    assert held["VXUS"]["value_cents"] == 78000  # the last price it had still stands


def test_unknown_ticker_is_reported(client, provider):
    set_up(client, "Strike", "brokerage", [holding("BTC", "0.5", 2500000, 3000000, kind="crypto")])

    status = refresh(client)

    assert "BTC-USD" in status["failed"]["BTC"]


def test_the_next_refresh_only_asks_for_recent_days(client, provider):
    set_up(client, "Roth IRA", "retirement", [holding("VTI", "10", 300000, 350000)])
    refresh(client)
    provider.asked.clear()

    refresh(client)

    (ticker, start, end), = provider.asked
    assert (ticker, end) == ("VTI", dt.date(2026, 10, 23))
    assert start == dt.date(2026, 10, 18)  # newest price (Oct 22) minus 4 days


def test_status_before_any_refresh(client):
    body = client.get("/api/prices/status").json()

    assert body["prices_as_of"] is None


def test_a_ticker_for_a_different_fund_is_caught_and_not_used(client, today):
    # The 401k fund is a trust priced at $100; "FUNDX" on Yahoo is a different fund at $80.
    fake = FakeProvider({"FUNDX": {dt.date(2026, 10, 21): "80"}})
    app.dependency_overrides[prices.get_price_provider] = lambda: fake
    set_up(client, "401k", "retirement", [holding("FUNDX", "100", 1000000, 1000000)])

    status = refresh(client)
    app.dependency_overrides.pop(prices.get_price_provider)

    assert "20% off" in status["failed"]["FUNDX"]
    assert holdings(client)["FUNDX"]["value_cents"] == 1000000  # unchanged


def test_switching_to_manual_prices(client, today):
    fake = FakeProvider({"FUNDX": {dt.date(2026, 10, 21): "80"}})
    app.dependency_overrides[prices.get_price_provider] = lambda: fake
    set_up(client, "401k", "retirement", [holding("FUNDX", "100", 1000000, 1000000)])
    refresh(client)
    security_id = holdings(client)["FUNDX"]["security_id"]

    response = client.patch(f"/api/securities/{security_id}", json={"price_source": "manual"})
    status = refresh(client)
    app.dependency_overrides.pop(prices.get_price_provider)

    assert response.status_code == 204
    assert holdings(client)["FUNDX"]["price_source"] == "manual"
    assert "FUNDX" not in status["failed"]
