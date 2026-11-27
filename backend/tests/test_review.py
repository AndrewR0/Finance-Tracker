"""Year in Review (today is Oct 23, 2026 in tests). Made-up numbers only."""

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
        "roth": post("/api/accounts", name="Roth IRA", type="retirement"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
        "food": food,
        "groceries": post("/api/categories", name="Groceries", kind="expense", parent_id=food),
        "fun": post("/api/categories", name="Fun", kind="expense"),
    }


def add(client, setup, cents, category, date, payee=None):
    body = {"account_id": setup["checking"], "date": date, "amount_cents": cents, "category_id": setup[category]}
    if payee:
        body["payee"] = payee
    response = client.post("/api/transactions", json=body)
    assert response.status_code == 201, response.json()


def review(client, **params):
    response = client.get("/api/review", params=params)
    assert response.status_code == 200, response.json()
    return response.json()


def test_totals_and_the_same_days_last_year(client, setup):
    add(client, setup, 500000, "paycheck", "2026-02-01")
    add(client, setup, -100000, "groceries", "2026-03-01")
    add(client, setup, 400000, "paycheck", "2025-02-01")
    add(client, setup, -50000, "fun", "2025-10-01")
    add(client, setup, -99900, "fun", "2025-12-01")  # after Oct 23 last year: not "the same days"

    body = review(client)

    assert (body["year"], body["start"], body["end"], body["partial"]) == (2026, "2026-01-01", "2026-10-23", True)
    assert body["totals"]["income_cents"] == 500000
    assert body["totals"]["spending_cents"] == 100000
    assert body["totals"]["saved_cents"] == 400000
    assert body["previous"]["spending_cents"] == 50000
    assert body["transactions"] == 2
    assert [m["month"] for m in body["months"]][0] == "2026-01" and len(body["months"]) == 10


def test_a_finished_year_runs_to_december(client, setup):
    add(client, setup, -50000, "fun", "2025-12-01")

    body = review(client, year=2025)

    assert body["end"] == "2025-12-31" and body["partial"] is False
    assert body["previous"] is None  # no data in 2024
    assert len(body["months"]) == 12


def test_top_categories_roll_up_and_compare(client, setup):
    add(client, setup, -30000, "groceries", "2026-03-01")
    add(client, setup, -10000, "fun", "2026-04-01")
    add(client, setup, -20000, "groceries", "2025-03-01")

    tops = review(client)["top_categories"]

    assert [(t["name"], t["cents"], t["previous_cents"]) for t in tops] == [("Food", 30000, 20000), ("Fun", 10000, 0)]


def test_top_payees(client, setup):
    add(client, setup, -3000, "groceries", "2026-03-01", payee="Corner Market")
    add(client, setup, -4000, "groceries", "2026-04-01", payee="Corner Market")
    add(client, setup, -9000, "fun", "2026-05-01", payee="Cinema")

    payees = review(client)["top_payees"]

    assert [(p["name"], p["cents"], p["count"]) for p in payees] == [("Cinema", 9000, 1), ("Corner Market", 7000, 2)]


def test_transfers_into_investments_count_as_invested(client, setup):
    client.post("/api/transfers", json={"from_account_id": setup["checking"], "to_account_id": setup["roth"],
                                        "date": "2026-06-01", "amount_cents": 70000})

    body = review(client)

    assert body["totals"]["invested_cents"] == 70000
    assert body["totals"]["spending_cents"] == 0
    assert body["investments_start_cents"] == 0 and body["investments_end_cents"] == 70000


def test_net_worth_start_and_end(client, setup):
    add(client, setup, 100000, "paycheck", "2025-06-01")
    add(client, setup, 50000, "paycheck", "2026-06-01")

    body = review(client)

    assert (body["net_worth_start_cents"], body["net_worth_end_cents"]) == (100000, 150000)


def test_budget_track_record_counts_finished_months(client, setup):
    client.put(f"/api/budgets/{setup['food']}", json={"month": "2026-08-01", "amount_cents": 20000})
    add(client, setup, -15000, "groceries", "2026-08-10")  # under
    add(client, setup, -25000, "groceries", "2026-09-10")  # over
    add(client, setup, -99900, "groceries", "2026-10-10")  # October isn't over yet

    body = review(client)

    assert (body["budget_months_on_track"], body["budget_months_total"]) == (1, 2)


def test_years_listed_and_future_refused(client, setup):
    add(client, setup, -1000, "fun", "2024-05-01")

    assert review(client)["years"] == [2024, 2025, 2026]
    assert client.get("/api/review", params={"year": 2027}).status_code == 422


def test_no_sp500_prices_means_none(client, setup):
    assert review(client)["sp500_return_bp"] is None
