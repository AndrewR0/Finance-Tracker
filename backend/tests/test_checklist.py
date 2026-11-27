"""The month-end checklist (today is Oct 23, 2026 in tests). Made-up numbers only."""


def create(client, name, type):
    response = client.post("/api/accounts", json={"name": name, "type": type})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def reconcile(client, account, cents, date):
    response = client.post(f"/api/accounts/{account}/reconcile", json={"date": date, "balance_cents": cents})
    assert response.status_code == 200, response.json()
    return response.json()


def set_up(client, account, ticker, price_source="manual", date="2026-09-15", cash_cents=0):
    response = client.post(f"/api/accounts/{account}/holdings", json={"date": date, "cash_cents": cash_cents, "holdings": [
        {"ticker": ticker, "name": f"{ticker} fund", "kind": "fund", "price_source": price_source,
         "shares": "10", "cost_basis_cents": 100000, "market_value_cents": 100000}]})
    assert response.status_code == 201, response.json()
    return response.json()["holdings"][0]["security_id"]


def items(client):
    response = client.get("/api/dashboard/checklist")
    assert response.status_code == 200, response.json()
    return {i["key"]: i for i in response.json()}


def test_reconcile_items_for_everyday_accounts(client, today):
    checking = create(client, "Checking", "checking")
    card = create(client, "Card", "credit_card")
    create(client, "Brokerage", "brokerage")  # not reconciled monthly

    found = items(client)

    assert set(found) == {f"reconcile:{checking}", f"reconcile:{card}"}
    assert not found[f"reconcile:{checking}"]["done"]
    assert "never reconciled" in found[f"reconcile:{checking}"]["detail"]


def test_reconciling_this_month_ticks_it_off_even_when_it_matched(client, today):
    checking = create(client, "Checking", "checking")
    reconcile(client, checking, 0, "2026-10-01")  # already matched: no adjustment is added

    assert items(client)[f"reconcile:{checking}"]["done"] is True


def test_last_months_reconcile_doesnt_count(client, today):
    checking = create(client, "Checking", "checking")
    reconcile(client, checking, 5000, "2026-09-30")

    item = items(client)[f"reconcile:{checking}"]
    assert item["done"] is False
    assert "Sep 30" in item["detail"]


def test_manual_prices_need_a_price_this_month(client, today):
    k401 = create(client, "401k", "retirement")
    security = set_up(client, k401, "TRUST1")

    assert items(client)[f"price:{security}"]["done"] is False

    client.post(f"/api/securities/{security}/prices", json={"date": "2026-10-20", "price": "105"})

    assert items(client)[f"price:{security}"]["done"] is True


def test_automatic_prices_arent_listed(client, today):
    roth = create(client, "Roth IRA", "retirement")
    set_up(client, roth, "FUNDA", price_source="yfinance")

    assert not any(key.startswith("price:") for key in items(client))


def test_payroll_retirement_account_needs_a_monthly_contribution(client, today):
    k401 = create(client, "401k", "retirement")
    security = set_up(client, k401, "TRUST1")

    assert items(client)[f"contribution:{k401}"]["done"] is False

    client.post(f"/api/accounts/{k401}/trades", json={"date": "2026-10-15", "kind": "contribution",
                                                      "security_id": security, "shares": "1", "amount_cents": 10000})

    assert items(client)[f"contribution:{k401}"]["done"] is True


def test_retirement_account_fed_by_transfers_has_no_contribution_item(client, today):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    client.post("/api/transfers", json={"from_account_id": checking, "to_account_id": roth,
                                        "date": "2026-09-01", "amount_cents": 100000})
    set_up(client, roth, "FUNDA", price_source="yfinance")

    assert f"contribution:{roth}" not in items(client)


def test_uninvested_cash_is_a_reminder_until_the_buy(client, today):
    checking = create(client, "Checking", "checking")
    strike = create(client, "Strike", "brokerage")
    security = set_up(client, strike, "COINX", price_source="yfinance")
    for day in ("2026-10-05", "2026-10-12"):
        client.post("/api/transfers", json={"from_account_id": checking, "to_account_id": strike,
                                            "date": day, "amount_cents": 5000})

    item = items(client)[f"invest:{strike}"]
    assert "$100.00" in item["detail"]

    client.post(f"/api/accounts/{strike}/trades", json={"date": "2026-10-20", "kind": "buy", "security_id": security,
                                                        "shares": "0.1", "amount_cents": 10000})

    assert f"invest:{strike}" not in items(client)


def test_closed_accounts_are_left_out(client, today):
    old = create(client, "Old checking", "checking")
    client.post(f"/api/accounts/{old}/close")

    assert items(client) == {}
