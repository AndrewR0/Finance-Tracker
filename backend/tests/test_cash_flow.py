from datetime import date

import pytest

from app.reports import last_n_months


# ======================= last_n_months (your code): plain unit tests =======================

def test_three_months_within_a_year():
    assert last_n_months(date(2026, 10, 31), 3) == ["2026-08", "2026-09", "2026-10"]


def test_crosses_into_the_previous_year():
    assert last_n_months(date(2026, 2, 15), 3) == ["2025-12", "2026-01", "2026-02"]


def test_january_end():
    assert last_n_months(date(2026, 1, 1), 2) == ["2025-12", "2026-01"]


def test_one_month_is_just_the_end_month():
    assert last_n_months(date(2026, 10, 5), 1) == ["2026-10"]


def test_twelve_months_ends_on_the_end_month_and_starts_eleven_before():
    months = last_n_months(date(2026, 10, 31), 12)

    assert len(months) == 12
    assert months[0] == "2025-11"
    assert months[-1] == "2026-10"


def test_more_than_a_year_back():
    months = last_n_months(date(2026, 3, 1), 27)

    assert months[0] == "2024-01"
    assert len(set(months)) == 27  # no duplicates
    assert months == sorted(months)  # oldest first


# ======================= the endpoint =======================

@pytest.fixture
def ids(client):
    def post(url, **body):
        return client.post(url, json=body).json()["id"]

    return {
        "checking": post("/api/accounts", name="Checking", type="checking"),
        "visa": post("/api/accounts", name="Visa", type="credit_card"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
        "food": post("/api/categories", name="Food", kind="expense"),
    }


def add(client, account, amount_cents, category, date):
    response = client.post("/api/transactions", json={
        "account_id": account, "date": date, "amount_cents": amount_cents, "category_id": category,
    })
    assert response.status_code == 201, response.json()


def cash_flow(client, **params):
    response = client.get("/api/dashboard/cash-flow", params={"end": "2026-10-31", **params})
    assert response.status_code == 200, response.json()
    return response.json()


def test_every_month_is_present_even_with_no_transactions(client, ids):
    rows = cash_flow(client)

    assert [r["month"] for r in rows] == last_n_months(date(2026, 10, 31), 12)
    assert all(r["income_cents"] == r["spending_cents"] == r["saved_cents"] == 0 for r in rows)


def test_each_month_gets_its_own_totals(client, ids):
    add(client, ids["checking"], 270000, ids["paycheck"], "2026-09-15")
    add(client, ids["visa"], -50000, ids["food"], "2026-09-20")
    add(client, ids["checking"], 270000, ids["paycheck"], "2026-10-15")
    add(client, ids["visa"], -80000, ids["food"], "2026-10-02")

    by_month = {r["month"]: r for r in cash_flow(client, months=2)}

    assert by_month["2026-09"] == {"month": "2026-09", "income_cents": 270000,
                                   "spending_cents": 50000, "saved_cents": 220000}
    assert by_month["2026-10"]["spending_cents"] == 80000
    assert by_month["2026-10"]["saved_cents"] == 190000


def test_month_boundaries(client, ids):
    add(client, ids["visa"], -1, ids["food"], "2026-09-30")
    add(client, ids["visa"], -20, ids["food"], "2026-10-01")
    add(client, ids["visa"], -300, ids["food"], "2026-10-31")

    rows = cash_flow(client, months=2)

    assert [r["spending_cents"] for r in rows] == [1, 320]


def test_ignores_before_the_range_and_after_end(client, ids):
    add(client, ids["visa"], -999, ids["food"], "2026-08-31")  # before a 2-month window
    add(client, ids["visa"], -50, ids["food"], "2026-10-20")
    add(client, ids["visa"], -777, ids["food"], "2026-11-01")  # after end

    rows = cash_flow(client, months=2)

    assert [r["spending_cents"] for r in rows] == [0, 50]


def test_transfers_are_left_out(client, ids):
    client.post("/api/transfers", json={
        "from_account_id": ids["checking"], "to_account_id": ids["visa"],
        "date": "2026-10-20", "amount_cents": 61200,
    })

    assert cash_flow(client, months=1) == [
        {"month": "2026-10", "income_cents": 0, "spending_cents": 0, "saved_cents": 0}
    ]


def test_matches_the_summary_for_the_same_month(client, ids):
    add(client, ids["checking"], 270000, ids["paycheck"], "2026-10-15")
    add(client, ids["visa"], -8412, ids["food"], "2026-10-02")
    add(client, ids["visa"], 2500, ids["food"], "2026-10-05")  # refund

    october = cash_flow(client, months=1)[0]
    summary = client.get("/api/dashboard/summary", params={"start": "2026-10-01", "end": "2026-10-31"}).json()

    assert october["income_cents"] == summary["income_cents"]
    assert october["spending_cents"] == summary["spending_cents"]


@pytest.mark.parametrize("months", [0, -1, 121])
def test_months_out_of_range_is_rejected(client, months):
    response = client.get("/api/dashboard/cash-flow", params={"end": "2026-10-31", "months": months})

    assert response.status_code == 422
