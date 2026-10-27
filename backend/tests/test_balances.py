from datetime import datetime

import pytest

from app.models import Account, AccountType


@pytest.fixture
def checking(client):
    return client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()


@pytest.fixture
def visa(client):
    return client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"}).json()


def add(client, account_id, amount_cents, date="2026-10-15"):
    client.post("/api/transactions", json={"account_id": account_id, "date": date, "amount_cents": amount_cents})


def balances(client, **params):
    """{account name: balance_cents} from GET /api/accounts."""
    return {a["name"]: a["balance_cents"] for a in client.get("/api/accounts", params=params).json()}


def test_new_account_has_zero_balance(client, checking):
    assert balances(client) == {"Checking": 0}


def test_balance_is_the_sum_of_transactions(client, checking):
    add(client, checking["id"], 270000)  # paycheck
    add(client, checking["id"], -8412)   # groceries
    add(client, checking["id"], 2500)    # refund

    assert balances(client) == {"Checking": 264088}


def test_each_account_only_counts_its_own_transactions(client, checking, visa):
    add(client, checking["id"], 10000)
    add(client, visa["id"], -4630)

    assert balances(client) == {"Checking": 10000, "Visa": -4630}


def test_transfer_moves_money_without_changing_the_total(client, checking, visa):
    add(client, checking["id"], 100000)
    add(client, visa["id"], -61200)
    client.post("/api/transfers", json={
        "from_account_id": checking["id"], "to_account_id": visa["id"],
        "date": "2026-10-20", "amount_cents": 61200,
    })

    result = balances(client)

    assert result == {"Checking": 38800, "Visa": 0}
    assert sum(result.values()) == 100000 - 61200  # same total as before the transfer


def test_as_of_counts_only_transactions_up_to_that_day(client, checking):
    add(client, checking["id"], 100, date="2026-10-30")
    add(client, checking["id"], 20, date="2026-10-31")  # on the day: included
    add(client, checking["id"], 3, date="2026-11-01")   # after: excluded

    assert balances(client, as_of="2026-10-31") == {"Checking": 120}
    assert balances(client) == {"Checking": 123}


def test_as_of_before_any_transactions_is_zero(client, checking):
    add(client, checking["id"], 500, date="2026-10-15")

    assert balances(client, as_of="2026-01-01") == {"Checking": 0}


def test_closed_account_still_reports_its_balance(client, db_session):
    old = Account(name="Old Card", type=AccountType.CREDIT_CARD)
    db_session.add(old)
    db_session.commit()
    add(client, old.id, -1500)
    old.closed_at = datetime(2026, 10, 31)
    db_session.commit()

    assert balances(client) == {"Old Card": -1500}
