"""Savings goal endpoints: /api/goals"""

import datetime as dt
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balances import get_balances
from app.clock import Today
from app.db import get_db
from app.goals import PACE_MONTHS, GoalStatus, Progress, monthly_pace, progress
from app.models import Account, Goal
from app.recurring import add_months
from app.schemas import GoalCreate, GoalOrder, GoalRead, GoalUpdate

router = APIRouter(prefix="/api/goals", tags=["goals"])

DbSession = Annotated[Session, Depends(get_db)]

ARCHIVED = Progress(saved_cents=0, status=GoalStatus.DONE, eta=None, needed_per_month_cents=None)


def read_all(db: Session, today: dt.date) -> list[GoalRead]:
    """Every goal with its progress. Active goals first, in fill order, then archived ones."""
    goals = db.scalars(
        select(Goal).order_by(Goal.archived_at.is_not(None), Goal.position, Goal.id)
    ).all()
    balances = get_balances(db)
    balances_then = get_balances(db, add_months(today, -PACE_MONTHS))

    by_account: dict[int, list[Goal]] = defaultdict(list)
    for goal in goals:
        if goal.archived_at is None:
            by_account[goal.account_id].append(goal)

    found: dict[int, Progress] = {}
    pace: dict[int, int] = {}
    for account_id, active in by_account.items():
        now = balances.get(account_id, 0)
        pace[account_id] = monthly_pace(now, balances_then.get(account_id, 0))
        results = progress(
            balance_cents=now,
            targets=[g.target_cents for g in active],
            target_dates=[g.target_date for g in active],
            pace_cents=pace[account_id],
            today=today,
        )
        found.update({g.id: r for g, r in zip(active, results)})

    return [
        GoalRead(
            id=g.id,
            name=g.name,
            account_id=g.account_id,
            target_cents=g.target_cents,
            target_date=g.target_date,
            position=g.position,
            archived_at=g.archived_at,
            created_at=g.created_at,
            saved_cents=found.get(g.id, ARCHIVED).saved_cents,
            status=found.get(g.id, ARCHIVED).status,
            eta=found.get(g.id, ARCHIVED).eta,
            needed_per_month_cents=found.get(g.id, ARCHIVED).needed_per_month_cents,
            account_pace_cents=pace.get(g.account_id, 0),
        )
        for g in goals
    ]


def read_one(db: Session, today: dt.date, goal_id: int) -> GoalRead:
    # A goal's progress depends on the goals ahead of it, so work out all of them.
    return next(g for g in read_all(db, today) if g.id == goal_id)


def get_goal(db: Session, goal_id: int) -> Goal:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} does not exist.")
    return goal


def check_account(db: Session, account_id: int) -> None:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Account {account_id} does not exist.")
    if account.closed_at is not None:
        raise HTTPException(status_code=409, detail=f"{account.name} is closed. Pick an open account.")


@router.get("", response_model=list[GoalRead])
def list_goals(db: DbSession, today: Today):
    return read_all(db, today)


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, db: DbSession, today: Today):
    check_account(db, payload.account_id)
    # New goals go last, so they don't take money from goals you already have.
    last = db.scalar(select(func.max(Goal.position))) or 0
    goal = Goal(**payload.model_dump(), position=last + 1)
    db.add(goal)
    db.commit()
    return read_one(db, today, goal.id)


@router.patch("/{goal_id}", response_model=GoalRead)
def update_goal(goal_id: int, payload: GoalUpdate, db: DbSession, today: Today):
    goal = get_goal(db, goal_id)
    changes = payload.model_dump(exclude_unset=True)
    if "account_id" in changes:
        check_account(db, changes["account_id"])
    if "archived" in changes:
        archived = changes.pop("archived")
        if archived and goal.archived_at is None:
            goal.archived_at = dt.datetime.combine(today, dt.time())
        elif not archived and goal.archived_at is not None:
            # Back in line, at the end: restoring shouldn't take money from the goals now ahead of it.
            goal.archived_at = None
            goal.position = (db.scalar(select(func.max(Goal.position))) or 0) + 1
    for field, value in changes.items():
        setattr(goal, field, value)
    db.commit()
    return read_one(db, today, goal.id)


@router.put("/order", response_model=list[GoalRead])
def reorder_goals(payload: GoalOrder, db: DbSession, today: Today):
    """Set the fill order. Send every goal id, first-to-fill first."""
    goals = db.scalars(select(Goal)).all()
    if sorted(payload.ids) != sorted(g.id for g in goals):
        raise HTTPException(status_code=422, detail="Send every goal id exactly once.")
    position = {goal_id: index for index, goal_id in enumerate(payload.ids)}
    for goal in goals:
        goal.position = position[goal.id]
    db.commit()
    return read_all(db, today)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: DbSession):
    """Deleting a goal never touches money: it only stops tracking it."""
    db.delete(get_goal(db, goal_id))
    db.commit()
