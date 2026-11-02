"""Import endpoints: preview (duplicates, suggested categories) and commit (all or nothing),
for a bank statement (one account) and for your own spreadsheet (accounts and categories per row)."""

from datetime import datetime

from app.models import Account, AccountType


def account(client, name="Checking", type_="checking"):
    return client.post("/api/accounts", json={"name": name, "type": type_}).json()["id"]


def category(client, name, kind="expense", parent_id=None):
    return client.post("/api/categories", json={"name": name, "kind": kind, "parent_id": parent_id}).json()["id"]


def add(client, account_id, date, cents, payee=None, category_id=None):
    client.post(
        "/api/transactions",
        json={"account_id": account_id, "date": date, "amount_cents": cents, "payee": payee, "category_id": category_id},
    )


def row(date, cents, payee=None, **extra):
    return {"date": date, "amount_cents": cents, "payee": payee, **extra}


def preview(client, rows):
    return client.post("/api/import/preview", json={"rows": rows})


def commit(client, rows, new_accounts=(), new_categories=()):
    return client.post(
        "/api/import",
        json={"rows": rows, "new_accounts": list(new_accounts), "new_categories": list(new_categories)},
    )


def tree(client):
    """{"Food (expense)": ["Coffee"], ...}"""
    return {f"{c['name']} ({c['kind']})": [s["name"] for s in c["subcategories"]] for c in client.get("/api/categories").json()}


# ---- preview ----

def test_preview_saves_nothing_and_keeps_the_order(client):
    checking = account(client)

    response = preview(client, [row("2026-10-02", -500, "Coffee", account_id=checking), row("2026-10-01", 9000, "Paycheck", account_id=checking)])

    assert response.status_code == 200
    assert [r["payee"] for r in response.json()] == ["Coffee", "Paycheck"]
    assert client.get("/api/transactions").json() == []


def test_preview_compares_each_row_with_its_own_account(client):
    checking = account(client)
    visa = account(client, "Visa", "credit_card")
    add(client, checking, "2026-10-05", -500)
    add(client, visa, "2026-10-06", -900)

    body = preview(client, [
        row("2026-10-06", -500, account_id=checking),  # matches Checking's
        row("2026-10-06", -900, account_id=checking),  # Visa has this one, not Checking
        row("2026-10-06", -900, account_id=visa),  # matches Visa's
    ]).json()

    assert [r["duplicate"] for r in body] == [True, False, True]


def test_rows_for_a_new_account_are_never_duplicates(client):
    checking = account(client)
    add(client, checking, "2026-10-05", -500)

    [result] = preview(client, [row("2026-10-05", -500)]).json()  # no account_id: a new account

    assert result["duplicate"] is False


def test_preview_counts_transfer_legs_as_already_entered(client):
    # A credit-card payment typed in as a transfer also shows up on the bank's CSV.
    checking = account(client)
    visa = account(client, "Visa", "credit_card")
    client.post("/api/transfers", json={"from_account_id": checking, "to_account_id": visa,
                                        "date": "2026-10-10", "amount_cents": 20_000})

    [result] = preview(client, [row("2026-10-11", -20_000, "CHASE CARD PAYMENT", account_id=checking)]).json()

    assert result["duplicate"] is True


def test_preview_suggests_the_last_category_used_with_the_payee(client):
    checking = account(client)
    food = category(client, "Food")
    fun = category(client, "Fun")
    add(client, checking, "2026-09-01", -500, "Blue Bottle", fun)
    add(client, checking, "2026-09-20", -500, "Blue Bottle", food)  # newer: wins

    body = preview(client, [row("2026-10-01", -450, "blue bottle", account_id=checking), row("2026-10-01", -100, "Someone new", account_id=checking)]).json()

    assert [r["suggested_category_id"] for r in body] == [food, None]


def test_preview_of_nothing(client):
    assert preview(client, []).json() == []


def test_preview_needs_open_accounts(client):
    assert preview(client, [row("2026-10-01", -1, account_id=999)]).status_code == 422


# ---- commit: existing accounts and categories (a bank statement) ----

def test_commit_creates_transactions_and_payees(client):
    checking = account(client)
    food = category(client, "Food")

    response = commit(client, [
        row("2026-10-01", -500, "Blue Bottle", account=checking, category=food),
        row("2026-10-02", -450, "blue bottle", account=checking, notes="oat latte"),  # same payee, other spelling
        row("2026-10-03", 100_000, "Paycheck", account=checking),
    ])

    assert response.status_code == 201
    assert response.json() == {"created": 3, "created_accounts": 0, "created_categories": 0}
    saved = client.get("/api/transactions").json()
    assert [(t["amount_cents"], t["category_id"], t["notes"]) for t in saved] == [
        (100_000, None, None), (-450, None, "oat latte"), (-500, food, None),
    ]
    assert len({t["payee_id"] for t in saved if t["payee_name"].lower() == "blue bottle"}) == 1


def test_commit_reuses_payees_that_already_exist(client):
    checking = account(client)
    add(client, checking, "2026-09-01", -500, "Blue Bottle")

    commit(client, [row("2026-10-01", -500, "BLUE BOTTLE", account=checking)])

    assert len({t["payee_id"] for t in client.get("/api/transactions").json()}) == 1


def test_imported_transactions_count_on_the_dashboard(client):
    checking = account(client)
    food = category(client, "Food")
    commit(client, [row("2026-10-01", -2_500, "Market", account=checking, category=food)])

    summary = client.get("/api/dashboard/summary?start=2026-10-01&end=2026-10-31").json()

    assert summary["spending_cents"] == 2_500


