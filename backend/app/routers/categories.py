"""Category endpoints: /api/categories"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Category, CategoryKind, Transaction
from app.schemas import CategoryCreate, CategoryDeleted, CategoryRead, CategoryTree, CategoryUpdate

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


def check_parent(db: Session, parent_id: int | None, kind: CategoryKind) -> None:
    """Raise HTTPException(422) if parent_id isn't a valid parent for a `kind` category."""
    if parent_id is None:
        return
    parent = db.get(Category, parent_id)
    if parent is None:
        raise HTTPException(status_code=422, detail=f"Parent category {parent_id} does not exist.")
    if parent.parent_id is not None:
        raise HTTPException(status_code=422, detail=f"{parent.name} is a subcategory, so it can't have subcategories of its own.")
    if kind != parent.kind:
        raise HTTPException(status_code=422, detail=f"The subcategory kind '{kind}' does not match its parent's kind '{parent.kind}'.")


def duplicate_name(name: str, parent_id: int | None, kind: CategoryKind) -> HTTPException:
    where = "under this parent" if parent_id else f"among {kind} categories"
    return HTTPException(status_code=409, detail=f"A category named '{name}' already exists {where}.")


def get_category_or_404(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail=f"Category {category_id} does not exist.")
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: DbSession):
    check_parent(db, payload.parent_id, payload.kind)

    category = Category(name=payload.name, kind=payload.kind, parent_id=payload.parent_id)
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise duplicate_name(payload.name, payload.parent_id, payload.kind)
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(category_id: int, payload: CategoryUpdate, db: DbSession):
    """Rename a category, or move it: under another parent, or up to the top level."""
    category = get_category_or_404(db, category_id)
    changes = payload.model_dump(exclude_unset=True)

    if "parent_id" in changes:
        new_parent = changes["parent_id"]
        if new_parent == category.id:
            raise HTTPException(status_code=422, detail="A category can't go under itself.")
        if new_parent is not None and category.subcategories:
            raise HTTPException(
                status_code=422,
                detail=f"{category.name} has subcategories, so it can't become a subcategory itself "
                       "(only one level is allowed). Move or delete its subcategories first.",
            )
        check_parent(db, new_parent, category.kind)

    for field, value in changes.items():
        setattr(category, field, value)
    name, parent_id, kind = category.name, category.parent_id, category.kind  # before a rollback reloads them
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise duplicate_name(name, parent_id, kind)
    return category


@router.delete("/{category_id}", response_model=CategoryDeleted)
def delete_category(category_id: int, db: DbSession, move_to: int | None = None):
    """Delete a category (and its subcategories). Merge two categories with ?move_to=<id>.

    Its transactions are never deleted: they move to `move_to`, or become uncategorized
    if it's left out. move_to must be the same kind, and can't be one of the categories
    being deleted.
    """
    category = get_category_or_404(db, category_id)
    doomed = [category, *category.subcategories]
    doomed_ids = [c.id for c in doomed]

    if move_to is not None:
        target = db.get(Category, move_to)
        if target is None:
            raise HTTPException(status_code=422, detail=f"Category {move_to} does not exist.")
        if target.id in doomed_ids:
            raise HTTPException(status_code=422, detail=f"Can't move transactions into {target.name}: it's being deleted too.")
        if target.kind != category.kind:
            raise HTTPException(
                status_code=422,
                detail=f"{target.name} is an {target.kind} category, and {category.name} is {category.kind}. "
                       "Transactions can only move to a category of the same kind.",
            )

    # One UPDATE for every affected transaction, instead of loading each one into Python.
    moved = db.execute(
        update(Transaction).where(Transaction.category_id.in_(doomed_ids)).values(category_id=move_to)
    ).rowcount
    for sub in category.subcategories:  # children first, so the parent's id is free to delete
        db.delete(sub)
    db.flush()
    db.delete(category)
    db.commit()
    return CategoryDeleted(moved_transactions=moved)
