"""Budgets (today is Oct 23, 2026 in tests). Made-up numbers only."""

import pytest


@pytest.fixture
def setup(client, today):
    def post(url, **body):
        response = client.post(url, json=body)
        assert response.status_code == 201, response.json()
        return response.json()["id"]

    food = post("/api/categories", name="Food", kind="expense")
    return {
        "checking": post("/api/accounts", name="Checking", type="checking"),
        "food": food,
        "groceries": post("/api/categories", name="Groceries", kind="expense", parent_id=food),
        "dining": post("/api/categories", name="Dining", kind="expense", parent_id=food),
        "fun": post("/api/categories", name="Fun", kind="expense"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
    }


def add(client, setup, cents, category, date="2026-10-10"):
    response = client.post("/api/transactions", json={"account_id": setup["checking"], "date": date,
                                                      "amount_cents": cents, "category_id": setup[category]})
    assert response.status_code == 201, response.json()


def set_budget(client, category_id, cents, month="2026-10-01"):
    response = client.put(f"/api/budgets/{category_id}", json={"month": month, "amount_cents": cents})
    assert response.status_code == 200, response.json()
    return response.json()


def view(client, month=None):
    response = client.get("/api/budgets", params={"month": month} if month else {})
    assert response.status_code == 200, response.json()
    body = response.json()
    body["by_name"] = {r["name"]: r for r in body["rows"]}
    return body


def test_spent_vs_budget_with_a_parent_covering_its_subcategories(client, setup):
    add(client, setup, -30000, "groceries")
    add(client, setup, -12000, "dining")
    add(client, setup, -5000, "fun")
    set_budget(client, setup["food"], 50000)

    body = view(client)

    assert body["month"] == "2026-10-01"
    assert body["by_name"]["Food"]["budget_cents"] == 50000
    assert body["by_name"]["Food"]["spent_cents"] == 42000  # groceries + dining
    assert body["by_name"]["Fun"]["budget_cents"] is None
    assert body["budgeted_cents"] == 50000
    assert body["spent_budgeted_cents"] == 42000
    assert body["unbudgeted_cents"] == 5000  # Fun has no budget
    assert body["total_spent_cents"] == 47000


def test_a_subcategory_budget_inside_a_budgeted_parent_isnt_counted_twice(client, setup):
    add(client, setup, -30000, "groceries")
    set_budget(client, setup["food"], 50000)
    set_budget(client, setup["groceries"], 35000)

    body = view(client)

    assert body["by_name"]["Groceries"]["budget_cents"] == 35000
    assert body["budgeted_cents"] == 50000  # the parent's budget already covers groceries
    assert body["spent_budgeted_cents"] == 30000


def test_subcategory_budget_alone_covers_just_itself(client, setup):
    add(client, setup, -30000, "groceries")
    add(client, setup, -12000, "dining")
    set_budget(client, setup["groceries"], 35000)

    body = view(client)

    assert body["spent_budgeted_cents"] == 30000
    assert body["unbudgeted_cents"] == 12000


def test_refunds_lower_spending(client, setup):
    add(client, setup, -30000, "groceries")
    add(client, setup, 5000, "groceries")  # refund
    set_budget(client, setup["food"], 50000)

    assert view(client)["by_name"]["Food"]["spent_cents"] == 25000


def test_a_change_applies_from_that_month_on(client, setup):
    set_budget(client, setup["food"], 50000, month="2026-09-01")
    set_budget(client, setup["food"], 60000, month="2026-11-15")  # any day in the month

    assert view(client, "2026-09-01")["by_name"]["Food"]["budget_cents"] == 50000
    assert view(client, "2026-10-01")["by_name"]["Food"]["budget_cents"] == 50000  # still September's
    assert view(client, "2026-12-01")["by_name"]["Food"]["budget_cents"] == 60000


def test_removing_a_budget_from_a_month_on(client, setup):
    set_budget(client, setup["food"], 50000, month="2026-09-01")
    set_budget(client, setup["food"], None, month="2026-10-01")

    assert view(client, "2026-09-01")["by_name"]["Food"]["budget_cents"] == 50000
    assert view(client)["by_name"]["Food"]["budget_cents"] is None


def test_pace_days(client, setup):
    assert (view(client)["days_elapsed"], view(client)["days_in_month"]) == (23, 31)  # Oct 23
    assert view(client, "2026-09-01")["days_elapsed"] == 30  # a past month is all elapsed
    assert view(client, "2026-12-01")["days_elapsed"] == 0


def test_suggestion_is_the_average_of_the_previous_6_months(client, setup):
    for month in ("2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"):
        add(client, setup, -60000, "groceries", date=f"{month}-15")
    add(client, setup, -99900, "groceries", date="2026-10-05")  # this month: not part of the suggestion

    body = view(client)

    assert body["by_name"]["Groceries"]["suggested_cents"] == 60000
    assert body["by_name"]["Food"]["suggested_cents"] == 60000  # rolled up into the parent


def test_only_spending_categories_can_have_budgets(client, setup):
    response = client.put(f"/api/budgets/{setup['paycheck']}", json={"month": "2026-10-01", "amount_cents": 100})

    assert response.status_code == 422
    assert "Paycheck" not in view(client)["by_name"]


def test_deleting_a_category_deletes_its_budgets(client, setup):
    set_budget(client, setup["fun"], 10000)

    assert client.delete(f"/api/categories/{setup['fun']}").status_code == 200
    assert "Fun" not in view(client)["by_name"]
