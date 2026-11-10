import datetime as dt

import pytest

from app.models import RecurringSeries
from app.recurring import Cadence, Charge, add_months, detect_series, upcoming

TODAY = dt.date(2026, 10, 23)


def charges(payee_id, dates, amounts, name="Payee"):
    """Charges to one payee. A single amount is used for every date."""
    if isinstance(amounts, int):
        amounts = [amounts] * len(dates)
    return [Charge(dt.date.fromisoformat(d), a, payee_id, name, None, 1) for d, a in zip(dates, amounts)]


MONTHLY = ["2026-06-15", "2026-07-15", "2026-08-17", "2026-09-15", "2026-10-15"]
WEEKLY = ["2026-09-25", "2026-10-02", "2026-10-09", "2026-10-16", "2026-10-23"]


# ======================= detect_series: pure unit tests =======================

def test_monthly_subscription():
    [s] = detect_series(charges(1, MONTHLY, 1199, "Spotify"), TODAY)
    assert (s.cadence, s.amount_cents, s.amount_varies) == (Cadence.MONTHLY, 1199, False)
    assert s.next_date == dt.date(2026, 11, 15)
    assert s.monthly_cents == 1199
    assert s.matched_amount_cents is None


def test_bill_that_moves_around_is_an_estimate():
    [s] = detect_series(charges(1, MONTHLY, [4800, 5100, 6200, 5000, 5300]), TODAY)
    assert s.amount_varies
    assert s.amount_cents == 5100  # the median


def test_weekly_costs_more_than_four_a_month():
    [s] = detect_series(charges(1, WEEKLY, 1000), TODAY)
    assert s.cadence == Cadence.WEEKLY
    assert s.monthly_cents == 4333  # 52 a year / 12


def test_yearly_needs_only_two_charges():
    [s] = detect_series(charges(1, ["2025-05-22", "2026-05-22"], 28620), TODAY)
    assert (s.cadence, s.next_date) == (Cadence.YEARLY, dt.date(2027, 5, 22))


def test_two_monthly_charges_are_not_enough():
    assert detect_series(charges(1, MONTHLY[-2:], 1199), TODAY) == []


def test_irregular_dates_are_not_recurring():
    dates = ["2026-07-01", "2026-07-04", "2026-08-20", "2026-08-22", "2026-10-10"]
    assert detect_series(charges(1, dates, 1000), TODAY) == []


def test_wildly_different_amounts_are_not_a_bill():
    # A weekly grocery run: regular, but not a bill.
    assert detect_series(charges(1, WEEKLY, [1500, 9800, 3100, 12000, 600]), TODAY) == []


def test_a_cancelled_subscription_drops_out():
    old = ["2026-03-15", "2026-04-15", "2026-05-15", "2026-06-15"]
    assert detect_series(charges(1, old, 1199), TODAY) == []


def test_one_exact_amount_can_repeat_inside_a_messy_payee():
    rent = charges(1, MONTHLY, 62000, "Zelle")
    other = charges(1, ["2026-07-03", "2026-07-04", "2026-09-02", "2026-10-20"], [2500, 1300, 4000, 900], "Zelle")
    [s] = detect_series(rent + other, TODAY)
    assert (s.matched_amount_cents, s.amount_cents) == (62000, 62000)


def test_two_payments_on_one_day_count_as_one_charge():
    split = charges(1, MONTHLY, 30000) + charges(1, MONTHLY, 32000)
    [s] = detect_series(split, TODAY)
    assert s.amount_cents == 62000


def test_soonest_first():
    later = charges(1, MONTHLY, 500, "Later")
    sooner = charges(2, ["2026-07-28", "2026-08-28", "2026-09-28"], 500, "Sooner")
    assert [s.payee_name for s in detect_series(later + sooner, TODAY)] == ["Sooner", "Later"]


@pytest.mark.parametrize(("day", "months", "expected"), [
    ("2026-01-31", 1, "2026-02-28"),
    ("2028-01-31", 1, "2028-02-29"),
    ("2026-11-15", 3, "2027-02-15"),
    ("2026-05-22", 12, "2027-05-22"),
])
def test_add_months(day, months, expected):
    assert add_months(dt.date.fromisoformat(day), months) == dt.date.fromisoformat(expected)


def test_upcoming_repeats_weekly_and_keeps_late_bills():
    weekly = detect_series(charges(1, WEEKLY, 1000, "Gym"), TODAY)
    late = detect_series(charges(2, ["2026-07-20", "2026-08-20", "2026-09-20"], 5000, "Late"), TODAY)
    window = upcoming(weekly + late, TODAY, TODAY + dt.timedelta(days=14))
    # Late was due Oct 20 and hasn't posted: it shows today.
    assert [(d.isoformat(), s.payee_name) for d, s in window] == [
        ("2026-10-23", "Late"), ("2026-10-30", "Gym"), ("2026-11-06", "Gym"),
    ]


# ======================= the endpoints (today is frozen at Oct 23, 2026) =======================

@pytest.fixture
def account(client):
    return client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()["id"]


def pay(client, account, payee, dates, amount_cents):
    for date in dates:
        response = client.post("/api/transactions", json={
            "account_id": account, "date": date, "amount_cents": -amount_cents, "payee": payee,
        })
        assert response.status_code == 201, response.json()


def test_lists_series(client, today, account):
    pay(client, account, "Spotify", MONTHLY, 1199)
    [s] = client.get("/api/recurring").json()
    assert (s["payee_name"], s["cadence"], s["next_date"], s["ignored"]) == ("Spotify", "monthly", "2026-11-15", False)


def test_income_is_not_a_bill(client, today, account):
    pay(client, account, "Employer", MONTHLY, -250000)  # negative "payment" = money in
    assert client.get("/api/recurring").json() == []


def test_upcoming_window(client, today, account):
    pay(client, account, "Spotify", MONTHLY, 1199)
    assert client.get("/api/recurring/upcoming", params={"days": 14}).json() == []
    [charge] = client.get("/api/recurring/upcoming", params={"days": 30}).json()
    assert (charge["date"], charge["payee_name"], charge["amount_cents"]) == ("2026-11-15", "Spotify", 1199)


def test_ignore_and_restore(client, today, account, db_session):
    pay(client, account, "Spotify", MONTHLY, 1199)
    payee_id = client.get("/api/recurring").json()[0]["payee_id"]

    for _ in range(2):  # twice: the second call updates the same row
        assert client.put("/api/recurring/ignored", json={"payee_id": payee_id, "ignored": True}).status_code == 204
    assert db_session.query(RecurringSeries).count() == 1
    assert client.get("/api/recurring").json()[0]["ignored"] is True
    assert client.get("/api/recurring/upcoming", params={"days": 30}).json() == []

    client.put("/api/recurring/ignored", json={"payee_id": payee_id, "ignored": False})
    assert client.get("/api/recurring").json()[0]["ignored"] is False


def test_ignoring_one_amount_is_separate_from_the_whole_payee(client, today, account, db_session):
    pay(client, account, "Zelle", MONTHLY, 62000)
    payee_id = client.get("/api/recurring").json()[0]["payee_id"]
    client.put("/api/recurring/ignored", json={"payee_id": payee_id, "matched_amount_cents": 62000, "ignored": True})
    client.put("/api/recurring/ignored", json={"payee_id": payee_id, "ignored": True})
    assert db_session.query(RecurringSeries).count() == 2


def test_ignore_unknown_payee(client):
    assert client.put("/api/recurring/ignored", json={"payee_id": 999, "ignored": True}).status_code == 404
