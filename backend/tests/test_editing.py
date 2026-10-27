from datetime import datetime

import pytest

from app.models import Account, AccountType


@pytest.fixture
def checking(client):
    return client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()


@pytest.fixture
def visa(client):
    return client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"}).json()


@pytest.fixture
def groceries(client):
    return client.post("/api/categories", json={"name": "Groceries", "kind": "expense"}).json()


@pytest.fixture
def expense(client, checking, groceries):
    """An ordinary transaction to edit."""
    return client.post("/api/transactions", json={
        "account_id": checking["id"], "date": "2026-10-22", "amount_cents": -8412,
        "payee": "Trader Joe's", "category_id": groceries["id"], "notes": "weekly shop",
    }).json()


@pytest.fixture
def card_payment(client, checking, visa):
    """A transfer to edit: $612 from Checking to Visa."""
    return client.post("/api/transfers", json={
        "from_account_id": checking["id"], "to_account_id": visa["id"],
        "date": "2026-10-21", "amount_cents": 61200, "description": "Credit card payment",
    }).json()


def balances(client):
    return {a["name"]: a["balance_cents"] for a in client.get("/api/accounts").json()}


def patch_tx(client, tx, **changes):
    return client.patch(f"/api/transactions/{tx['id']}", json=changes)


def patch_transfer(client, transfer, **changes):
    return client.patch(f"/api/transfers/{transfer['id']}", json=changes)


# ======================= editing transactions =======================

def test_patch_changes_only_the_fields_sent(client, expense):
    response = patch_tx(client, expense, amount_cents=-9000)

    assert response.status_code == 200
    body = response.json()
    assert body["amount_cents"] == -9000
    for unchanged in ("date", "payee_name", "category_id", "notes", "account_id"):
        assert body[unchanged] == expense[unchanged]


def test_null_clears_an_optional_field(client, expense):
    body = patch_tx(client, expense, category_id=None, notes=None).json()

    assert body["category_id"] is None
    assert body["notes"] is None
    assert body["payee_name"] == "Trader Joe's"  # not sent, so untouched


def test_patch_payee_reuses_or_creates(client, expense):
    other = client.post("/api/transactions", json={
        "account_id": expense["account_id"], "date": "2026-10-23", "amount_cents": -500, "payee": "Blue Bottle",
    }).json()

    body = patch_tx(client, expense, payee="blue bottle").json()

    assert body["payee_id"] == other["payee_id"]
    assert patch_tx(client, expense, payee=None).json()["payee_name"] is None


def test_move_to_another_account_updates_both_balances(client, expense, visa):
    patch_tx(client, expense, account_id=visa["id"])

    assert balances(client) == {"Checking": 0, "Visa": -8412}


def test_cannot_move_into_a_closed_account(client, db_session, expense):
    closed = Account(name="Old Card", type=AccountType.CREDIT_CARD, closed_at=datetime(2026, 1, 1))
    db_session.add(closed)
    db_session.commit()

    assert patch_tx(client, expense, account_id=closed.id).status_code == 422


def test_cannot_use_a_transfer_category(client, expense):
    transfer_cat = client.post("/api/categories", json={"name": "Transfer", "kind": "transfer"}).json()

    assert patch_tx(client, expense, category_id=transfer_cat["id"]).status_code == 422


@pytest.mark.parametrize("bad", [
    {"amount_cents": None},   # required field can't be cleared
    {"amount_cents": 90.5},   # cents only
    {"date": None},
    {"account_id": None},
    {"amount": -9000},        # typo: unknown field
])
def test_bad_patches_are_rejected_and_change_nothing(client, expense, bad):
    response = client.patch(f"/api/transactions/{expense['id']}", json=bad)

    assert response.status_code == 422
    assert client.get("/api/transactions").json()[0]["amount_cents"] == -8412


def test_patch_missing_transaction_is_404(client):
    assert client.patch("/api/transactions/999", json={"notes": "x"}).status_code == 404


