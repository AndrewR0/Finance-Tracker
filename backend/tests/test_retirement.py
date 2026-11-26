"""Retirement estimator inputs and settings. Made-up numbers only."""


def create(client, name, type, **extra):
    response = client.post("/api/accounts", json={"name": name, "type": type, **extra})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def category(client, name, kind):
    return client.post("/api/categories", json={"name": name, "kind": kind}).json()["id"]


def add(client, account, cents, category_id, date):
    response = client.post("/api/transactions", json={"account_id": account, "date": date,
                                                      "amount_cents": cents, "category_id": category_id})
    assert response.status_code == 201, response.json()


def transfer(client, from_id, to_id, cents, date):
    response = client.post("/api/transfers", json={"from_account_id": from_id, "to_account_id": to_id,
                                                   "date": date, "amount_cents": cents})
    assert response.status_code == 201, response.json()


def inputs(client):
    response = client.get("/api/retirement")
    assert response.status_code == 200, response.json()
    return response.json()


def test_defaults_before_anything_is_saved(client, today):
    body = inputs(client)

    assert body["settings"] == {
        "birth_year": None, "retire_age": None, "withdrawal_rate_bp": 400, "real_return_bp": 700,
        "volatility_bp": 1500, "spending_override_cents": None, "contribution_override_cents": None, "k401_yearly_cents": 0,
    }
    assert body["period_start"] == "2025-10-24" and body["period_end"] == "2026-10-23"  # 365 days to today


def test_inputs_come_from_the_last_12_months(client, today):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    food = category(client, "Food", "expense")
    add(client, checking, -300000, food, "2026-03-01")
    add(client, checking, -999900, food, "2025-06-01")  # more than 12 months ago: left out
    transfer(client, checking, roth, 50000, "2026-04-01")
    client.post(f"/api/accounts/{roth}/reconcile", json={"date": "2026-10-01", "balance_cents": 60000})

    body = inputs(client)

    assert body["spending_12m_cents"] == 300000
    assert body["invested_12m_cents"] == 50000
    assert body["balance_cents"] == 60000
    assert [a["name"] for a in body["accounts"]] == ["Roth IRA"]  # investment accounts only


def test_401k_contribution_trades_are_counted(client, today):
    k401 = create(client, "401k", "retirement")
    client.post(f"/api/accounts/{k401}/holdings", json={"date": "2026-09-01", "holdings": [
        {"ticker": "TRUST1", "name": "A trust", "kind": "fund", "price_source": "manual",
         "shares": "100", "cost_basis_cents": 1000000, "market_value_cents": 1000000}]})
    client.post(f"/api/accounts/{k401}/trades", json={"date": "2026-09-30", "kind": "contribution",
                                                      "security_id": 1, "shares": "2", "amount_cents": 20000})

    body = inputs(client)

    assert body["k401_12m_cents"] == 20000
    assert body["balance_cents"] == 1020000


def test_save_and_read_back_settings(client, today):
    new = {"birth_year": 1995, "retire_age": 55, "withdrawal_rate_bp": 350, "real_return_bp": 600,
           "volatility_bp": 1800, "spending_override_cents": 4000000, "contribution_override_cents": None, "k401_yearly_cents": 1200000}

    response = client.put("/api/retirement/settings", json=new)

    assert response.status_code == 200, response.json()
    assert inputs(client)["settings"] == new


def test_null_override_goes_back_to_actual(client, today):
    client.put("/api/retirement/settings", json={"spending_override_cents": 4000000})

    client.put("/api/retirement/settings", json={"spending_override_cents": None})

    assert inputs(client)["settings"]["spending_override_cents"] is None


def test_bad_settings_are_refused(client, today):
    for bad in ({"withdrawal_rate_bp": 0}, {"withdrawal_rate_bp": 4.5}, {"birth_year": 1800},
                {"k401_yearly_cents": -1}, {"surprise": 1}):
        assert client.put("/api/retirement/settings", json=bad).status_code == 422, bad
