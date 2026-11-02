"""Reconciling a balance to a statement, and closing / reopening accounts."""

from datetime import datetime

from app.models import Account, AccountType


def create(client, name, type_="checking"):
    return client.post("/api/accounts", json={"name": name, "type": type_}).json()["id"]


def add(client, account_id, date, cents, category_id=None):
    response = client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": date, "amount_cents": cents, "category_id": category_id},
    )
    assert response.status_code == 201
    return response.json()


def reconcile(client, account_id, date, balance_cents):
    return client.post(f"/api/accounts/{account_id}/reconcile", json={"date": date, "balance_cents": balance_cents})


def balance(client, account_id, as_of=None):
    query = f"?as_of={as_of}" if as_of else ""
    return next(a["balance_cents"] for a in client.get(f"/api/accounts{query}").json() if a["id"] == account_id)


# ---- reconcile ----

def test_reconcile_adds_the_difference_as_an_adjustment(client):
    checking = create(client, "Checking")
    add(client, checking, "2026-10-01", 100_000)
    add(client, checking, "2026-10-05", -2_500)

    response = reconcile(client, checking, "2026-10-31", 96_000)  # the bank says $960; the app says $975

    assert response.status_code == 200
    body = response.json()
    assert body["previous_balance_cents"] == 97_500
    assert body["balance_cents"] == 96_000
    assert body["adjustment"]["amount_cents"] == -1_500
    assert body["adjustment"]["is_adjustment"] is True
    assert body["adjustment"]["date"] == "2026-10-31"
    assert balance(client, checking) == 96_000


def test_matching_balance_adds_nothing(client):
    checking = create(client, "Checking")
    add(client, checking, "2026-10-01", 5_000)

    body = reconcile(client, checking, "2026-10-31", 5_000).json()

    assert body["adjustment"] is None
    assert len(client.get("/api/transactions").json()) == 1


def test_reconcile_uses_the_balance_on_that_date(client):
    # A later transaction must not affect a statement from earlier.
    checking = create(client, "Checking")
    add(client, checking, "2026-09-01", 10_000)
    add(client, checking, "2026-10-15", -4_000)

    body = reconcile(client, checking, "2026-09-30", 10_200).json()

    assert body["adjustment"]["amount_cents"] == 200
    assert balance(client, checking, "2026-09-30") == 10_200
    assert balance(client, checking) == 6_200  # the October spending still counts afterwards


def test_credit_card_owed_is_negative(client):
    visa = create(client, "Visa", "credit_card")
    add(client, visa, "2026-10-03", -12_000)

    body = reconcile(client, visa, "2026-10-31", -12_550).json()  # the statement says you owe $125.50

    assert body["adjustment"]["amount_cents"] == -550


def test_adjustments_are_not_income_or_spending(client, today):
    checking = create(client, "Checking")
    add(client, checking, "2026-10-01", 100_000)
    reconcile(client, checking, "2026-10-10", 90_000)  # -$100 adjustment
    reconcile(client, checking, "2026-10-12", 95_000)  # +$50 adjustment

    summary = client.get("/api/dashboard/summary?start=2026-10-01&end=2026-10-31").json()

    assert summary["income_cents"] == 100_000  # only the real deposit
    assert summary["spending_cents"] == 0
    assert summary["net_worth_cents"] == 95_000  # but the balance does change
    by_category = client.get("/api/dashboard/spending-by-category?start=2026-10-01&end=2026-10-31").json()
    assert by_category == []
    [month] = client.get("/api/dashboard/cash-flow?end=2026-10-31&months=1").json()
    assert (month["income_cents"], month["spending_cents"]) == (100_000, 0)
    pace = client.get("/api/dashboard/spending-pace?kind=month&date=2026-10-23").json()
    assert pace["spent_cents"] == 0


def test_an_adjustment_can_be_deleted_like_any_transaction(client):
    checking = create(client, "Checking")
    adjustment = reconcile(client, checking, "2026-10-31", 700).json()["adjustment"]

    assert client.delete(f"/api/transactions/{adjustment['id']}").status_code == 204
    assert balance(client, checking) == 0


def test_ordinary_transactions_are_not_adjustments(client):
    checking = create(client, "Checking")

    assert add(client, checking, "2026-10-01", 100)["is_adjustment"] is False


def test_reconcile_missing_account_is_404(client):
    assert reconcile(client, 999, "2026-10-31", 0).status_code == 404


def test_reconcile_closed_account_is_409(client, db_session):
    old = Account(name="Old", type=AccountType.CHECKING, closed_at=datetime(2025, 1, 1))
    db_session.add(old)
    db_session.commit()

    assert reconcile(client, old.id, "2026-10-31", 100).status_code == 409


def test_reconcile_rejects_dollar_amounts(client):
    checking = create(client, "Checking")

    assert reconcile(client, checking, "2026-10-31", 12.5).status_code == 422


# ---- close / reopen ----

def test_close_an_empty_account(client, today):
    visa = create(client, "Visa", "credit_card")

    response = client.post(f"/api/accounts/{visa}/close")

    assert response.status_code == 200
    assert response.json()["closed_at"].startswith("2026-10-23")


def test_close_needs_a_zero_balance(client, today):
    visa = create(client, "Visa", "credit_card")
    add(client, visa, "2026-10-03", -12_345)

    response = client.post(f"/api/accounts/{visa}/close")

    assert response.status_code == 409
    assert "-$123.45" in response.json()["detail"]
    assert client.get("/api/accounts").json()[0]["closed_at"] is None


def test_closed_account_keeps_its_history_and_takes_no_new_transactions(client, today):
    visa = create(client, "Visa", "credit_card")
    add(client, visa, "2026-10-03", -500)
    add(client, visa, "2026-10-20", 500)  # paid off
    client.post(f"/api/accounts/{visa}/close")

    assert len(client.get(f"/api/transactions?account_id={visa}").json()) == 2
    response = client.post("/api/transactions", json={"account_id": visa, "date": "2026-10-23", "amount_cents": -1})
    assert response.status_code == 422


def test_closing_twice_is_fine(client, today):
    visa = create(client, "Visa", "credit_card")
    first = client.post(f"/api/accounts/{visa}/close").json()

    again = client.post(f"/api/accounts/{visa}/close")

    assert again.status_code == 200
    assert again.json()["closed_at"] == first["closed_at"]


def test_reopen(client, today):
    visa = create(client, "Visa", "credit_card")
    client.post(f"/api/accounts/{visa}/close")

    response = client.post(f"/api/accounts/{visa}/reopen")

    assert response.status_code == 200
    assert response.json()["closed_at"] is None


def test_reopen_with_a_name_now_taken_is_409(client, today):
    old = create(client, "Visa", "credit_card")
    client.post(f"/api/accounts/{old}/close")
    create(client, "Visa", "credit_card")  # a new card with the same name

    response = client.post(f"/api/accounts/{old}/reopen")

    assert response.status_code == 409
    assert "Rename" in response.json()["detail"]
    closed = [a for a in client.get("/api/accounts").json() if a["id"] == old]
    assert closed[0]["closed_at"] is not None


def test_close_missing_account_is_404(client, today):
    assert client.post("/api/accounts/999/close").status_code == 404
    assert client.post("/api/accounts/999/reopen").status_code == 404
