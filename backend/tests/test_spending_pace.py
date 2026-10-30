import pytest

from app.reports import running_totals


# ======================= running_totals (your code): plain unit tests =======================

def test_adds_up_bucket_by_bucket():
    assert running_totals({"d1": 100, "d2": 20, "d3": 3}, ["d1", "d2", "d3"]) == [100, 120, 123]


def test_quiet_buckets_keep_the_line_flat():
    assert running_totals({"d1": 100, "d3": 50}, ["d1", "d2", "d3", "d4"]) == [100, 100, 150, 150]


def test_quiet_start():
    assert running_totals({"d2": 70}, ["d1", "d2"]) == [0, 70]


def test_a_refund_brings_the_total_down():
    assert running_totals({"d1": 500, "d2": -200}, ["d1", "d2"]) == [500, 300]


def test_no_spending_is_all_zeros():
    assert running_totals({}, ["d1", "d2", "d3"]) == [0, 0, 0]


def test_no_keys_is_empty():
    assert running_totals({}, []) == []


# ======================= the endpoint (today is frozen at Oct 23, 2026) =======================

@pytest.fixture
def account(client):
    return client.post("/api/accounts", json={"name": "Visa", "type": "credit_card"}).json()["id"]


def spend(client, account, date, amount_cents, category=None):
    response = client.post("/api/transactions", json={
        "account_id": account, "date": date, "amount_cents": amount_cents, "category_id": category,
    })
    assert response.status_code == 201, response.json()


def pace(client, **params):
    response = client.get("/api/dashboard/spending-pace", params={"kind": "month", **params})
    assert response.status_code == 200, response.json()
    return response.json()


def current(body):
    return [p["current_cents"] for p in body["points"]]


def previous(body):
    return [p["previous_cents"] for p in body["points"]]


def test_month_has_a_point_per_day_and_stops_today(client, today):
    body = pace(client)

    assert [p["label"] for p in body["points"]] == [str(d) for d in range(1, 32)]  # October: 31 days
    assert current(body)[:23] == [0] * 23
    assert current(body)[23:] == [None] * 8  # Oct 24-31 haven't happened
    assert previous(body)[30] is None  # September has no 31st


def test_current_line_is_a_running_total(client, today, account):
    food = client.post("/api/categories", json={"name": "Food", "kind": "expense"}).json()["id"]
    spend(client, account, "2026-10-01", -1000, food)
    spend(client, account, "2026-10-02", 200, food)  # refund (uncategorized +200 would count as income)
    spend(client, account, "2026-10-03", -500, food)

    body = pace(client)

    assert current(body)[:4] == [1000, 800, 1300, 1300]
    assert current(body)[22] == 1300
    assert body["spent_cents"] == 1300


def test_previous_line_is_the_whole_previous_month(client, today, account):
    spend(client, account, "2026-09-02", -300)
    spend(client, account, "2026-09-24", -999)  # after "the same point" (Sep 23)

    body = pace(client)

    assert previous(body)[:2] == [0, 300]
    assert previous(body)[29] == 1299
    assert body["previous_same_point_cents"] == 300
    assert body["previous_total_cents"] == 1299


def test_projection_uses_the_daily_average_so_far(client, today, account):
    spend(client, account, "2026-10-05", -2300)  # 23 days in: $100/day, October has 31

    assert pace(client)["projected_cents"] == 3100


def test_finished_month_is_projected_at_what_was_spent(client, today, account):
    spend(client, account, "2026-09-10", -4200)

    body = pace(client, date="2026-09-10")

    assert body["projected_cents"] == body["spent_cents"] == 4200
    assert None not in current(body)[:30]  # every day of September has happened
    assert current(body)[30] is None  # 31 points because August has 31 days; Sep has no 31st


def test_year_has_a_point_per_month(client, today, account):
    spend(client, account, "2026-02-14", -100)
    spend(client, account, "2025-12-31", -50)

    body = pace(client, kind="year")

    assert [p["label"] for p in body["points"]] == [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    assert current(body) == [0, 100, 100, 100, 100, 100, 100, 100, 100, 100, None, None]
    assert previous(body)[-1] == 50


def test_matches_the_summary(client, today, account):
    spend(client, account, "2026-10-04", -6100)
    spend(client, account, "2026-10-09", 1500)
    spend(client, account, "2026-09-20", -870)
    spend(client, account, "2026-09-28", -5000)

    body = pace(client)

    def summary_spending(start, end):
        return client.get("/api/dashboard/summary", params={"start": start, "end": end}).json()["spending_cents"]

    assert body["spent_cents"] == summary_spending("2026-10-01", "2026-10-23")
    assert body["previous_same_point_cents"] == summary_spending("2026-09-01", "2026-09-23")


def test_income_and_transfers_are_left_out(client, today, account):
    checking = client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()["id"]
    paycheck = client.post("/api/categories", json={"name": "Paycheck", "kind": "income"}).json()["id"]
    spend(client, checking, "2026-10-01", 270000, paycheck)
    client.post("/api/transfers", json={
        "from_account_id": checking, "to_account_id": account, "date": "2026-10-02", "amount_cents": 61200,
    })

    assert pace(client)["spent_cents"] == 0


@pytest.mark.parametrize("params", [{"kind": "all"}, {"kind": "month", "date": "2026-11-01"}])
def test_all_and_future_periods_are_rejected(client, today, params):
    assert client.get("/api/dashboard/spending-pace", params=params).status_code == 422
