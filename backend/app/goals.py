"""Goal progress, derived from account balances. Nothing here is stored.

Goals on one account fill in order: the first takes what it needs from the balance,
the next one takes what's left, and so on (a "waterfall"). So the same dollar is never
counted toward two goals.

These are pure functions (numbers in, numbers out) so they're easy to test without a database.
"""

import datetime as dt
import enum
from dataclasses import dataclass

from app.recurring import add_months

PACE_MONTHS = 3  # how far back to look when working out how fast an account is growing


class GoalStatus(enum.StrEnum):
    DONE = "done"  # fully funded
    ON_TRACK = "on_track"  # at the current pace, funded by the target date
    BEHIND = "behind"  # at the current pace, not funded in time (or not growing at all)
    NO_DATE = "no_date"  # no target date, so nothing to be on track for


@dataclass
class Progress:
    saved_cents: int
    status: GoalStatus
    eta: dt.date | None  # when it's funded at the current pace; None if done or never
    needed_per_month_cents: int | None  # to hit the target date; None without a date, or when done


def allocate(balance_cents: int, targets: list[int]) -> list[int]:
    """Split one balance across goals, in order. Returns how much each goal has.

    allocate(500_000, [200_000, 450_000]) -> [200_000, 300_000]
    A negative balance (an overdrawn account) funds nothing.
    """
    remaining = max(balance_cents, 0)
    saved = []
    for target in targets:
        take = min(remaining, target)
        saved.append(take)
        remaining -= take
    return saved


def months_until(today: dt.date, day: dt.date) -> int:
    """Calendar months left until `day`, counting the month it falls in. At least 1.

    Nov 20 -> Jan 15 is 2 (December and January). Nov 20 -> Nov 30 is 1.
    """
    return max(1, (day.year - today.year) * 12 + day.month - today.month)


def monthly_pace(balance_now: int, balance_then: int) -> int:
    """Average growth per month over the last PACE_MONTHS months. Negative if it shrank."""
    return round((balance_now - balance_then) / PACE_MONTHS)


def progress(
    *,
    balance_cents: int,
    targets: list[int],
    target_dates: list[dt.date | None],
    pace_cents: int,
    today: dt.date,
) -> list[Progress]:
    """Progress for every active goal on one account, in fill order."""
    results = []
    funded_through = 0  # this goal's target plus every target ahead of it
    for saved, target, target_date in zip(allocate(balance_cents, targets), targets, target_dates):
        funded_through += target
        if saved >= target:
            results.append(Progress(saved, GoalStatus.DONE, None, None))
            continue

        # This goal is funded once the balance covers it AND every goal ahead of it.
        shortfall = funded_through - balance_cents
        eta = None
        if pace_cents > 0:
            eta = add_months(today, -(-shortfall // pace_cents))  # -(-a // b) rounds up

        if target_date is None:
            results.append(Progress(saved, GoalStatus.NO_DATE, eta, None))
            continue

        # What this goal alone still needs, spread over the months left (all of it if the date passed).
        months_left = months_until(today, target_date) if target_date >= today else 1
        needed = -(-(target - saved) // months_left)
        on_track = eta is not None and eta <= target_date
        results.append(Progress(saved, GoalStatus.ON_TRACK if on_track else GoalStatus.BEHIND, eta, needed))
    return results
