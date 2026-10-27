"""Account balances, derived from transactions. Never stored.

This lives outside the routers so other features (the dashboard's net worth,
reconciling) can reuse it without going through HTTP.
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Transaction


def get_balances(db: Session, as_of: dt.date | None = None) -> dict[int, int]:
    """Return {account_id: balance_cents} for every account that has transactions.

    as_of: count only transactions on or before this date. None means all of them.
    Accounts with no transactions are simply missing from the dict; callers treat
    missing as 0.
    """
    query = (
        select(Transaction.account_id, func.sum(Transaction.amount_cents))
        .group_by(Transaction.account_id)
    )
    if as_of is not None:
        query = query.where(Transaction.date <= as_of)

    rows = db.execute(query)
    return {account_id: total for account_id, total in rows}
