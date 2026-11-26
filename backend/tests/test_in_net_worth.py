"""Accounts left out of net worth: retirement money you can't reach yet (401k, Roth IRA)."""

OCTOBER = {"start": "2026-10-01", "end": "2026-10-31"}


def create(client, name, type, **extra):
    response = client.post("/api/accounts", json={"name": name, "type": type, **extra})
    assert response.status_code == 201, response.json()
    return response.json()


def reconcile(client, account_id, balance_cents, date="2026-10-15"):
    response = client.post(f"/api/accounts/{account_id}/reconcile", json={"date": date, "balance_cents": balance_cents})
    assert response.status_code == 200, response.json()


def summary(client):
    return client.get("/api/dashboard/summary", params=OCTOBER).json()


def test_retirement_accounts_start_out_of_net_worth(client):
    assert create(client, "Roth IRA", "retirement")["in_net_worth"] is False
    assert create(client, "Checking", "checking")["in_net_worth"] is True
    assert create(client, "Brokerage", "brokerage")["in_net_worth"] is True


def test_default_can_be_overridden_when_creating(client):
    assert create(client, "Roth IRA", "retirement", in_net_worth=True)["in_net_worth"] is True
    assert create(client, "Old 401k", "brokerage", in_net_worth=False)["in_net_worth"] is False


def test_left_out_balance_doesnt_count_in_net_worth(client):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    reconcile(client, checking["id"], 500000)
    reconcile(client, roth["id"], 2500000)  # a balance snapshot from the provider

    body = summary(client)

    assert body["net_worth_cents"] == 500000
    assert body["net_worth_change_cents"] == 500000
    # A snapshot is an adjustment: never income or spending.
    assert body["income_cents"] == 0 and body["spending_cents"] == 0


def test_left_out_account_still_shows_its_balance(client):
    roth = create(client, "Roth IRA", "retirement")
    reconcile(client, roth["id"], 2500000)

    accounts = client.get("/api/accounts").json()

    assert accounts[0]["balance_cents"] == 2500000
    assert accounts[0]["in_net_worth"] is False


def test_switching_it_on_adds_it_to_net_worth(client):
    roth = create(client, "Roth IRA", "retirement")
    reconcile(client, roth["id"], 2500000)

    response = client.patch(f"/api/accounts/{roth['id']}", json={"in_net_worth": True})

    assert response.status_code == 200
    assert response.json()["in_net_worth"] is True
    assert summary(client)["net_worth_cents"] == 2500000


def test_in_net_worth_cant_be_null(client):
    roth = create(client, "Roth IRA", "retirement")

    response = client.patch(f"/api/accounts/{roth['id']}", json={"in_net_worth": None})

    assert response.status_code == 422


# ---- "invested" on the Saved card ----

def transfer(client, from_id, to_id, amount_cents, date="2026-10-15"):
    response = client.post("/api/transfers", json={
        "from_account_id": from_id, "to_account_id": to_id, "date": date, "amount_cents": amount_cents,
    })
    assert response.status_code == 201, response.json()


def test_transfers_into_investment_accounts_count_as_invested(client):
    checking = create(client, "Checking", "checking")
    savings = create(client, "Savings", "savings")
    roth = create(client, "Roth IRA", "retirement")
    strike = create(client, "Strike", "brokerage")
    transfer(client, checking["id"], roth["id"], 50000)
    transfer(client, checking["id"], strike["id"], 5000)
    transfer(client, checking["id"], savings["id"], 99900)  # a savings account isn't investing

    body = summary(client)

    assert body["moved_to_savings_cents"] == 55000
    assert body["spending_cents"] == 0  # transfers are never spending


def test_taking_money_out_or_moving_between_investments(client):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    strike = create(client, "Strike", "brokerage")
    transfer(client, checking["id"], strike["id"], 10000)
    transfer(client, strike["id"], roth["id"], 4000)  # between investments: no change
    transfer(client, strike["id"], checking["id"], 1000)  # sold some: lowers it

    assert summary(client)["moved_to_savings_cents"] == 9000
