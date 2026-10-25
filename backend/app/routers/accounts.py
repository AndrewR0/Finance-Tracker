"""Account endpoints: /api/accounts"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account
from app.schemas import AccountCreate, AccountRead

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

# "Give me a database session" as a reusable type. FastAPI calls get_db() for us.
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AccountRead])
def list_accounts(db: DbSession):
    # Open accounts first (closed_at IS NULL sorts first), then alphabetical.
    query = select(Account).order_by(Account.closed_at.is_not(None), Account.name)
    return db.scalars(query).all()


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: DbSession):
    account = Account(name=payload.name, type=payload.type)
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"An open account named '{payload.name}' already exists.")
    return account
