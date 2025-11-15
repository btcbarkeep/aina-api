# routers/user_access.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from models.user_access import UserBuildingAccess
from models.building import Building

from dependencies.auth import get_current_user

router = APIRouter(
    prefix="/user-access",
    tags=["User Access"]
)

@router.get("/", response_model=List[UserBuildingAccess])
def list_user_access(session: Session = Depends(get_session)):
    """List all user access records (admin use)."""
    return session.exec(select(UserBuildingAccess)).all()

@router.post("/", response_model=UserBuildingAccess)
def add_user_access(
    record: UserBuildingAccess,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    """Add a user-building access link."""
    session.add(record)
    session.commit()
    session.refresh(record)
    return record

@router.get("/me", response_model=List[UserBuildingAccess])
def my_access(
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user),
):
    """Get buildings current user has access to."""
    return session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == current_user)
    ).all()