def test_one_bad_category_saves_nothing(client):
    checking = account(client)
    moves = category(client, "Moves", "transfer")

    response = commit(client, [row("2026-10-01", -500, account=checking), row("2026-10-02", -500, account=checking, category=moves)])

    assert response.status_code == 422
    assert client.get("/api/transactions").json() == []


def test_missing_category_saves_nothing(client):
    checking = account(client)

    response = commit(client, [row("2026-10-01", -500, account=checking, category=999)])

    assert response.status_code == 422
    assert client.get("/api/transactions").json() == []


def test_commit_needs_at_least_one_row(client):
    assert commit(client, []).status_code == 422


def test_commit_rejects_dollar_amounts(client):
    assert commit(client, [row("2026-10-01", -5.25, account=account(client))]).status_code == 422


def test_commit_to_a_closed_account_is_422(client, db_session):
    old = Account(name="Old", type=AccountType.CHECKING, closed_at=datetime(2025, 1, 1))
    db_session.add(old)
    db_session.commit()

    assert commit(client, [row("2026-10-01", -500, account=old.id)]).status_code == 422


# ---- commit: new accounts and categories (your own spreadsheet) ----

def test_new_accounts_and_categories_are_created_and_used(client):
    checking = account(client)
    food = category(client, "Food")

    response = commit(
        client,
        rows=[
            row("2023-01-05", -1_200, "Cafe", account="account:Amex", category="category:Food>Coffee"),
            row("2023-01-06", -8_000, "Market", account=checking, category=food),
            row("2023-01-31", 300_000, "Acme", account=checking, category="category:Salary"),
        ],
        new_accounts=[{"key": "account:Amex", "name": "Amex", "type": "credit_card"}],
        new_categories=[
            {"key": "category:Food>Coffee", "name": "Coffee", "kind": "expense", "parent": food},
            {"key": "category:Salary", "name": "Salary", "kind": "income"},
        ],
    )

    assert response.status_code == 201
    assert response.json() == {"created": 3, "created_accounts": 1, "created_categories": 2}
    accounts = {a["name"]: a for a in client.get("/api/accounts").json()}
    assert accounts["Amex"]["type"] == "credit_card"
    assert accounts["Amex"]["balance_cents"] == -1_200
    assert tree(client) == {"Food (expense)": ["Coffee"], "Salary (income)": []}
    summary = client.get("/api/dashboard/summary?start=2023-01-01&end=2023-01-31").json()
    assert (summary["income_cents"], summary["spending_cents"]) == (300_000, 9_200)


def test_a_new_subcategory_under_a_new_category(client):
    checking = account(client)

    response = commit(
        client,
        rows=[row("2023-01-05", -1_200, account=checking, category="sub")],
        # Listed child first on purpose: the server creates parents first anyway.
        new_categories=[
            {"key": "sub", "name": "Coffee", "kind": "expense", "parent": "top"},
            {"key": "top", "name": "Food", "kind": "expense"},
        ],
    )

    assert response.status_code == 201
    assert tree(client) == {"Food (expense)": ["Coffee"]}


def test_a_new_category_with_an_existing_name_is_409_and_saves_nothing(client):
    account(client)
    category(client, "Food")

    response = commit(
        client,
        rows=[row("2023-01-05", -100, account="account:New")],
        new_accounts=[{"key": "account:New", "name": "New", "type": "cash"}],
        new_categories=[{"key": "x", "name": "Food", "kind": "expense"}],
    )

    assert response.status_code == 409
    assert [a["name"] for a in client.get("/api/accounts").json()] == ["Checking"]  # the new account was rolled back too
    assert client.get("/api/transactions").json() == []


def test_a_new_account_with_an_open_accounts_name_is_409(client):
    account(client, "Amex", "credit_card")

    response = commit(
        client,
        rows=[row("2023-01-05", -100, account="a")],
        new_accounts=[{"key": "a", "name": "Amex", "type": "credit_card"}],
    )

    assert response.status_code == 409


def test_a_bad_row_after_new_accounts_saves_nothing(client):
    response = commit(
        client,
        rows=[row("2023-01-05", -100, account="a"), row("2023-01-06", -100, account="a", category=999)],
        new_accounts=[{"key": "a", "name": "Amex", "type": "credit_card"}],
    )

    assert response.status_code == 422
    assert client.get("/api/accounts").json() == []


def test_unknown_keys_are_422(client):
    assert commit(client, [row("2023-01-05", -100, account="nope")]).status_code == 422
    checking = account(client)
    assert commit(client, [row("2023-01-05", -100, account=checking, category="nope")]).status_code == 422


def test_new_subcategory_kind_must_match_its_parent(client):
    checking = account(client)
    salary = category(client, "Salary", "income")

    response = commit(
        client,
        rows=[row("2023-01-05", -100, account=checking, category="c")],
        new_categories=[{"key": "c", "name": "Coffee", "kind": "expense", "parent": salary}],
    )

    assert response.status_code == 422
    assert tree(client) == {"Salary (income)": []}


def test_rows_cant_use_a_new_transfer_category(client):
    checking = account(client)

    response = commit(
        client,
        rows=[row("2023-01-05", -100, account=checking, category="t")],
        new_categories=[{"key": "t", "name": "Moves", "kind": "transfer"}],
    )

    assert response.status_code == 422
    assert tree(client) == {}


def test_duplicate_keys_are_422(client):
    response = commit(
        client,
        rows=[row("2023-01-05", -100, account="a")],
        new_accounts=[{"key": "a", "name": "One", "type": "cash"}, {"key": "a", "name": "Two", "type": "cash"}],
    )

    assert response.status_code == 422
