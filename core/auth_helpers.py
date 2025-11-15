# core/auth_helpers.py

from fastapi import HTTPException
from datetime import datetime, timedelta
from uuid import uuid4
from sqlmodel import Session, select

# Use python-jose, NOT plain jwt
from jose import jwt


from models import (
    UserBuildingAccess,
    User,
    PasswordResetToken
)

from core.config import settings

SECRET_KEY = settings.JWT_SECRET_KEY       # ✅ correct
ALGORITHM = settings.JWT_ALGORITHM         # ✅ correct (HS256)



# ============================================================
# 🔐 VERIFY USER HAS ACCESS TO A BUILDING
# ============================================================
def verify_user_building_access(session: Session, username: str, building_id: int) -> None:
    """
    Verify that a user has permission to access a specific building.

    Rules:
    - Contractors → full access
    - HOA Manager/Board → only assigned buildings
    - If no match → 403
    """

    # Contractor = global access
    contractor = session.exec(
        select(UserBuildingAccess)
        .where(UserBuildingAccess.username == username)
        .where(UserBuildingAccess.role == "contractor")
    ).first()

    if contractor:
        return  # ✔ global access

    # Check access to a specific building
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


# ============================================================
# 👤 CREATE USER *WITHOUT* A PASSWORD
# ============================================================
def create_user_no_password(
    session: Session,
    full_name: str,
    email: str,
    hoa_name: str
):
    """
    Creates a user in the local database with NO password.
    Used for:
    - Admin-created HOA accounts
    - Approved signup requests
    """

    # Prevent duplicate email accounts
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists."
        )

    user = User(
        username=email,
        email=email,
        full_name=full_name,
        hoa_name=hoa_name,
        hashed_password=None,   # User sets password later
        created_at=datetime.utcnow(),
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


# ============================================================
# 🔑 CREATE PASSWORD-RESET TOKEN ENTRY (DB STORED)
# ============================================================
def create_password_token(
    session: Session,
    user_id: int,
    expires_minutes: int = 60
) -> str:
    """
    Creates a unique token stored in the DB.
    Used for password setup via emailed link.
    """

    token = uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)

    reset_entry = PasswordResetToken(
        user_id=user_id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=expires_at,
    )

    session.add(reset_entry)
    session.commit()
    session.refresh(reset_entry)

    return token


# ============================================================
# 📧 JWT TOKEN FOR PASSWORD SETUP (emailed link)
# ============================================================
def generate_password_setup_token(email: str) -> str:
    """
    Creates a signed JWT the user clicks to set a password.
    This token is NOT stored in the database.
    """
    expire = datetime.utcnow() + timedelta(hours=24)
    data = {"sub": email, "exp": expire}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_setup_token(token: str) -> str:
    """
    Verifies JWT token → returns email.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