def test_delete_transaction(client, expense):
    response = client.delete(f"/api/transactions/{expense['id']}")

    assert response.status_code == 204
    assert client.get("/api/transactions").json() == []
    assert balances(client) == {"Checking": 0}


def test_delete_missing_transaction_is_404(client):
    assert client.delete("/api/transactions/999").status_code == 404


def test_transfer_legs_cannot_be_edited_or_deleted_one_at_a_time(client, card_payment):
    leg = card_payment["from_leg"]

    edit = client.patch(f"/api/transactions/{leg['id']}", json={"amount_cents": -100})
    delete = client.delete(f"/api/transactions/{leg['id']}")

    assert edit.status_code == 409
    assert f"/api/transfers/{card_payment['id']}" in edit.json()["detail"]
    assert delete.status_code == 409
    assert balances(client) == {"Checking": -61200, "Visa": 61200}


# ======================= editing transfers (your code) =======================

def test_new_amount_goes_on_both_legs_with_opposite_signs(client, card_payment):
    body = patch_transfer(client, card_payment, amount_cents=50000).json()

    assert body["from_leg"]["amount_cents"] == -50000
    assert body["to_leg"]["amount_cents"] == 50000
    assert balances(client) == {"Checking": -50000, "Visa": 50000}


def test_new_date_goes_on_both_legs(client, card_payment):
    body = patch_transfer(client, card_payment, date="2026-10-25").json()

    assert body["from_leg"]["date"] == "2026-10-25"
    assert body["to_leg"]["date"] == "2026-10-25"


def test_description_changes_on_the_transfer(client, card_payment):
    body = patch_transfer(client, card_payment, description="Visa payment").json()

    assert body["description"] == "Visa payment"
    assert body["from_leg"]["transfer_description"] == "Visa payment"
    assert body["from_leg"]["notes"] is None


def test_blank_or_null_description_clears_it(client, card_payment):
    assert patch_transfer(client, card_payment, description="  ").json()["description"] is None
    assert patch_transfer(client, card_payment, description="Back").json()["description"] == "Back"
    assert patch_transfer(client, card_payment, description=None).json()["description"] is None


def test_category_set_and_cleared_on_both_legs(client, card_payment):
    cat = client.post("/api/categories", json={"name": "Card payment", "kind": "transfer"}).json()

    body = patch_transfer(client, card_payment, category_id=cat["id"]).json()
    assert body["from_leg"]["category_id"] == cat["id"]
    assert body["to_leg"]["category_id"] == cat["id"]

    body = patch_transfer(client, card_payment, category_id=None).json()
    assert body["from_leg"]["category_id"] is None
    assert body["to_leg"]["category_id"] is None


def test_fields_not_sent_are_untouched(client, card_payment):
    body = patch_transfer(client, card_payment, date="2026-10-25").json()

    assert body["description"] == "Credit card payment"
    assert body["from_leg"]["amount_cents"] == -61200


# ======================= transfer validation and delete =======================

@pytest.mark.parametrize("bad", [{"amount_cents": 0}, {"amount_cents": -5}, {"amount_cents": None}, {"date": None}])
def test_bad_transfer_patches_are_rejected(client, card_payment, bad):
    assert client.patch(f"/api/transfers/{card_payment['id']}", json=bad).status_code == 422


def test_transfer_category_must_be_transfer_kind(client, card_payment, groceries):
    assert patch_transfer(client, card_payment, category_id=groceries["id"]).status_code == 422


def test_patch_missing_transfer_is_404(client):
    assert client.patch("/api/transfers/999", json={"description": "x"}).status_code == 404


def test_delete_transfer_removes_both_legs(client, card_payment):
    response = client.delete(f"/api/transfers/{card_payment['id']}")

    assert response.status_code == 204
    assert client.get("/api/transactions").json() == []
    assert balances(client) == {"Checking": 0, "Visa": 0}


def test_delete_missing_transfer_is_404(client):
    assert client.delete("/api/transfers/999").status_code == 404
