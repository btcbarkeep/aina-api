# core/auth_helpers.py
from fastapi import HTTPException
from sqlmodel import Session, select
from models import UserBuildingAccess

def verify_user_building_access(session: Session, username: str, building_id: int) -> None:
    """
    Verify that a user has permission to access a specific building.

    - HOA users can only access their own building(s)
    - Property Managers can access their assigned buildings
    - Contractors can access all buildings (wildcard role)
    """

    # Check if the user is a contractor — global access
    contractor = session.exec(
        select(UserBuildingAccess)
        .where(UserBuildingAccess.username == username)
        .where(UserBuildingAccess.role == "contractor")
    ).first()

    if contractor:
        return  # ✅ Global access granted

    # Check if the user has explicit access to this building
    allowed = session.exec(
        select(UserBuildingAccess)
        .where(UserBuildingAccess.username == username)
        .where(UserBuildingAccess.building_id == building_id)
    ).first()

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"User '{username}' is not authorized to access building {building_id}.",
        )
