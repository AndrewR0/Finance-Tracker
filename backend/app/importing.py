"""CSV import helpers that don't need the database, so they're easy to test."""

import datetime as dt
from collections import defaultdict
from typing import NamedTuple

# Banks often post a few days after the purchase, so a hand-entered transaction and
# the bank's line for it can have different dates.
DUPLICATE_WINDOW_DAYS = 3


class Money(NamedTuple):
    """Just what's compared when looking for duplicates. Payees are left out on purpose:
    "SQ *BLUE BOTTLE 0423" from the bank and "Blue Bottle" typed by hand are the same coffee."""

    date: dt.date
    amount_cents: int


def find_duplicates(existing: list[Money], incoming: list[Money], window_days: int = DUPLICATE_WINDOW_DAYS) -> list[bool]:
    """For each incoming row, in order: True if it matches a transaction already saved.

    existing:    transactions already in the account.
    incoming:    rows from the CSV.
    Returns:     a list the same length as incoming.

    A match is the same amount, with dates at most window_days apart. Each existing
    transaction can be the match for only ONE incoming row: two $5.00 coffees on the
    same day in the CSV, with one already saved, means one duplicate and one new row.
    """
    # Only the same amount can match, so group the saved ones by amount first. Then each row
    # is compared with a handful of transactions, not all of them: years of rows stay fast.
    saved_by_amount: dict[int, list[int]] = defaultdict(list)
    for saved_index, saved in enumerate(existing):
        saved_by_amount[saved.amount_cents].append(saved_index)

    # Every possible (incoming, existing) match, closest dates first. Matching in that order,
    # instead of top to bottom through the CSV, stops a nearby but unrelated row from taking
    # a match that belongs to a closer one.
    candidates = sorted(
        (days, row_index, saved_index)
        for row_index, row in enumerate(incoming)
        for saved_index in saved_by_amount.get(row.amount_cents, ())
        if (days := abs((existing[saved_index].date - row.date).days)) <= window_days
    )

    duplicate = [False] * len(incoming)
    used: set[int] = set()  # existing transactions already matched to a row
    for _, row_index, saved_index in candidates:
        if not duplicate[row_index] and saved_index not in used:
            duplicate[row_index] = True
            used.add(saved_index)
    return duplicate
