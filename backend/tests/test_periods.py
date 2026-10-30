from datetime import date

import pytest

from app.periods import Period, PeriodKind, one_period_back, resolve_period

MONTH, YEAR, ALL = PeriodKind.MONTH, PeriodKind.YEAR, PeriodKind.ALL


# ======================= one_period_back (your code): plain unit tests =======================

@pytest.mark.parametrize("day, kind, expected", [
    (date(2026, 10, 23), MONTH, date(2026, 9, 23)),
    (date(2026, 1, 15), MONTH, date(2025, 12, 15)),   # January wraps to last year's December
    (date(2026, 3, 31), MONTH, date(2026, 2, 28)),    # no Feb 31: use the last day of Feb
    (date(2024, 3, 31), MONTH, date(2024, 2, 29)),    # leap year: Feb has 29 days
    (date(2026, 5, 31), MONTH, date(2026, 4, 30)),    # 30-day month
    (date(2026, 3, 1), MONTH, date(2026, 2, 1)),
    (date(2026, 10, 23), YEAR, date(2025, 10, 23)),
    (date(2026, 1, 1), YEAR, date(2025, 1, 1)),
    (date(2028, 2, 29), YEAR, date(2027, 2, 28)),     # leap day, no leap day last year
])
def test_one_period_back(day, kind, expected):
    assert one_period_back(day, kind) == expected


# ======================= resolve_period =======================

def test_month_in_progress_compares_with_the_same_point_last_month():
    p = resolve_period(MONTH, date(2026, 10, 23), today=date(2026, 10, 23))

    assert p == Period(MONTH, date(2026, 10, 1), date(2026, 10, 23), date(2026, 9, 1), date(2026, 9, 23))


def test_finished_month_compares_with_the_whole_previous_month():
    # September has 30 days, August has 31: all of August counts, not Aug 1-30.
    p = resolve_period(MONTH, date(2026, 9, 12), today=date(2026, 10, 23))

    assert p == Period(MONTH, date(2026, 9, 1), date(2026, 9, 30), date(2026, 8, 1), date(2026, 8, 31))


def test_month_in_progress_at_the_end_of_a_long_month():
    p = resolve_period(MONTH, date(2026, 3, 30), today=date(2026, 3, 30))

    assert (p.compare_start, p.compare_end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_year_in_progress():
    p = resolve_period(YEAR, date(2026, 10, 23), today=date(2026, 10, 23))

    assert p == Period(YEAR, date(2026, 1, 1), date(2026, 10, 23), date(2025, 1, 1), date(2025, 10, 23))


def test_finished_year():
    p = resolve_period(YEAR, date(2025, 6, 1), today=date(2026, 10, 23))

    assert p == Period(YEAR, date(2025, 1, 1), date(2025, 12, 31), date(2024, 1, 1), date(2024, 12, 31))


def test_all_starts_at_the_first_transaction_and_has_no_compare():
    p = resolve_period(ALL, date(2026, 10, 23), today=date(2026, 10, 23), first_day=date(2025, 1, 4))

    assert p == Period(ALL, date(2025, 1, 4), date(2026, 10, 23), None, None)


def test_all_with_no_transactions_is_just_today():
    p = resolve_period(ALL, date(2026, 10, 23), today=date(2026, 10, 23))

    assert (p.start, p.end) == (date(2026, 10, 23), date(2026, 10, 23))


def test_future_period_is_rejected():
    with pytest.raises(ValueError):
        resolve_period(MONTH, date(2026, 11, 1), today=date(2026, 10, 23))


# ======================= the endpoint =======================

def get_period(client, **params):
    return client.get("/api/dashboard/period", params=params)


def test_date_defaults_to_today(client, today):
    body = get_period(client, kind="month").json()

    assert body == {
        "kind": "month",
        "start": "2026-10-01", "end": "2026-10-23",
        "compare_start": "2026-09-01", "compare_end": "2026-09-23",
        "previous_date": "2026-09-01",
        "next_date": None,  # November hasn't started
    }


def test_a_past_month_has_a_next_date(client, today):
    body = get_period(client, kind="month", date="2026-08-15").json()

    assert body["previous_date"] == "2026-07-01"
    assert body["next_date"] == "2026-09-01"


def test_all_uses_the_first_transaction(client, today):
    account = client.post("/api/accounts", json={"name": "Checking", "type": "checking"}).json()["id"]
    for day in ["2025-03-09", "2025-01-04"]:
        client.post("/api/transactions", json={"account_id": account, "date": day, "amount_cents": -100})

    body = get_period(client, kind="all").json()

    assert (body["start"], body["end"], body["compare_start"]) == ("2025-01-04", "2026-10-23", None)


def test_future_month_is_422(client, today):
    assert get_period(client, kind="month", date="2026-11-01").status_code == 422


def test_unknown_kind_is_422(client, today):
    assert get_period(client, kind="week").status_code == 422
