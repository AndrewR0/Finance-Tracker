"""Savings goals: the waterfall math (pure functions) and the /api/goals endpoints."""

import datetime as dt

from app.goals import GoalStatus, allocate, months_until, progress

TODAY = dt.date(2026, 10, 23)  # same as the `today` fixture


# ---- pure functions ----

def test_allocate_fills_goals_in_order():
    assert allocate(500_000, [200_000, 450_000]) == [200_000, 300_000]


def test_allocate_leaves_later_goals_empty_when_money_runs_out():
    assert allocate(150_000, [200_000, 450_000]) == [150_000, 0]


def test_allocate_extra_money_is_simply_unclaimed():
    assert allocate(1_000_000, [200_000, 450_000]) == [200_000, 450_000]


def test_allocate_negative_balance_funds_nothing():
    assert allocate(-5_000, [200_000]) == [0]


def test_months_until_counts_calendar_months():
    assert months_until(TODAY, dt.date(2027, 1, 1)) == 3  # Nov, Dec, Jan
    assert months_until(TODAY, dt.date(2026, 10, 31)) == 1  # this month still counts as one


def one(balance, target, target_date, pace):
    return progress(balance_cents=balance, targets=[target], target_dates=[target_date], pace_cents=pace, today=TODAY)[0]


def test_funded_goal_is_done():
    p = one(250_000, 200_000, dt.date(2027, 1, 1), pace=0)
    assert (p.saved_cents, p.status, p.eta, p.needed_per_month_cents) == (200_000, GoalStatus.DONE, None, None)


def test_second_goal_waits_for_the_first():
    first, second = progress(
        balance_cents=500_000,
        targets=[200_000, 450_000],
        target_dates=[None, dt.date(2027, 1, 1)],
        pace_cents=100_000,
        today=TODAY,
    )
    assert first.status == GoalStatus.DONE
    # Short 150_000 in total; at 100_000 a month that's 2 months (rounded up).
    assert second.eta == dt.date(2026, 12, 23)
    assert second.status == GoalStatus.ON_TRACK
    assert second.needed_per_month_cents == 50_000  # 150_000 left over 3 months


def test_too_slow_is_behind():
    p = one(0, 600_000, dt.date(2027, 1, 1), pace=100_000)
    assert p.eta == dt.date(2027, 4, 23)
    assert p.status == GoalStatus.BEHIND
    assert p.needed_per_month_cents == 200_000


def test_not_growing_is_behind_with_no_eta():
    p = one(100_000, 600_000, dt.date(2027, 1, 1), pace=-20_000)
    assert (p.status, p.eta) == (GoalStatus.BEHIND, None)


def test_past_target_date_needs_everything_now():
    p = one(100_000, 600_000, dt.date(2026, 9, 1), pace=0)
    assert p.status == GoalStatus.BEHIND
    assert p.needed_per_month_cents == 500_000


def test_no_date_still_gets_an_eta():
    p = one(0, 300_000, None, pace=100_000)
    assert (p.status, p.eta, p.needed_per_month_cents) == (GoalStatus.NO_DATE, dt.date(2027, 1, 23), None)


def test_needed_per_month_rounds_up_to_the_cent():
    p = one(0, 100, dt.date(2027, 1, 1), pace=0)
    assert p.needed_per_month_cents == 34  # 100 / 3 = 33.3, so 34 gets there


# ---- endpoints ----

def account(client, name="Savings", type_="savings"):
    return client.post("/api/accounts", json={"name": name, "type": type_}).json()["id"]


def deposit(client, account_id, date, cents):
    response = client.post("/api/transactions", json={"account_id": account_id, "date": date, "amount_cents": cents})
    assert response.status_code == 201


def goal(client, account_id, name, target, target_date=None):
    response = client.post(
        "/api/goals",
        json={"name": name, "account_id": account_id, "target_cents": target, "target_date": target_date},
    )
    assert response.status_code == 201, response.text
    return response.json()


def goals(client):
    return {g["name"]: g for g in client.get("/api/goals").json()}


def test_create_and_list(client, today):
    savings = account(client)
    deposit(client, savings, "2026-10-01", 115_000)
    created = goal(client, savings, "New laptop", 200_000, "2027-01-31")
    assert created["saved_cents"] == 115_000
    assert created["needed_per_month_cents"] == 28_334  # 85_000 over Nov, Dec, Jan
    assert [g["name"] for g in client.get("/api/goals").json()] == ["New laptop"]


def test_pace_comes_from_the_last_three_months(client, today):
    savings = account(client)
    deposit(client, savings, "2026-07-01", 100_000)  # before Jul 23: counts as "then"
    deposit(client, savings, "2026-09-15", 300_000)
    created = goal(client, savings, "Japan", 1_000_000)
    assert created["account_pace_cents"] == 100_000  # (400_000 - 100_000) / 3
    assert created["eta"] == "2027-04-23"  # 600_000 short at 100_000 a month


