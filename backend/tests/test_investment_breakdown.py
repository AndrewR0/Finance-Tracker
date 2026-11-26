"""Contributed / gain for Brokerage and Retirement accounts, derived from transfers and balance updates."""


def create(client, name, type):
    response = client.post("/api/accounts", json={"name": name, "type": type})
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def transfer(client, from_id, to_id, amount_cents, date):
    response = client.post("/api/transfers", json={
        "from_account_id": from_id, "to_account_id": to_id, "date": date, "amount_cents": amount_cents,
    })
    assert response.status_code == 201, response.json()


def update_balance(client, account_id, balance_cents, date):
    response = client.post(f"/api/accounts/{account_id}/reconcile", json={"date": date, "balance_cents": balance_cents})
    assert response.status_code == 200, response.json()


def account(client, account_id, **params):
    return next(a for a in client.get("/api/accounts", params=params).json() if a["id"] == account_id)


def test_contributions_then_a_balance_update(client):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    transfer(client, checking, roth, 700000, "2026-01-05")
    transfer(client, checking, roth, 300000, "2026-06-05")
    update_balance(client, roth, 1150000, "2026-11-26")  # worth $11,500 today

    body = account(client, roth)

    assert body["balance_cents"] == 1150000
    assert body["investment"] == {"starting_cents": 0, "contributed_cents": 1000000, "gain_cents": 150000}


def test_a_loss_is_a_negative_gain(client):
    checking = create(client, "Checking", "checking")
    strike = create(client, "Strike", "brokerage")
    transfer(client, checking, strike, 500000, "2026-01-05")
    update_balance(client, strike, 350000, "2026-11-26")

    assert account(client, strike)["investment"]["gain_cents"] == -150000


def test_opening_snapshot_counts_as_starting_balance_not_gain(client):
    checking = create(client, "Checking", "checking")
    brokerage = create(client, "Brokerage", "brokerage")
    update_balance(client, brokerage, 4000000, "2026-10-31")  # first thing ever: an opening snapshot
    transfer(client, checking, brokerage, 100000, "2026-11-05")
    update_balance(client, brokerage, 4200000, "2026-11-26")

    assert account(client, brokerage)["investment"] == {
        "starting_cents": 4000000, "contributed_cents": 100000, "gain_cents": 100000,
    }


def test_snapshot_only_account_is_all_starting_balance(client):
    k401 = create(client, "401k", "retirement")
    update_balance(client, k401, 9000000, "2026-11-25")

    assert account(client, k401)["investment"] == {"starting_cents": 9000000, "contributed_cents": 0, "gain_cents": 0}


def test_withdrawals_lower_contributed(client):
    checking = create(client, "Checking", "checking")
    strike = create(client, "Strike", "brokerage")
    transfer(client, checking, strike, 500000, "2026-01-05")
    transfer(client, strike, checking, 200000, "2026-03-05")

    assert account(client, strike)["investment"]["contributed_cents"] == 300000


def test_as_of_gives_the_breakdown_on_that_day(client):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    transfer(client, checking, roth, 700000, "2026-01-05")
    update_balance(client, roth, 900000, "2026-11-26")

    assert account(client, roth, as_of="2026-06-30")["investment"]["gain_cents"] == 0


def test_only_investment_accounts_get_a_breakdown(client):
    checking = create(client, "Checking", "checking")

    assert account(client, checking)["investment"] is None


def test_later_updates_on_a_snapshot_only_account_are_gains(client):
    k401 = create(client, "401k", "retirement")
    update_balance(client, k401, 8000000, "2026-10-31")
    update_balance(client, k401, 8300000, "2026-11-26")

    assert account(client, k401)["investment"] == {"starting_cents": 8000000, "contributed_cents": 0, "gain_cents": 300000}


def test_corrections_in_the_first_week_are_part_of_the_opening_balance(client):
    brokerage = create(client, "Brokerage", "brokerage")
    update_balance(client, brokerage, 4000000, "2026-10-31")
    update_balance(client, brokerage, 4100000, "2026-11-02")  # a setup correction, 2 days later
    update_balance(client, brokerage, 4200000, "2026-11-26")  # a real update, weeks later

    assert account(client, brokerage)["investment"] == {
        "starting_cents": 4100000, "contributed_cents": 0, "gain_cents": 100000,
    }


def test_a_transfer_ends_the_setup_week_early(client):
    checking = create(client, "Checking", "checking")
    roth = create(client, "Roth IRA", "retirement")
    update_balance(client, roth, 1000000, "2026-11-01")
    transfer(client, checking, roth, 50000, "2026-11-02")
    update_balance(client, roth, 1100000, "2026-11-03")

    assert account(client, roth)["investment"] == {"starting_cents": 1000000, "contributed_cents": 50000, "gain_cents": 50000}
