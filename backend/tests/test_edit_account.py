from datetime import datetime

from app.models import Account, AccountType


def create(client, name, type_="checking"):
    return client.post("/api/accounts", json={"name": name, "type": type_}).json()["id"]


def rename(client, account_id, name):
    return client.patch(f"/api/accounts/{account_id}", json={"name": name})


def closed_account(db_session, name):
    account = Account(name=name, type=AccountType.CREDIT_CARD, closed_at=datetime(2025, 6, 1))
    db_session.add(account)
    db_session.commit()
    return account.id


def test_rename_changes_the_name(client):
    visa = create(client, "Visa", "credit_card")

    response = rename(client, visa, "Chase Sapphire")

    assert response.status_code == 200
    assert response.json()["name"] == "Chase Sapphire"
    assert [a["name"] for a in client.get("/api/accounts").json()] == ["Chase Sapphire"]


def test_name_is_trimmed(client):
    visa = create(client, "Visa", "credit_card")

    assert rename(client, visa, "  Amex  ").json()["name"] == "Amex"


def test_type_and_balance_are_untouched(client):
    checking = create(client, "Checking")
    client.post("/api/transactions", json={"account_id": checking, "date": "2026-10-01", "amount_cents": 5000})

    rename(client, checking, "Everyday")

    [account] = client.get("/api/accounts").json()
    assert (account["type"], account["balance_cents"]) == ("checking", 5000)


def test_transactions_follow_the_rename(client):
    checking = create(client, "Checking")
    client.post("/api/transactions", json={"account_id": checking, "date": "2026-10-01", "amount_cents": -100})

    rename(client, checking, "Everyday")

    # Transactions store the account id, not its name, so nothing else needs updating.
    [tx] = client.get("/api/transactions").json()
    assert tx["account_id"] == checking


def test_keeping_the_same_name_is_fine(client):
    checking = create(client, "Checking")

    assert rename(client, checking, "Checking").status_code == 200


def test_name_of_another_open_account_is_409(client):
    create(client, "Checking")
    savings = create(client, "Savings", "savings")

    response = rename(client, savings, "Checking")

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    # Nothing changed, and the session recovered: the list still works.
    assert sorted(a["name"] for a in client.get("/api/accounts").json()) == ["Checking", "Savings"]


def test_closed_accounts_can_share_a_name_with_an_open_one(client, db_session):
    # Only OPEN account names must be unique (the partial index), so an old closed "Visa"
    # and a new open "Visa" can live side by side.
    old_card = closed_account(db_session, "Old card")
    create(client, "Visa", "credit_card")

    assert rename(client, old_card, "Visa").status_code == 200


def test_open_account_can_take_a_closed_accounts_name(client, db_session):
    closed_account(db_session, "Visa")
    new_card = create(client, "New card", "credit_card")

    assert rename(client, new_card, "Visa").status_code == 200


def test_missing_account_is_404(client):
    assert rename(client, 999, "Anything").status_code == 404


def test_blank_name_is_422(client):
    checking = create(client, "Checking")

    assert rename(client, checking, "   ").status_code == 422


def test_unknown_fields_are_422(client):
    checking = create(client, "Checking")

    response = client.patch(f"/api/accounts/{checking}", json={"balance_cents": 100})

    assert response.status_code == 422  # balances come from transactions, never set directly


# ---- changing the type ----

def change(client, account_id, **fields):
    return client.patch(f"/api/accounts/{account_id}", json=fields)


def test_change_only_the_type(client):
    card = create(client, "Store card", "checking")  # created with the wrong type

    response = change(client, card, type="credit_card")

    assert response.status_code == 200
    assert (response.json()["name"], response.json()["type"]) == ("Store card", "credit_card")


def test_change_name_and_type_together(client):
    account = create(client, "Checking")

    body = change(client, account, name="Emergency fund", type="savings").json()

    assert (body["name"], body["type"]) == ("Emergency fund", "savings")


def test_type_change_keeps_balance_and_transactions(client):
    account = create(client, "Checking")
    client.post("/api/transactions", json={"account_id": account, "date": "2026-10-01", "amount_cents": -2500})

    change(client, account, type="credit_card")

    [listed] = client.get("/api/accounts").json()
    assert (listed["type"], listed["balance_cents"]) == ("credit_card", -2500)
    assert len(client.get("/api/transactions", params={"account_id": account}).json()) == 1


def test_unknown_type_is_422(client):
    account = create(client, "Checking")

    assert change(client, account, type="piggy_bank").status_code == 422


def test_null_type_or_name_is_422(client):
    account = create(client, "Checking")

    assert change(client, account, type=None).status_code == 422
    assert change(client, account, name=None).status_code == 422


def test_empty_body_changes_nothing(client):
    account = create(client, "Checking")

    body = change(client, account).json()

    assert (body["name"], body["type"]) == ("Checking", "checking")


def test_failed_rename_does_not_change_the_type_either(client):
    create(client, "Checking")
    savings = create(client, "Savings", "savings")

    response = change(client, savings, name="Checking", type="cash")

    assert response.status_code == 409
    # All or nothing: the rollback undid the type change too.
    listed = {a["name"]: a["type"] for a in client.get("/api/accounts").json()}
    assert listed == {"Checking": "checking", "Savings": "savings"}
