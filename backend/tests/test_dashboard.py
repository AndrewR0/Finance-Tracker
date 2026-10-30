import pytest

OCTOBER = {"start": "2026-10-01", "end": "2026-10-31"}


@pytest.fixture
def setup(client):
    """Two accounts and one category of each kind. Returns a dict of ids."""
    def post(url, **body):
        return client.post(url, json=body).json()["id"]

    food = post("/api/categories", name="Food", kind="expense")
    return {
        "checking": post("/api/accounts", name="Checking", type="checking"),
        "visa": post("/api/accounts", name="Visa", type="credit_card"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
        "food": food,
        "groceries": post("/api/categories", name="Groceries", kind="expense", parent_id=food),
        "card_payment": post("/api/categories", name="Card payment", kind="transfer"),
    }


def add(client, account, amount_cents, category=None, date="2026-10-15"):
    response = client.post("/api/transactions", json={
        "account_id": account, "date": date, "amount_cents": amount_cents, "category_id": category,
    })
    assert response.status_code == 201, response.json()


def summary(client, **params):
    response = client.get("/api/dashboard/summary", params=params or OCTOBER)
    assert response.status_code == 200, response.json()
    return response.json()


# ---- the four numbers ----

def test_empty_month_is_all_zeros(client, setup):
    body = summary(client)

    assert body | {"start": None, "end": None} == {
        "start": None, "end": None,
        "net_worth_cents": 0, "net_worth_change_cents": 0,
        "income_cents": 0, "spending_cents": 0, "saved_cents": 0,
        "income_change": None, "spending_change": None, "saved_change": None,
    }


def test_income_and_expense_categories(client, setup):
    add(client, setup["checking"], 270000, setup["paycheck"])
    add(client, setup["checking"], -8412, setup["groceries"])

    body = summary(client)

    assert body["income_cents"] == 270000
    assert body["spending_cents"] == 8412  # positive
    assert body["saved_cents"] == 270000 - 8412


def test_subcategory_counts_by_its_own_kind(client, setup):
    add(client, setup["visa"], -4630, setup["groceries"])  # a subcategory of Food

    assert summary(client)["spending_cents"] == 4630


def test_refund_reduces_spending_and_is_not_income(client, setup):
    add(client, setup["visa"], -6240, setup["food"])
    add(client, setup["visa"], 2500, setup["food"])  # refund

    body = summary(client)

    assert body["spending_cents"] == 3740
    assert body["income_cents"] == 0


def test_negative_income_lowers_income(client, setup):
    add(client, setup["checking"], 270000, setup["paycheck"])
    add(client, setup["checking"], -10000, setup["paycheck"])  # paycheck correction

    assert summary(client)["income_cents"] == 260000


def test_uncategorized_counts_by_sign(client, setup):
    add(client, setup["checking"], 4000)   # Venmo from a friend
    add(client, setup["checking"], -1500)  # cash withdrawal, not yet categorized

    body = summary(client)

    assert body["income_cents"] == 4000
    assert body["spending_cents"] == 1500


def test_transfers_are_neither_income_nor_spending(client, setup):
    client.post("/api/transfers", json={
        "from_account_id": setup["checking"], "to_account_id": setup["visa"],
        "date": "2026-10-20", "amount_cents": 61200, "category_id": setup["card_payment"],
    })

    body = summary(client)

    assert body["income_cents"] == 0
    assert body["spending_cents"] == 0


def test_spending_more_than_income_gives_negative_saved(client, setup):
    add(client, setup["checking"], 100000, setup["paycheck"])
    add(client, setup["visa"], -150000, setup["food"])

    assert summary(client)["saved_cents"] == -50000


# ---- dates ----

def test_only_transactions_in_the_range_count(client, setup):
    add(client, setup["visa"], -100, setup["food"], date="2026-09-30")  # before
    add(client, setup["visa"], -20, setup["food"], date="2026-10-01")   # first day
    add(client, setup["visa"], -3, setup["food"], date="2026-10-31")    # last day
    add(client, setup["visa"], -4000, setup["food"], date="2026-11-01")  # after

    assert summary(client)["spending_cents"] == 23


def test_start_after_end_is_rejected(client, setup):
    response = client.get("/api/dashboard/summary", params={"start": "2026-10-31", "end": "2026-10-01"})

    assert response.status_code == 422


# ---- net worth ----

def test_net_worth_includes_debts_and_history_before_the_range(client, setup):
    add(client, setup["checking"], 500000, setup["paycheck"], date="2026-01-15")  # before October
    add(client, setup["visa"], -182040, setup["food"], date="2026-10-10")          # card debt

    assert summary(client)["net_worth_cents"] == 500000 - 182040


def test_net_worth_ignores_transactions_after_the_end(client, setup):
    add(client, setup["checking"], 1000, setup["paycheck"], date="2026-10-31")
    add(client, setup["checking"], 99999, setup["paycheck"], date="2026-11-01")

    assert summary(client)["net_worth_cents"] == 1000


def test_transfers_do_not_change_net_worth(client, setup):
    add(client, setup["checking"], 100000, setup["paycheck"])
    client.post("/api/transfers", json={
        "from_account_id": setup["checking"], "to_account_id": setup["visa"],
        "date": "2026-10-20", "amount_cents": 61200,
    })

    assert summary(client)["net_worth_cents"] == 100000
