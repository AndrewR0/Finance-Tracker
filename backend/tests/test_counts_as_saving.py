"""Categories that count as saving: money moved to a Roth IRA or brokerage is saved, not spent."""

import pytest

OCTOBER = {"start": "2026-10-01", "end": "2026-10-31"}


@pytest.fixture
def setup(client):
    def post(url, **body):
        response = client.post(url, json=body)
        assert response.status_code == 201, response.json()
        return response.json()["id"]

    savings = post("/api/categories", name="Savings (Extra)", kind="expense")
    roth = post("/api/categories", name="Roth IRA", kind="expense", parent_id=savings)
    response = client.patch(f"/api/categories/{savings}", json={"counts_as_saving": True})
    assert response.status_code == 200, response.json()
    return {
        "checking": post("/api/accounts", name="Checking", type="checking"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
        "food": post("/api/categories", name="Food", kind="expense"),
        "savings": savings,
        "roth": roth,
    }


def add(client, account, amount_cents, category, date="2026-10-15"):
    response = client.post("/api/transactions", json={
        "account_id": account, "date": date, "amount_cents": amount_cents, "category_id": category,
    })
    assert response.status_code == 201, response.json()


def category(client, category_id):
    for top in client.get("/api/categories").json():
        for c in [top, *top["subcategories"]]:
            if c["id"] == category_id:
                return c
    raise AssertionError(f"category {category_id} not found")


# ---- dashboard numbers ----

def test_contribution_is_saved_not_spent(client, setup):
    add(client, setup["checking"], 300000, setup["paycheck"])
    add(client, setup["checking"], -10000, setup["food"])
    add(client, setup["checking"], -50000, setup["roth"])

    body = client.get("/api/dashboard/summary", params=OCTOBER).json()

    assert body["income_cents"] == 300000
    assert body["spending_cents"] == 10000  # the Roth contribution is not spending
    assert body["saved_cents"] == 290000  # so it shows up in saved
    assert body["moved_to_savings_cents"] == 50000


def test_taking_money_back_out_lowers_moved_to_savings(client, setup):
    add(client, setup["checking"], -50000, setup["roth"])
    add(client, setup["checking"], 20000, setup["roth"])  # withdrew a contribution

    body = client.get("/api/dashboard/summary", params=OCTOBER).json()

    assert body["moved_to_savings_cents"] == 30000
    assert body["spending_cents"] == 0


def test_cash_flow_counts_contribution_as_saved(client, setup):
    add(client, setup["checking"], 300000, setup["paycheck"])
    add(client, setup["checking"], -50000, setup["roth"])

    october = client.get("/api/dashboard/cash-flow", params={"end": "2026-10-31", "months": 1}).json()[0]

    assert october["spending_cents"] == 0
    assert october["saved_cents"] == 300000


def test_saving_category_left_out_of_spending_by_category(client, setup):
    add(client, setup["checking"], -10000, setup["food"])
    add(client, setup["checking"], -50000, setup["roth"])

    rows = client.get("/api/dashboard/spending-by-category", params=OCTOBER).json()

    assert [r["name"] for r in rows] == ["Food"]


def test_turning_it_off_makes_it_spending_again(client, setup):
    add(client, setup["checking"], -50000, setup["roth"])
    client.patch(f"/api/categories/{setup['savings']}", json={"counts_as_saving": False})

    body = client.get("/api/dashboard/summary", params=OCTOBER).json()

    assert body["spending_cents"] == 50000
    assert body["moved_to_savings_cents"] == 0


# ---- the setting itself ----

def test_subcategories_follow_their_parent(client, setup):
    assert category(client, setup["roth"])["counts_as_saving"] is True

    client.patch(f"/api/categories/{setup['savings']}", json={"counts_as_saving": False})

    assert category(client, setup["roth"])["counts_as_saving"] is False


def test_new_subcategory_copies_its_parent(client, setup):
    new = client.post("/api/categories", json={"name": "Brokerage", "kind": "expense", "parent_id": setup["savings"]})

    assert new.json()["counts_as_saving"] is True


def test_moving_a_subcategory_takes_the_new_parents_setting(client, setup):
    client.patch(f"/api/categories/{setup['roth']}", json={"parent_id": setup["food"]})
    assert category(client, setup["roth"])["counts_as_saving"] is False

    client.patch(f"/api/categories/{setup['roth']}", json={"parent_id": setup["savings"]})
    assert category(client, setup["roth"])["counts_as_saving"] is True


def test_only_set_on_a_top_level_category(client, setup):
    response = client.patch(f"/api/categories/{setup['roth']}", json={"counts_as_saving": False})

    assert response.status_code == 422
    assert "Savings (Extra)" in response.json()["detail"]


def test_only_expense_categories_can_count_as_saving(client, setup):
    response = client.patch(f"/api/categories/{setup['paycheck']}", json={"counts_as_saving": True})

    assert response.status_code == 422


def test_off_by_default(client, setup):
    assert category(client, setup["food"])["counts_as_saving"] is False


def test_include_saving_lists_saving_categories_with_amount_moved(client, setup):
    add(client, setup["checking"], -10000, setup["food"])
    add(client, setup["checking"], -50000, setup["roth"])
    add(client, setup["checking"], -20000, setup["roth"], date="2026-09-15")

    rows = client.get("/api/dashboard/spending-by-category", params={
        **OCTOBER, "compare_start": "2026-09-01", "compare_end": "2026-09-30", "include_saving": "true",
    }).json()

    savings = next(r for r in rows if r["name"] == "Savings (Extra)")
    assert savings["counts_as_saving"] is True
    assert savings["spending_cents"] == 50000
    assert savings["previous_cents"] == 20000
    assert savings["subcategories"][0] | {"category_id": 0} == {
        "category_id": 0, "name": "Roth IRA", "spending_cents": 50000, "previous_cents": 20000, "counts_as_saving": True,
    }
    food = next(r for r in rows if r["name"] == "Food")
    assert food["counts_as_saving"] is False and food["spending_cents"] == 10000
