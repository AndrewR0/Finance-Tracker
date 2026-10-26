"""Category endpoints: /api/categories"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Category, CategoryKind
from app.schemas import CategoryCreate, CategoryRead, CategoryTree

router = APIRouter(prefix="/api/categories", tags=["categories"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CategoryTree])
def list_categories(db: DbSession, kind: CategoryKind | None = None):
    """Top-level categories with their subcategories nested. Filter with ?kind=expense."""
    query = (
        select(Category)
        .where(Category.parent_id.is_(None))
        # Load every category's subcategories in one extra query, not one per category.
        .options(selectinload(Category.subcategories))
        .order_by(Category.name)
    )
    if kind is not None:
        query = query.where(Category.kind == kind)
    return db.scalars(query).all()


def check_parent(db: Session, payload: CategoryCreate) -> None:
    """Raise HTTPException(422) if payload.parent_id isn't a valid parent. Return None if it's fine."""
    if payload.parent_id is None:
        return
    parent = db.get(Category, payload.parent_id)
    if parent is None:
        raise HTTPException(status_code=422, detail=f"Parent category {payload.parent_id} does not exist.")
    if parent.parent_id is not None:
        raise HTTPException(status_code=422, detail=f"{parent.name} is a subcategory, so it can't have subcategories of its own.")
    if payload.kind != parent.kind:
        raise HTTPException(status_code=422, detail=f"The subcategory kind '{payload.kind}' does not match its parent's kind '{parent.kind}'.")


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: DbSession):
    check_parent(db, payload)

    category = Category(name=payload.name, kind=payload.kind, parent_id=payload.parent_id)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        where = "under this parent" if payload.parent_id else f"among {payload.kind} categories"
        raise HTTPException(status_code=409, detail=f"A category named '{payload.name}' already exists {where}.")
    return category
