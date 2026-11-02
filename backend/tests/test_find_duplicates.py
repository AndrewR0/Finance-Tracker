"""find_duplicates: which CSV rows are already in the account."""

from datetime import date

from app.importing import Money, find_duplicates


def m(day, cents):
    """Money on a day in October 2026."""
    return Money(date(2026, 10, day), cents)


def test_nothing_saved_means_nothing_is_a_duplicate():
    assert find_duplicates([], [m(1, -500), m(2, -900)]) == [False, False]


def test_same_day_same_amount_is_a_duplicate():
    assert find_duplicates([m(5, -500)], [m(5, -500)]) == [True]


def test_different_amount_is_not():
    assert find_duplicates([m(5, -500)], [m(5, -501)]) == [False]


def test_sign_matters():
    # A $5 refund is not the same as a $5 purchase.
    assert find_duplicates([m(5, -500)], [m(5, 500)]) == [False]


def test_bank_posting_a_few_days_later_is_still_a_duplicate():
    assert find_duplicates([m(5, -500)], [m(8, -500)]) == [True]  # 3 days later
    assert find_duplicates([m(5, -500)], [m(2, -500)]) == [True]  # or earlier


def test_too_far_apart_is_not():
    assert find_duplicates([m(5, -500)], [m(9, -500)]) == [False]  # 4 days


def test_window_can_be_changed():
    assert find_duplicates([m(5, -500)], [m(5, -500), m(6, -500)], window_days=0) == [True, False]


def test_each_saved_transaction_matches_only_once():
    # Two coffees on the CSV, one already typed in: one duplicate, one new.
    assert find_duplicates([m(5, -500)], [m(5, -500), m(5, -500)]) == [True, False]


def test_two_saved_two_incoming():
    assert find_duplicates([m(5, -500), m(5, -500)], [m(5, -500), m(5, -500)]) == [True, True]


def test_the_result_follows_the_incoming_order():
    incoming = [m(1, -100), m(5, -500), m(9, -900)]

    assert find_duplicates([m(9, -900), m(1, -100)], incoming) == [True, False, True]


def test_empty_csv():
    assert find_duplicates([m(5, -500)], []) == []


def test_a_closer_match_is_not_stolen():
    # Saved: a $5 coffee on Oct 5 only. The CSV has the same coffee posted Oct 5, plus an
    # unrelated $5 on Oct 2. The Oct 5 row is the real duplicate, whatever order rows come in.
    assert find_duplicates([m(5, -500)], [m(2, -500), m(5, -500)]) == [False, True]