def test_goals_on_one_account_fill_in_order(client, today):
    savings = account(client)
    deposit(client, savings, "2026-10-01", 500_000)
    goal(client, savings, "Laptop", 200_000)
    goal(client, savings, "Japan", 450_000)
    found = goals(client)
    assert (found["Laptop"]["saved_cents"], found["Japan"]["saved_cents"]) == (200_000, 300_000)
    assert found["Laptop"]["status"] == "done"


def test_goals_on_different_accounts_are_separate(client, today):
    savings, hysa = account(client), account(client, "HYSA")
    deposit(client, savings, "2026-10-01", 100_000)
    deposit(client, hysa, "2026-10-01", 50_000)
    goal(client, savings, "Laptop", 200_000)
    goal(client, hysa, "Bike", 80_000)
    found = goals(client)
    assert (found["Laptop"]["saved_cents"], found["Bike"]["saved_cents"]) == (100_000, 50_000)


def test_reorder_changes_who_gets_the_money(client, today):
    savings = account(client)
    deposit(client, savings, "2026-10-01", 300_000)
    laptop = goal(client, savings, "Laptop", 200_000)
    japan = goal(client, savings, "Japan", 450_000)
    response = client.put("/api/goals/order", json={"ids": [japan["id"], laptop["id"]]})
    assert response.status_code == 200
    assert [g["name"] for g in response.json()] == ["Japan", "Laptop"]
    found = goals(client)
    assert (found["Japan"]["saved_cents"], found["Laptop"]["saved_cents"]) == (300_000, 0)


def test_reorder_must_list_every_goal(client, today):
    savings = account(client)
    laptop = goal(client, savings, "Laptop", 200_000)
    goal(client, savings, "Japan", 450_000)
    assert client.put("/api/goals/order", json={"ids": [laptop["id"]]}).status_code == 422
    assert client.put("/api/goals/order", json={"ids": [laptop["id"], laptop["id"]]}).status_code == 422


def test_archiving_frees_the_money_for_the_next_goal(client, today):
    savings = account(client)
    deposit(client, savings, "2026-10-01", 300_000)
    laptop = goal(client, savings, "Laptop", 200_000)
    goal(client, savings, "Japan", 450_000)

    archived = client.patch(f"/api/goals/{laptop['id']}", json={"archived": True}).json()
    assert archived["archived_at"].startswith("2026-10-23")
    assert archived["saved_cents"] == 0
    assert goals(client)["Japan"]["saved_cents"] == 300_000
    # Active goals are listed before archived ones.
    assert [g["name"] for g in client.get("/api/goals").json()] == ["Japan", "Laptop"]


def test_restoring_puts_the_goal_last(client, today):
    savings = account(client)
    deposit(client, savings, "2026-10-01", 300_000)
    laptop = goal(client, savings, "Laptop", 200_000)
    goal(client, savings, "Japan", 450_000)
    client.patch(f"/api/goals/{laptop['id']}", json={"archived": True})
    restored = client.patch(f"/api/goals/{laptop['id']}", json={"archived": False}).json()
    assert restored["archived_at"] is None
    assert restored["saved_cents"] == 0  # Japan, now ahead of it, keeps the money
    assert goals(client)["Japan"]["saved_cents"] == 300_000


def test_edit_a_goal(client, today):
    savings, hysa = account(client), account(client, "HYSA")
    deposit(client, hysa, "2026-10-01", 50_000)
    laptop = goal(client, savings, "Laptop", 200_000, "2027-01-31")
    response = client.patch(
        f"/api/goals/{laptop['id']}",
        json={"name": "Gaming laptop", "account_id": hysa, "target_cents": 250_000, "target_date": None},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["account_id"], body["target_cents"], body["target_date"]) == ("Gaming laptop", hysa, 250_000, None)
    assert (body["saved_cents"], body["status"]) == (50_000, "no_date")


def test_delete_a_goal(client, today):
    savings = account(client)
    laptop = goal(client, savings, "Laptop", 200_000)
    assert client.delete(f"/api/goals/{laptop['id']}").status_code == 204
    assert client.get("/api/goals").json() == []
    assert client.patch(f"/api/goals/{laptop['id']}", json={"name": "x"}).status_code == 404


def test_rejects_bad_goals(client, today, db_session):
    savings = account(client)
    bad = {"name": "Laptop", "account_id": savings}
    assert client.post("/api/goals", json={**bad, "target_cents": 0}).status_code == 422
    assert client.post("/api/goals", json={**bad, "target_cents": 1999.99}).status_code == 422
    assert client.post("/api/goals", json={**bad, "account_id": 999, "target_cents": 100}).status_code == 404

    client.post(f"/api/accounts/{savings}/close")  # empty, so it closes
    assert client.post("/api/goals", json={**bad, "target_cents": 100}).status_code == 409
