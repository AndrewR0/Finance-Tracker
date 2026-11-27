"""Year in Review: /api/review"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.clock import Today
from app.db import get_db
from app.review import year_in_review
from app.schemas import YearInReview

router = APIRouter(prefix="/api/review", tags=["review"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=YearInReview)
def review(db: DbSession, today: Today, year: int | None = None):
    """?year=2026 (defaults to this year). A year in progress covers Jan 1 to today."""
    year = year or today.year
    if year > today.year or year < 1900:
        raise HTTPException(status_code=422, detail=f"There's nothing to review for {year} yet.")
    return year_in_review(db, year, today)
