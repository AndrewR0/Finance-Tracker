import pytest

from app.reports import percent_change


# ======================= percent_change (your code): plain unit tests =======================

@pytest.mark.parametrize("now, before, expected", [
    (106, 100, 6.0),
    (50, 100, -50.0),
    (100, 100, 0.0),
    (0, 100, -100.0),        # spent nothing this time
    (1, 3, -66.7),           # rounded to 1 decimal
    (4, 3, 33.3),
    (500, 0, None),          # nothing before: can't divide by zero
    (0, 0, None),
    (200, -500, 140.0),      # -$5 -> +$2 went UP
    (-1000, -500, -100.0),   # -$5 -> -$10 went DOWN
    (-250, -500, 50.0),      # -$5 -> -$2.50 went UP (less negative)
])
def test_percent_change(now, before, expected):
    assert percent_change(now, before) == expected


# ======================= the endpoint =======================

OCT_VS_SEP = {"start": "2026-10-01", "end": "2026-10-23", "compare_start": "2026-09-01", "compare_end": "2026-09-23"}


@pytest.fixture
def ids(client):
    def post(url, **body):
        return client.post(url, json=body).json()["id"]

    return {
        "checking": post("/api/accounts", name="Checking", type="checking"),
        "paycheck": post("/api/categories", name="Paycheck", kind="income"),
        "food": post("/api/categories", name="Food", kind="expense"),
    }


def add(client, ids, amount_cents, category, date):
    response = client.post("/api/transactions", json={
        "account_id": ids["checking"], "date": date, "amount_cents": amount_cents, "category_id": ids[category],
    })
    assert response.status_code == 201, response.json()


def summary(client, params=OCT_VS_SEP):
    response = client.get("/api/dashboard/summary", params=params)
    assert response.status_code == 200, response.json()
    return response.json()


def test_changes_are_none_without_a_compare_range(client, ids):
    body = summary(client, {"start": "2026-10-01", "end": "2026-10-23"})

    assert body["income_change"] is body["spending_change"] is body["saved_change"] is None


def test_spending_change_vs_the_same_point_last_month(client, ids):
    add(client, ids, -10000, "food", "2026-09-10")
    add(client, ids, -99999, "food", "2026-09-28")  # after Sep 23: not part of the compare range
    add(client, ids, -10600, "food", "2026-10-10")

    assert summary(client)["spending_change"] == {"previous_cents": 10000, "change_cents": 600, "change_percent": 6.0}


def test_same_income_is_zero_percent(client, ids):
    add(client, ids, 540000, "paycheck", "2026-09-15")
    add(client, ids, 540000, "paycheck", "2026-10-15")

    assert summary(client)["income_change"] == {"previous_cents": 540000, "change_cents": 0, "change_percent": 0.0}


def test_nothing_last_period_has_no_percent(client, ids):
    add(client, ids, -5000, "food", "2026-10-05")

    assert summary(client)["spending_change"] == {"previous_cents": 0, "change_cents": 5000, "change_percent": None}


def test_saved_change_from_negative_to_positive(client, ids):
    add(client, ids, 100000, "paycheck", "2026-09-15")
    add(client, ids, -150000, "food", "2026-09-16")   # saved -$500 in September
    add(client, ids, 100000, "paycheck", "2026-10-15")
    add(client, ids, -80000, "food", "2026-10-16")    # saved +$200 in October

    assert summary(client)["saved_change"] == {"previous_cents": -50000, "change_cents": 70000, "change_percent": 140.0}


def test_net_worth_change_is_since_the_day_before_start(client, ids):
    add(client, ids, 500000, "paycheck", "2026-09-30")  # before the period: in the starting net worth
    add(client, ids, -20000, "food", "2026-10-01")      # first day of the period: part of the change
    add(client, ids, -7000, "food", "2026-10-24")       # after end: ignored

    body = summary(client)

    assert body["net_worth_cents"] == 480000
    assert body["net_worth_change_cents"] == -20000


@pytest.mark.parametrize("params", [
    {"start": "2026-10-31", "end": "2026-10-01"},
    {"start": "2026-10-01", "end": "2026-10-31", "compare_start": "2026-09-01"},
    {"start": "2026-10-01", "end": "2026-10-31", "compare_start": "2026-09-30", "compare_end": "2026-09-01"},
])
def test_bad_date_ranges_are_rejected(client, params):
    assert client.get("/api/dashboard/summary", params=params).status_code == 422
