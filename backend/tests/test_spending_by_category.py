import pytest

from app.reports import roll_up


# ======================= roll_up (your code): plain unit tests =======================
#   Category ids used below:  1 = Food (top)   5 = Groceries (sub of 1)   6 = Coffee (sub of 1)
#                             2 = Bills (top)  7 = Phone (sub of 2)
PARENT_OF = {1: None, 5: 1, 6: 1, 2: None, 7: 2}


def test_subcategories_add_into_their_parent():
    assert roll_up({5: 300, 6: 200}, PARENT_OF) == {1: 500}


def test_parent_direct_spending_and_subcategories_both_count():
    assert roll_up({1: 1000, 5: 300}, PARENT_OF) == {1: 1300}


def test_each_parent_gets_only_its_own_subcategories():
    assert roll_up({5: 300, 7: 65}, PARENT_OF) == {1: 300, 2: 65}


def test_uncategorized_stays_under_none():
    assert roll_up({None: 40, 5: 10}, PARENT_OF) == {None: 40, 1: 10}


def test_refunds_can_make_a_total_negative_or_zero():
    assert roll_up({5: 300, 6: -300}, PARENT_OF) == {1: 0}


def test_nothing_in_nothing_out():
    assert roll_up({}, PARENT_OF) == {}


# ======================= the endpoint =======================

@pytest.fixture
def ids(client):
    def post(url, **body):
        return client.post(url, json=body).json()["id"]

    food = post("/api/categories", name="Food", kind="expense")
    bills = post("/api/categories", name="Bills", kind="expense")
    return {
        "visa": post("/api/accounts", name="Visa", type="credit_card"),
        "checking": post("/api/accounts", name="Checking", type="checking"),
        "food": food,
        "groceries": post("/api/categories", name="Groceries", kind="expense", parent_id=food),
        "coffee": post("/api/categories", name="Coffee", kind="expense", parent_id=food),
        "bills": bills,
        "phone": post("/api/categories", name="Phone", kind="expense", parent_id=bills),
        "travel": post("/api/categories", name="Travel", kind="expense"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
    }


def add(client, ids, amount_cents, category=None, date="2026-10-15", account="visa"):
    response = client.post("/api/transactions", json={
        "account_id": ids[account], "date": date, "amount_cents": amount_cents, "category_id": category,
    })
    assert response.status_code == 201, response.json()


OCT = {"start": "2026-10-01", "end": "2026-10-31"}
OCT_VS_SEP = OCT | {"compare_start": "2026-09-01", "compare_end": "2026-09-30"}


def report(client, params=OCT):
    response = client.get("/api/dashboard/spending-by-category", params=params)
    assert response.status_code == 200, response.json()
    return response.json()


def test_parent_total_includes_subcategories_and_direct_spending(client, ids):
    add(client, ids, -40200, ids["groceries"])
    add(client, ids, -1500, ids["coffee"])
    add(client, ids, -2000, ids["food"])  # categorized as Food itself

    food = report(client)[0]

    assert food["name"] == "Food"
    assert food["spending_cents"] == 43700
    assert [(s["name"], s["spending_cents"]) for s in food["subcategories"]] == [
        ("Groceries", 40200), ("Coffee", 1500),
    ]


def test_biggest_category_first_and_empty_ones_hidden(client, ids):
    add(client, ids, -1000, ids["groceries"])
    add(client, ids, -6500, ids["phone"])
    # Travel has nothing: not listed

    assert [r["name"] for r in report(client)] == ["Bills", "Food"]


def test_uncategorized_spending_gets_its_own_row(client, ids):
    add(client, ids, -700)

    rows = report(client)

    assert rows == [{"category_id": None, "name": "Uncategorized", "spending_cents": 700,
                     "previous_cents": None, "subcategories": []}]


def test_refunds_reduce_and_income_and_transfers_are_left_out(client, ids):
    add(client, ids, -6240, ids["groceries"])
    add(client, ids, 2500, ids["groceries"])  # refund
    add(client, ids, 270000, ids["paycheck"], account="checking")
    client.post("/api/transfers", json={
        "from_account_id": ids["checking"], "to_account_id": ids["visa"],
        "date": "2026-10-20", "amount_cents": 61200,
    })

    rows = report(client)

    assert [(r["name"], r["spending_cents"]) for r in rows] == [("Food", 3740)]


def test_total_matches_the_summary(client, ids):
    add(client, ids, -40200, ids["groceries"])
    add(client, ids, -6500, ids["phone"])
    add(client, ids, -700)
    add(client, ids, 1000, ids["coffee"])  # refund

    total = sum(r["spending_cents"] for r in report(client))
    summary = client.get("/api/dashboard/summary", params=OCT).json()

    assert total == summary["spending_cents"]


def test_previous_period_is_filled_in_when_asked(client, ids):
    add(client, ids, -54000, ids["groceries"], date="2026-09-10")
    add(client, ids, -61200, ids["groceries"], date="2026-10-10")

    food = report(client, OCT_VS_SEP)[0]

    assert food["spending_cents"] == 61200
    assert food["previous_cents"] == 54000
    assert food["subcategories"][0]["previous_cents"] == 54000


def test_previous_is_none_without_a_compare_period(client, ids):
    add(client, ids, -100, ids["groceries"])

    assert report(client)[0]["previous_cents"] is None


def test_category_with_only_previous_spending_still_shows(client, ids):
    add(client, ids, -184000, ids["travel"], date="2026-09-05")

    rows = report(client, OCT_VS_SEP)

    assert rows == [{"category_id": ids["travel"], "name": "Travel", "spending_cents": 0,
                     "previous_cents": 184000, "subcategories": []}]


@pytest.mark.parametrize("params", [
    {"start": "2026-10-31", "end": "2026-10-01"},
    OCT | {"compare_start": "2026-09-01"},  # only half of the compare range
    OCT | {"compare_start": "2026-09-30", "compare_end": "2026-09-01"},
])
def test_bad_date_ranges_are_rejected(client, params):
    assert client.get("/api/dashboard/spending-by-category", params=params).status_code == 422
