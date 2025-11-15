# core/auth_helpers.py

from fastapi import HTTPException
from datetime import datetime, timedelta
from sqlmodel import Session, select
from uuid import uuid4

from models import (
    UserBuildingAccess,
    User,                  # from models/user.py
    PasswordResetToken     # from models/user.py
)


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

    # Check if they are allowed on this specific building
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
    Creates a user in the LOCAL database with no password set.
    Used for:
    - Admin-invited HOA accounts
    - Approved signup requests
    """

    # Check if user already exists
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
        hashed_password=None,  # 🔥 user will set this later
        created_at=datetime.utcnow()
    )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


# ============================================================
# 🔑 CREATE PASSWORD SETUP TOKEN
# ============================================================
def create_password_token(
    session: Session,
    user_id: int,
    expires_minutes: int = 60
) -> str:
    """
    Generates a unique password-reset / set-password token.
    Stored in the local database in password_reset_tokens table.

    Returned token is emailed to the user.
    """

    token = uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)

    reset_entry = PasswordResetToken(
        user_id=user_id,
        token=token,
        created_at=datetime.utcnow(),
        expires_at=expires_at
    )

    session.add(reset_entry)
    session.commit()
    session.refresh(reset_entry)

    return token

## password generator

import jwt
from datetime import datetime, timedelta
from core.config import settings
from models.user_model import User  # Adjust if needed
from fastapi import HTTPException

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

def generate_password_setup_token(email: str) -> str:
    """
    Creates a short-lived token for password setup.
    """
    expire = datetime.utcnow() + timedelta(hours=24)
    data = {"sub": email, "exp": expire}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_setup_token(token: str) -> str:
    """
    Decodes the token and returns the email if valid.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")


def create_user_no_password(session, full_name: str, email: str, hoa_name: str):
    """
    Creates a user entry WITHOUT a password.
    Used for admin-created accounts & approved signup requests.
    """
    user = User(
        username=email,
        email=email,
        full_name=full_name,
        hoa_name=hoa_name,
        hashed_password=None,
    )

    session.add(user)
    session.commit()
    session.refresh(user)
    return user
