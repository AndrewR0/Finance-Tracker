from datetime import datetime

import pytest

from app.models import Account, AccountType


@pytest.fixture
def checking(client):
    return client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()


@pytest.fixture
def groceries(client):
    food = client.post("/api/categories", json={"name": "Food", "kind": "expense"}).json()
    return client.post(
        "/api/categories", json={"name": "Groceries", "kind": "expense", "parent_id": food["id"]}
    ).json()


def add(client, account_id, amount_cents, date="2026-10-22", **extra):
    return client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": date, "amount_cents": amount_cents, **extra},
    )


# ---- creating ----

def test_create_expense(client, checking, groceries):
    response = add(client, checking["id"], -8412, payee="Trader Joe's", category_id=groceries["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["account_id"] == checking["id"]
    assert body["date"] == "2026-10-22"
    assert body["amount_cents"] == -8412
    assert body["payee_name"] == "Trader Joe's"
    assert body["category_id"] == groceries["id"]


def test_payee_category_and_notes_are_optional(client, checking):
    response = add(client, checking["id"], 270000)

    assert response.status_code == 201
    body = response.json()
    assert body["payee_id"] is None
    assert body["payee_name"] is None
    assert body["category_id"] is None
    assert body["notes"] is None


@pytest.mark.parametrize("bad_amount", [84.12, "8412", None])
def test_amount_must_be_integer_cents(client, checking, bad_amount):
    response = add(client, checking["id"], bad_amount)

    assert response.status_code == 422


def test_bad_date_is_rejected(client, checking):
    response = add(client, checking["id"], -100, date="2026-02-30")

    assert response.status_code == 422


# ---- references (check_references) ----

def test_account_must_exist(client):
    assert add(client, 999, -100).status_code == 422


def test_closed_account_is_rejected(client, db_session):
    closed = Account(name="Old Card", type=AccountType.CREDIT_CARD, closed_at=datetime(2026, 1, 1))
    db_session.add(closed)
    db_session.commit()

    response = add(client, closed.id, -100)

    assert response.status_code == 422
    assert "closed" in response.json()["detail"]


def test_category_must_exist(client, checking):
    assert add(client, checking["id"], -100, category_id=999).status_code == 422


def test_transfer_category_is_rejected(client, checking):
    transfer = client.post("/api/categories", json={"name": "Transfer", "kind": "transfer"}).json()

    response = add(client, checking["id"], -100, category_id=transfer["id"])

    assert response.status_code == 422


# ---- payees (get_or_create_payee) ----

def test_same_payee_name_reuses_the_payee(client, checking):
    first = add(client, checking["id"], -500, payee="Blue Bottle").json()
    second = add(client, checking["id"], -475, payee="Blue Bottle").json()

    assert first["payee_id"] is not None
    assert second["payee_id"] == first["payee_id"]


def test_payee_match_ignores_case_and_keeps_first_spelling(client, checking):
    first = add(client, checking["id"], -8412, payee="Trader Joe's").json()
    second = add(client, checking["id"], -2310, payee="TRADER JOE'S").json()

    assert second["payee_id"] == first["payee_id"]
    assert second["payee_name"] == "Trader Joe's"


def test_different_payees_get_different_ids(client, checking):
    a = add(client, checking["id"], -500, payee="Blue Bottle").json()
    b = add(client, checking["id"], -1485, payee="Chipotle").json()

    assert a["payee_id"] != b["payee_id"]


# ---- listing ----

def test_list_is_newest_first(client, checking):
    add(client, checking["id"], -1, date="2026-10-20")
    add(client, checking["id"], -2, date="2026-10-22")
    add(client, checking["id"], -3, date="2026-10-21")
    add(client, checking["id"], -4, date="2026-10-22")  # same day: later entry first

    amounts = [t["amount_cents"] for t in client.get("/api/transactions").json()]

    assert amounts == [-4, -2, -3, -1]


def test_list_filters_by_account(client, checking):
    visa = client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"}).json()
    add(client, checking["id"], -100)
    add(client, visa["id"], -200)

    rows = client.get("/api/transactions", params={"account_id": visa["id"]}).json()

    assert [t["amount_cents"] for t in rows] == [-200]


def test_list_filters_by_date_range_inclusive(client, checking):
    for day in ["2026-09-30", "2026-10-01", "2026-10-31", "2026-11-01"]:
        add(client, checking["id"], -100, date=day)

    rows = client.get("/api/transactions", params={"start": "2026-10-01", "end": "2026-10-31"}).json()

    assert [t["date"] for t in rows] == ["2026-10-31", "2026-10-01"]
