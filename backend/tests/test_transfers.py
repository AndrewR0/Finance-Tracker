from datetime import datetime

import pytest

from app.models import Account, AccountType


@pytest.fixture
def checking(client):
    return client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()


@pytest.fixture
def visa(client):
    return client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"}).json()


def transfer(client, from_id, to_id, amount_cents=61200, date="2026-10-21", **extra):
    return client.post(
        "/api/transfers",
        json={"from_account_id": from_id, "to_account_id": to_id,
              "date": date, "amount_cents": amount_cents, **extra},
    )


# ---- creating (your code) ----

def test_transfer_creates_two_opposite_legs(client, checking, visa):
    response = transfer(client, checking["id"], visa["id"], description="Credit card payment")

    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "Credit card payment"
    assert body["from_leg"]["account_id"] == checking["id"]
    assert body["from_leg"]["amount_cents"] == -61200
    assert body["to_leg"]["account_id"] == visa["id"]
    assert body["to_leg"]["amount_cents"] == 61200


def test_description_is_shown_on_legs_but_not_copied_into_notes(client, checking, visa):
    transfer(client, checking["id"], visa["id"], description="Credit card payment")

    rows = client.get("/api/transactions").json()

    for leg in rows:
        assert leg["transfer_description"] == "Credit card payment"
        assert leg["notes"] is None


def test_ordinary_transactions_have_no_transfer_description(client, checking):
    body = client.post(
        "/api/transactions",
        json={"account_id": checking["id"], "date": "2026-10-21", "amount_cents": -500},
    ).json()

    assert body["transfer_description"] is None


def test_both_legs_share_the_transfer_and_date(client, checking, visa):
    body = transfer(client, checking["id"], visa["id"], date="2026-10-21").json()

    for leg in (body["from_leg"], body["to_leg"]):
        assert leg["transfer_id"] == body["id"]
        assert leg["date"] == "2026-10-21"
        assert leg["payee_id"] is None


def test_legs_show_up_as_ordinary_transactions(client, checking, visa):
    transfer(client, checking["id"], visa["id"])

    rows = client.get("/api/transactions").json()

    assert sorted(t["amount_cents"] for t in rows) == [-61200, 61200]
    assert sum(t["amount_cents"] for t in rows) == 0  # money moved, none created or lost


def test_each_account_sees_only_its_own_leg(client, checking, visa):
    transfer(client, checking["id"], visa["id"])

    checking_rows = client.get("/api/transactions", params={"account_id": checking["id"]}).json()

    assert [t["amount_cents"] for t in checking_rows] == [-61200]


def test_transfer_category_goes_on_both_legs(client, checking, visa):
    category = client.post("/api/categories", json={"name": "Credit card payment", "kind": "transfer"}).json()

    body = transfer(client, checking["id"], visa["id"], category_id=category["id"]).json()

    assert body["from_leg"]["category_id"] == category["id"]
    assert body["to_leg"]["category_id"] == category["id"]


def test_ordinary_transactions_have_no_transfer(client, checking):
    body = client.post(
        "/api/transactions",
        json={"account_id": checking["id"], "date": "2026-10-21", "amount_cents": -500},
    ).json()

    assert body["transfer_id"] is None


# ---- validation (check_transfer and the schema) ----

@pytest.mark.parametrize("bad_amount", [0, -61200, 612.0])
def test_amount_must_be_positive_integer_cents(client, checking, visa, bad_amount):
    assert transfer(client, checking["id"], visa["id"], amount_cents=bad_amount).status_code == 422


def test_accounts_must_differ(client, checking):
    assert transfer(client, checking["id"], checking["id"]).status_code == 422


def test_accounts_must_exist(client, checking):
    assert transfer(client, checking["id"], 999).status_code == 422
    assert transfer(client, 999, checking["id"]).status_code == 422


def test_closed_account_is_rejected(client, db_session, checking):
    closed = Account(name="Old Card", type=AccountType.CREDIT_CARD, closed_at=datetime(2026, 1, 1))
    db_session.add(closed)
    db_session.commit()

    assert transfer(client, checking["id"], closed.id).status_code == 422


def test_non_transfer_category_is_rejected(client, checking, visa):
    food = client.post("/api/categories", json={"name": "Food", "kind": "expense"}).json()

    response = transfer(client, checking["id"], visa["id"], category_id=food["id"])

    assert response.status_code == 422
    assert "not a transfer category" in response.json()["detail"]


def test_rejected_transfer_saves_nothing(client, checking):
    transfer(client, checking["id"], 999)

    assert client.get("/api/transactions").json() == []
