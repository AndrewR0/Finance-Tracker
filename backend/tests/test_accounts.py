from datetime import datetime

from app.models import Account, AccountType


def test_create_account_returns_the_saved_account(client):
    response = client.post("/api/accounts", json={"name": "Checking", "type": "checking"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Checking"
    assert body["type"] == "checking"
    assert body["created_at"] is not None
    assert body["closed_at"] is None


def test_created_account_shows_up_in_the_list(client):
    client.post("/api/accounts", json={"name": "Checking", "type": "checking"})

    response = client.get("/api/accounts")

    assert response.status_code == 200
    assert [a["name"] for a in response.json()] == ["Checking"]


def test_name_is_trimmed(client):
    response = client.post("/api/accounts", json={"name": "  Savings  ", "type": "savings"})

    assert response.json()["name"] == "Savings"


def test_blank_name_is_rejected(client):
    response = client.post("/api/accounts", json={"name": "   ", "type": "checking"})

    assert response.status_code == 422


def test_unknown_type_is_rejected(client):
    response = client.post("/api/accounts", json={"name": "Piggy bank", "type": "piggy"})

    assert response.status_code == 422


def test_duplicate_open_name_is_a_conflict(client):
    client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"})

    response = client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"})

    assert response.status_code == 409
    # The failed attempt must not break the session for the next request.
    assert len(client.get("/api/accounts").json()) == 1


def test_name_of_a_closed_account_can_be_reused(client, db_session):
    db_session.add(Account(name="Visa", type=AccountType.CREDIT_CARD, closed_at=datetime(2026, 3, 1)))
    db_session.commit()

    response = client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"})

    assert response.status_code == 201


def test_list_puts_open_accounts_first_then_sorts_by_name(client, db_session):
    db_session.add_all([
        Account(name="Old Card", type=AccountType.CREDIT_CARD, closed_at=datetime(2026, 1, 1)),
        Account(name="Savings", type=AccountType.SAVINGS),
        Account(name="Brokerage", type=AccountType.BROKERAGE),
    ])
    db_session.commit()

    names = [a["name"] for a in client.get("/api/accounts").json()]

    assert names == ["Brokerage", "Savings", "Old Card"]
